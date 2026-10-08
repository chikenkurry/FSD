"""Prepare sparse, option-based decisions without inventing option facts.

This is a versioned handoff for a future generic matcher. The activity/time
contract in pipeline.py remains available for existing rounds.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation

from decision_service.contract import ContractError, group_objective

from .common import InputError, issue as _issue, require_in, require_int, require_list, require_object, require_text
from .canonicalization import Canonicalizer
from .generic_mapping import QUESTION_NUMERIC_INTENTS, TYPES, fact_registry, local_question, model_question_role, question_numeric_intent, resolve_mapping
from .generic_preparation import MEMBER_ISSUES, compile_preparation
from .generic_answers import process_answers
from .scenarios import DEFAULT_MAX_SCENARIO_REQUESTS, build_scenario_requests
from .member_importance import importance_question
from .semantics import (
    SemanticProvider, SemanticServiceError,
    validate_sparse_option_suggestions, validate_sparse_question_assessment,
)


SCHEMA_VERSION = "sparse-v4"
VERSION = "sparse-v11"


def _slug(value: str) -> str:
    slug = re.sub(r"[^\w]+", "-", value.casefold(), flags=re.UNICODE).strip("-_ ")
    if not slug:
        raise InputError("INVALID_ID", "planning.options", "Option name needs letters or digits")
    return slug


def _choices(raw: object, path: str) -> dict[str, str]:
    if raw is None:
        return {}
    result = {}
    for i, item in enumerate(require_list(raw, path)):
        if isinstance(item, str):
            label = require_text(item, f"{path}[{i}]")
            choice_id = _slug(label)
        else:
            item = require_object(item, f"{path}[{i}]")
            choice_id = require_text(item.get("choice_id"), f"{path}[{i}].choice_id")
            label = require_text(item.get("label"), f"{path}[{i}].label")
        if choice_id in result:
            raise InputError("DUPLICATE_ID", path, "Duplicate choice ID")
        result[choice_id] = label
    return result


def _local_question(label: str) -> dict | None:
    """A small domain-independent fallback when no semantic provider is set."""
    text = label.casefold()
    if any(term in text for term in ("availab", "when are you free", "when can you")):
        return {"role": "hard", "criterion": "availability", "relevance": 0.0, "reason": "Availability may constrain the choice"}
    if any(term in text for term in ("budget", "maximum spend", "max spend", "how much can you spend")):
        return {"role": "hard", "criterion": "max_cost", "relevance": 0.0, "reason": "A maximum spend is a feasibility limit"}
    if "days" in text and any(term in text for term in ("how many", "how long", "duration", "length")):
        return {"role": "soft", "criterion": "duration_days", "relevance": 0.5, "reason": "Duration may affect the choice"}
    if "prefer" in text or "what do you enjoy" in text:
        return {"role": "soft", "criterion": "preferences", "relevance": 0.5, "reason": "The question asks for preferences"}
    return None


def _fact(raw: object, path: str) -> dict:
    item = require_object(raw, path)
    criterion = require_text(item.get("criterion"), f"{path}.criterion")
    status = require_in(item.get("status"), {"confirmed", "estimated", "unknown"}, f"{path}.status")
    source = require_text(item.get("source"), f"{path}.source")
    value = item.get("value")
    values = value if isinstance(value, list) else [value]
    if status == "unknown":
        if value is not None or item.get("value_type") is None:
            raise InputError("INVALID_FACT", path, "Unknown facts need a null value and an explicit value_type")
    elif not values or any(v is None or isinstance(v, (dict, list)) or
                         (isinstance(v, str) and not v.strip()) or
                         (isinstance(v, float) and not math.isfinite(v)) for v in values):
        raise InputError("INVALID_FACT", f"{path}.value", "Provide a factual value or nonempty list of values")
    fact = {"criterion": criterion, "value": value, "status": status, "source": source}
    if "value_type" in item:
        fact["value_type"] = require_text(item["value_type"], f"{path}.value_type")
    if "unit" in item:
        fact["unit"] = require_text(item["unit"], f"{path}.unit")
    if "context" in item:
        fact["context"] = require_object(item["context"], f"{path}.context")
    return fact


def _options(raw: object) -> list[dict]:
    options = []
    seen = set()
    for i, item in enumerate(require_list(raw, "planning.options")):
        path = f"planning.options[{i}]"
        if isinstance(item, str):
            title = require_text(item, path)
            option_id, description, facts = _slug(title), "", []
        else:
            item = require_object(item, path)
            title = require_text(item.get("title"), f"{path}.title")
            option_id = require_text(item.get("option_id", _slug(title)), f"{path}.option_id")
            description = item.get("description", "")
            if not isinstance(description, str):
                raise InputError("INVALID_TYPE", f"{path}.description", "Expected text")
            facts = [_fact(f, f"{path}.facts[{fi}]") for fi, f in enumerate(require_list(item.get("facts", []), f"{path}.facts"))]
            if len({f["criterion"] for f in facts}) != len(facts):
                raise InputError("DUPLICATE_ID", f"{path}.facts", "Duplicate fact criterion")
        if option_id in seen:
            raise InputError("DUPLICATE_ID", path, "Duplicate option ID")
        seen.add(option_id)
        options.append({"candidate_id": option_id, "option_id": option_id, "title": title, "description": description, "facts": facts})
    if not options:
        raise InputError("MISSING_OPTIONS", "planning.options", "At least one option is required")
    return options


def _check_option_cost_facts(candidates: list[dict], currency: str | None, cost_scope: str | None) -> None:
    for candidate in candidates:
        for fact in candidate["facts"]:
            if fact["criterion"] != "max_cost":
                continue
            if currency is not None and fact.get("unit") != currency:
                raise InputError("CURRENCY_MISMATCH", "planning.options.facts", "Cost fact currency differs from the budget currency")
            if cost_scope is not None and fact.get("context", {}).get("scope") != cost_scope:
                raise InputError("INVALID_COST_SCOPE", "planning.options.facts", "Cost fact scope differs from the budget scope")
            if fact["status"] == "unknown":
                continue
            try:
                amount = Decimal(str(fact["value"]))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise InputError("INVALID_COST", "planning.options.facts", "Cost fact needs a numeric amount") from exc
            if not amount.is_finite() or amount < 0:
                raise InputError("INVALID_COST", "planning.options.facts", "Cost fact needs a nonnegative amount")


def _scenario_costs(raw: object, currency: str | None, cost_scope: str | None, option_ids: set[str]) -> dict[tuple, dict]:
    costs = {}
    for i, entry in enumerate(require_list(raw, "planning.scenario_costs")):
        path = f"planning.scenario_costs[{i}]"
        item = require_object(entry, path)
        option_id = require_text(item.get("option_id"), f"{path}.option_id")
        if option_id not in option_ids:
            raise InputError("UNKNOWN_OPTION", path, "Cost references an unknown option")
        days = item.get("duration_days")
        if type(days) is not int or days < 1:
            raise InputError("INVALID_DURATION", f"{path}.duration_days", "Expected positive whole days")
        first = require_text(item.get("earliest_start_date"), f"{path}.earliest_start_date")
        last = require_text(item.get("latest_start_date"), f"{path}.latest_start_date")
        try:
            if date.fromisoformat(first) > date.fromisoformat(last):
                raise ValueError
        except ValueError as exc:
            raise InputError("INVALID_DATE", path, "Expected ordered ISO start dates") from exc
        cost_currency = require_text(item.get("currency"), f"{path}.currency").upper()
        if currency is not None and cost_currency != currency:
            raise InputError("CURRENCY_MISMATCH", path, "Cost and budget currencies differ")
        amount = item.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, (int, float, str)):
            raise InputError("INVALID_COST", f"{path}.amount", "Expected nonnegative amount")
        try:
            parsed = Decimal(str(amount))
        except InvalidOperation as exc:
            raise InputError("INVALID_COST", f"{path}.amount", "Expected nonnegative amount") from exc
        if not parsed.is_finite() or parsed < 0:
            raise InputError("INVALID_COST", f"{path}.amount", "Expected nonnegative amount")
        scope = require_text(item.get("scope"), f"{path}.scope")
        if cost_scope is not None and scope != cost_scope:
            raise InputError("INVALID_COST_SCOPE", path, "Cost evidence scope must match the decision budget scope")
        key = (option_id, days, first, last)
        if key in costs:
            raise InputError("DUPLICATE_ID", path, "Duplicate scenario cost")
        costs[key] = {"amount": str(parsed), "currency": cost_currency,
                      "scope": scope,
                      "status": require_in(item.get("status"), {"confirmed", "estimated"}, f"{path}.status"),
                      "source": require_text(item.get("source"), f"{path}.source")}
    return costs


def preprocess_sparse(
    planning_snapshot: dict, response_snapshot: dict, semantic_provider: SemanticProvider | None = None,
    semantic_evidence: dict | None = None,
    policy: dict | None = None,
) -> dict:
    issues: list[dict] = []
    try:
        planning = require_object(planning_snapshot, "planning")
        responses = require_object(response_snapshot, "responses")
        policy = require_object({} if policy is None else policy, "policy")
        objective = group_objective(policy.get("group_objective"))
        scenario_limit = require_int(policy.get("max_scenario_requests", DEFAULT_MAX_SCENARIO_REQUESTS), "policy.max_scenario_requests", minimum=1)
        round_id = require_text(planning.get("round_id"), "planning.round_id")
        revision = require_text(planning.get("option_revision"), "planning.option_revision")
        option_snapshot_id = require_text(planning.get("option_snapshot_id"), "planning.option_snapshot_id")
        response_snapshot_id = require_text(responses.get("response_snapshot_id"), "responses.response_snapshot_id")
        if responses.get("round_id") != round_id or responses.get("option_revision") != revision:
            raise InputError("STALE_SNAPSHOT", "responses", "Response round or option revision does not match planning")
        decision = require_text(planning.get("decision_question"), "planning.decision_question")
        context = {"decision_question": decision, "currency": planning.get("currency"),
                   "cost_scope": planning.get("cost_scope"),
                   "details": require_object(planning.get("context", {}), "planning.context")}
        currency = context["currency"]
        if currency is not None:
            currency = require_text(currency, "planning.currency").upper()
            if not re.fullmatch(r"[A-Z]{3}", currency):
                raise InputError("INVALID_CURRENCY", "planning.currency", "Use a three-letter currency code")
            context["currency"] = currency
        if context["cost_scope"] is not None:
            context["cost_scope"] = require_text(context["cost_scope"], "planning.cost_scope")
        candidates = _options(planning.get("options"))
        _check_option_cost_facts(candidates, currency, context["cost_scope"])
        registry = fact_registry(candidates)
        for raw in require_list(planning.get("criteria", []), "planning.criteria"):
            raw = require_object(raw, "planning.criteria")
            aid = require_text(raw.get("attribute_id"), "planning.criteria.attribute_id")
            definition = {"attribute_id": aid, "value_type": require_in(raw.get("value_type"), TYPES, "planning.criteria.value_type"),
                          "unit": raw.get("unit")}
            if definition["unit"] is not None:
                require_text(definition["unit"], "planning.criteria.unit")
            if aid in registry and registry[aid] != definition:
                raise InputError("CONFLICTING_FACT_TYPE", "planning.criteria", "Criterion declaration differs from supplied facts")
            registry[aid] = definition
        context["criteria"] = list(registry.values())
        context["options"] = [{"option_id": c["option_id"], "title": c["title"], "description": c["description"],
                               "facts": c["facts"]} for c in candidates]
        roster = [require_text(x, "planning.roster") for x in require_list(planning.get("roster"), "planning.roster")]
        if not roster or len(set(roster)) != len(roster):
            raise InputError("INVALID_ROSTER", "planning.roster", "Roster must contain unique member IDs")
        if semantic_evidence is not None:
            semantic_evidence = require_object(semantic_evidence, "semantic_evidence")
            if any(semantic_evidence.get(k) != v for k, v in {
                "option_snapshot_id": option_snapshot_id, "response_snapshot_id": response_snapshot_id,
                "processing_version": VERSION,
            }.items()):
                raise InputError("STALE_SEMANTIC_EVIDENCE", "semantic_evidence", "Evidence does not match these snapshots")
            if semantic_evidence.get("scenario_policy", {"max_requests": DEFAULT_MAX_SCENARIO_REQUESTS}) != {"max_requests": scenario_limit}:
                raise InputError("STALE_SEMANTIC_EVIDENCE", "semantic_evidence.scenario_policy", "Scenario policy differs from the recorded run")
            assessments = require_object(semantic_evidence.get("question_assessments"), "semantic_evidence.question_assessments")
            extracted = require_object(semantic_evidence.get("answer_assessments"), "semantic_evidence.answer_assessments")
            suggestions = require_object(semantic_evidence.get("option_suggestions", {}), "semantic_evidence.option_suggestions")
            date_assessments = require_object(semantic_evidence.get("date_assessments", {}), "semantic_evidence.date_assessments")
            canonical_assessments = require_object(semantic_evidence.get("canonical_assessments", {}), "semantic_evidence.canonical_assessments")
        else:
            assessments, extracted, suggestions, date_assessments = {}, {}, {}, {}
            canonical_assessments = {}

        canonicalizer = Canonicalizer(planning.get("canonicalization", {}), registry, semantic_provider,
                                      canonical_assessments, replay=semantic_evidence is not None,
                                      model_enabled=semantic_evidence.get("canonicalization_enabled") if semantic_evidence is not None else None,
                                      decision_question=decision)
        if semantic_evidence is not None and semantic_evidence.get("canonicalization_declarations", {}) != canonicalizer.declarations:
            raise InputError("STALE_SEMANTIC_EVIDENCE", "semantic_evidence.canonicalization_declarations", "Frozen aliases differ from this plan")
        canonicalizer.prepare_facts(candidates)
        registry = {aid: definition for aid, definition in registry.items() if aid in canonicalizer.target_ids}
        canonicalizer.registry = registry
        context["criteria"] = list(registry.values())
        context["canonicalization"] = canonicalizer.declarations

        questions = []
        ids = set()
        for i, raw in enumerate(require_list(planning.get("questions"), "planning.questions")):
            path = f"planning.questions[{i}]"
            item = require_object(raw, path)
            qid = require_text(item.get("question_id", item.get("id")), f"{path}.question_id")
            if qid in ids:
                raise InputError("DUPLICATE_ID", path, "Duplicate question ID")
            ids.add(qid)
            label = require_text(item.get("label", item.get("text")), f"{path}.label")
            choices = _choices(item.get("choices"), f"{path}.choices")
            canonical_label = canonicalizer.question_label(label)
            local = importance_question(canonical_label, registry) or local_question(canonical_label, registry) or _local_question(canonical_label)
            # The general preference fallback cannot identify a specific attribute.
            # Let a provider resolve that meaning when one is available.
            trusted_local = local if local and local["criterion"] != "preferences" else None
            if "role" in item or "criterion" in item:
                explicit = {"role": item.get("role"), "criterion": item.get("criterion"),
                            "relevance": item.get("relevance", 0.0),
                            "reason": item.get("reason", "Defined by the leader")}
                inferred = validate_sparse_question_assessment(explicit, path)
                source = "leader"
            elif trusted_local is not None:
                inferred = trusted_local
                source = "rules"
            elif qid in assessments:
                inferred = validate_sparse_question_assessment(assessments[qid], f"semantic.questions.{qid}", model_derived=True)
                inferred = model_question_role(inferred, label)
                source = "model"
            elif semantic_provider is not None:
                if not hasattr(semantic_provider, "classify_question"):
                    raise SemanticServiceError("Sparse questions require classify_question on the semantic provider")
                assessments[qid] = semantic_provider.classify_question({"question_id": qid, "label": label, "choices": choices}, context)
                inferred = validate_sparse_question_assessment(assessments[qid], f"semantic.questions.{qid}", model_derived=True)
                inferred = model_question_role(inferred, label)
                source = "model"
            else:
                inferred = local
                source = "rules"
                if inferred is None:
                    inferred = {"role": "unclassified", "criterion": "unclassified", "relevance": 0.0, "reason": "Question role needs review"}
                    issues.append(_issue("UNKNOWN_QUESTION_ROLE", path, "Question needs classification"))
                    source = "unclassified"
            if inferred["role"] not in {"informational", "importance", "unclassified"} or inferred["criterion"] in registry:
                try:
                    aid, model_canonical = canonicalizer.criterion(inferred["criterion"], path)
                    inferred = {**inferred, "criterion": aid}
                except InputError as exc:
                    if exc.code != "AMBIGUOUS_CANONICAL_LABEL":
                        raise
                    issues.append(exc.as_issue())
                    inferred = {**inferred, "role": "unclassified", "criterion": "unclassified", "relevance": 0.0}
                    model_canonical = False
            else:
                model_canonical = False
            weight = item.get("leader_weight")
            if weight is not None and (type(weight) not in {int, float} or not 0 <= weight <= 1e308):
                raise InputError("INVALID_WEIGHT", f"{path}.leader_weight", "Weight must be finite and nonnegative")
            if weight is not None and inferred["role"] != "soft":
                raise InputError("HARD_WEIGHT_UNSUPPORTED", path, "Only soft questions can carry a weight")
            questions.append({"question_id": qid, "label": label, "choices": choices, "role": inferred["role"],
                              "criterion": inferred["criterion"], "relevance": inferred["relevance"],
                              "reason": inferred["reason"], "inference_source": source,
                              "leader_weight": weight, "required": item.get("required", inferred["role"] != "informational")})
            if type(questions[-1]["required"]) is not bool:
                raise InputError("INVALID_TYPE", f"{path}.required", "Expected true or false")
            question = questions[-1]
            if model_canonical:
                question["canonicalization_source"] = "semantic_model"
            question["answer_format"] = require_in(item.get("answer_format", "choice" if choices else "text"),
                                                  {"text", "choice", "multi_choice", "number", "boolean", "date_intervals"}, f"{path}.answer_format")
            definition = registry.get(question["criterion"])
            numeric = question["criterion"] in {"max_cost", "duration_days"} or definition and definition["value_type"] in {"number", "decimal"}
            if "numeric_intent" in item and question["role"] == "unclassified":
                question.update(numeric_intent=require_in(item["numeric_intent"], QUESTION_NUMERIC_INTENTS, f"{path}.numeric_intent"),
                                numeric_intent_source="leader")
            elif "numeric_intent" in item and (not numeric or question["role"] not in {"soft", "hard"}):
                raise InputError("INVALID_MAPPING", f"{path}.numeric_intent", "Numeric intent requires a hard or soft numeric question")
            if numeric and question["role"] in {"soft", "hard"}:
                intent, intent_source = question_numeric_intent({**question, **({"numeric_intent": item["numeric_intent"]} if "numeric_intent" in item else {})}, item.get("mapping"))
                question.update(numeric_intent=intent, numeric_intent_source=intent_source)
            question["mapping"] = resolve_mapping(question, registry, candidates, context, item.get("mapping"))
            canonicalizer.register_choices(question)
            if question["mapping"]["status"] == "unresolved" and question["role"] != "unclassified":
                issues.append(_issue("UNRESOLVED_QUESTION_MAPPING", path, "Define a supported comparison or numeric scale for this question"))
        soft = [q for q in questions if q["role"] == "soft"]
        topic_counts = Counter(q["criterion"] for q in soft if q["leader_weight"] is None)
        leader_scale = max([1.0] + [float(q["leader_weight"]) for q in soft if q["leader_weight"] is not None])
        raw_weights = {q["question_id"]: (float(q["leader_weight"]) / leader_scale if q["leader_weight"] is not None
                                          else q["relevance"] / topic_counts[q["criterion"]]) for q in soft}
        total = sum(raw_weights.values())
        if soft and total == 0:
            issues.append(_issue("NO_RELEVANT_SOFT_QUESTION", "planning.questions", "No soft criterion has positive relevance"))
        for q in questions:
            q["weight"] = round(raw_weights[q["question_id"]] / total, 12) if q["role"] == "soft" and total else None
            q["weight_source"] = ("leader" if q["leader_weight"] is not None else q["inference_source"]) if q["role"] == "soft" else None
            del q["leader_weight"]

        constraints, preferences, informational, unclassified_answers, members, importance_entries = process_answers(
            responses, roster, questions, candidates, context, semantic_provider,
            extracted, date_assessments, response_snapshot_id, issues, registry, canonicalizer,
        )
        meanings = constraints + preferences
        answered_questions = {entry["question_id"] for entry in meanings}
        question_weights = {q["question_id"]: q["weight"] for q in questions}
        active_preferences = [entry for entry in preferences if question_weights[entry["question_id"]]]
        for i, q in enumerate(questions):
            entries = [entry for entry in meanings if entry["question_id"] == q["question_id"]]
            if entries and all(entry.get("mapping", q["mapping"])["status"] == "resolved" for entry in entries):
                issues[:] = [issue for issue in issues if not (issue["code"] == "UNRESOLVED_QUESTION_MAPPING"
                              and issue["path"] == f"planning.questions[{i}]")]

        has_schedule_questions = {"availability", "duration_days"} <= {q["criterion"] for q in questions}
        scenario_requests = build_scenario_requests(candidates, roster, constraints, preferences, questions, max_requests=scenario_limit) if has_schedule_questions else []
        scenario_criteria = {"availability", "duration_days", "max_cost"} if has_schedule_questions else set()
        criteria = sorted({q["criterion"] for q in questions
                           if q["question_id"] not in answered_questions and (q["role"] == "hard" or q["role"] == "soft" and q["weight"])
                           and q["criterion"] not in scenario_criteria} |
                          {entry["criterion"] for entry in constraints + active_preferences if entry["criterion"] not in scenario_criteria})
        for candidate in candidates:
            known = {f["criterion"] for f in candidate["facts"] if f["status"] != "unknown"}
            candidate["missing_criteria"] = [c for c in criteria if c not in known]
            option_id = candidate["option_id"]
            requested = sorted({entry["criterion"] for entry in active_preferences if entry["criterion"] in candidate["missing_criteria"]}
                               | {q["criterion"] for q in questions if q["role"] == "soft" and q["weight"]
                                  and q["question_id"] not in answered_questions and q["criterion"] in candidate["missing_criteria"]})
            requested = [aid for aid in requested if registry.get(aid, {}).get("value_type") in {"category", "tag_set"}]
            if option_id not in suggestions and requested and semantic_provider is not None and hasattr(semantic_provider, "suggest_option_tags"):
                suggestions[option_id] = semantic_provider.suggest_option_tags(
                    {"option_id": option_id, "title": candidate["title"], "description": candidate["description"]}, requested, context,
                )
            candidate["tag_suggestions"] = validate_sparse_option_suggestions(
                suggestions[option_id], set(requested), f"semantic.option_suggestions.{option_id}"
            ) if option_id in suggestions else []
        costs = _scenario_costs(planning.get("scenario_costs", []), currency, context["cost_scope"], {c["option_id"] for c in candidates})
        used_costs = set()
        for request in scenario_requests:
            key = (request["option_id"], request["duration_days"], request["earliest_start_date"], request["latest_start_date"])
            if key in costs:
                request["cost_evidence_status"] = costs[key]["status"]
                request["cost_evidence"] = costs[key]
                used_costs.add(key)
        if set(costs) - used_costs:
            raise InputError("UNMATCHED_SCENARIO_COST", "planning.scenario_costs", "Cost evidence does not match a feasible scenario request")
        if has_schedule_questions and not scenario_requests:
            issues.append(_issue("NO_SCHEDULE_SCENARIO", "responses.participants", "No shared date window fits a declared duration"))
        uses_cost = any(q["criterion"] == "max_cost" for q in questions) or any(entry["criterion"] == "max_cost" for entry in meanings)
        if uses_cost and currency is None:
            issues.append(_issue("MISSING_CURRENCY", "planning.currency", "Specify the budget currency"))
        if uses_cost and context["cost_scope"] is None:
            issues.append(_issue("MISSING_COST_SCOPE", "planning.cost_scope", "Define what the budget includes and whom it covers"))
        if any(candidate["missing_criteria"] for candidate in candidates):
            issues.append(_issue("MISSING_OPTION_FACTS", "planning.options", "Option criteria need sourced facts before confirmation"))
        if any(f["status"] == "estimated" for candidate in candidates for f in candidate["facts"] if f["criterion"] in criteria):
            issues.append(_issue("ESTIMATED_OPTION_FACTS", "planning.options", "Estimated option facts require confirmation before a final comparison"))
        if any(q["criterion"] == "max_cost" for q in questions) and has_schedule_questions:
            if any(r["cost_evidence_status"] == "unknown" for r in scenario_requests):
                issues.append(_issue("MISSING_SCENARIO_COST", "planning.options", "Sourced costs are needed for the proposed dates and durations"))
            if any(r["cost_evidence_status"] == "estimated" for r in scenario_requests):
                issues.append(_issue("ESTIMATED_SCENARIO_COST", "planning.scenario_costs", "Estimated costs require confirmation before a hard budget check"))

        frozen = None
        if assessments or extracted or suggestions or date_assessments or canonical_assessments or semantic_evidence is not None:
            frozen = semantic_evidence or {"option_snapshot_id": option_snapshot_id, "response_snapshot_id": response_snapshot_id,
                                           "processing_version": VERSION, "model": getattr(semantic_provider, "model", None),
                                           "question_assessments": assessments, "answer_assessments": extracted,
                                           "option_suggestions": suggestions, "date_assessments": date_assessments,
                                           "canonical_assessments": canonical_assessments,
                                           "canonicalization_enabled": canonicalizer.model_enabled,
                                           "canonicalization_declarations": canonicalizer.declarations,
                                           "scenario_policy": {"max_requests": scenario_limit}}
        artifact_id = hashlib.sha256(json.dumps(frozen, sort_keys=True, ensure_ascii=False).encode()).hexdigest() if frozen else None
        handoff = {"context": {"schema_version": SCHEMA_VERSION, "round_id": round_id, "option_revision": revision,
                                "processing_version": VERSION,
                                "policy_version": require_text(policy.get("policy_version", "generic-question-relevance-v1"), "policy.policy_version"),
                                "max_scenario_requests": scenario_limit,
                                "option_snapshot_id": option_snapshot_id, "response_snapshot_id": response_snapshot_id,
                                "decision_question": decision, "currency": currency, "cost_scope": context["cost_scope"],
                                "details": context["details"],
                                "semantic_artifact_id": artifact_id},
                   "candidates": candidates, "scenario_requests": scenario_requests,
                   "participants": [{"participant_id": x, "response_status": members.get(x, {}).get("response_status", "incomplete"),
                                     "is_required_for_decision": True} for x in roster],
                   "constraints": constraints, "preferences": preferences, "informational_answers": informational,
                   "unclassified_answers": unclassified_answers, "importance_entries": importance_entries,
                   "canonicalization": canonicalizer.packet(),
                   "scoring_model": {"questions": questions, "missing_fact_policy": "unresolved", "group_objective": objective}}
        handoff = compile_preparation(handoff, registry, issues)
        issues.append(_issue("EXECUTION_ADAPTER_REQUIRED", "preparation", "Sparse meanings need a supported execution adapter before ranking"))
        status = "needs_clarification" if any(i["code"] in MEMBER_ISSUES for i in issues) else "provisional"
        return {"status": status, "issues": issues, "algorithm_input": None, "preparation": handoff, "semantic_evidence": frozen}
    except InputError as exc:
        return {"status": "invalid_input", "issues": [exc.as_issue()], "algorithm_input": None}
    except ContractError as exc:
        return {"status": "invalid_input", "issues": [_issue("INVALID_POLICY", "policy", str(exc))], "algorithm_input": None}
    except SemanticServiceError as exc:
        return {"status": "upstream_unavailable", "issues": [_issue("SEMANTIC_SERVICE_UNAVAILABLE", "semantic_provider", str(exc))], "algorithm_input": None}
