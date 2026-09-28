"""Prepare sparse, option-based decisions without inventing option facts.

This is a versioned handoff for a future generic matcher. The activity/time
contract in pipeline.py remains available for existing rounds.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from .common import InputError, require_in, require_list, require_object, require_text
from .semantics import (
    SemanticProvider, SemanticServiceError, validate_sparse_answer_assessment,
    validate_sparse_dates, validate_sparse_option_suggestions, validate_sparse_question_assessment,
)


VERSION = "sparse-v2"
NO_PREFERENCE = {"anything", "fine with anything", "no preference", "none", "either"}
DATE_RANGE_RE = re.compile(r"\s*(\d{4}-\d{2}-\d{2})(?:\s*(?:to|through|until|–|—| - )\s*(\d{4}-\d{2}-\d{2}))?\s*", re.I)


def _issue(code: str, path: str, message: str) -> dict:
    return {"code": code, "path": path, "message": message}


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
    if any(term in text for term in ("how many days", "how long", "duration", "length")):
        return {"role": "soft", "criterion": "duration_days", "relevance": 0.5, "reason": "Duration may affect the choice"}
    if "prefer" in text or "what do you enjoy" in text:
        return {"role": "soft", "criterion": "preferences", "relevance": 0.5, "reason": "The question asks for preferences"}
    return None


def _fact(raw: object, path: str) -> dict:
    item = require_object(raw, path)
    criterion = require_text(item.get("criterion"), f"{path}.criterion")
    status = require_in(item.get("status"), {"confirmed", "estimated"}, f"{path}.status")
    source = require_text(item.get("source"), f"{path}.source")
    value = item.get("value")
    values = value if isinstance(value, list) else [value]
    if not values or any(v is None or isinstance(v, (dict, list)) or
                         (isinstance(v, str) and not v.strip()) or
                         (isinstance(v, float) and not math.isfinite(v)) for v in values):
        raise InputError("INVALID_FACT", f"{path}.value", "Provide a factual value or nonempty list of values")
    fact = {"criterion": criterion, "value": value, "status": status, "source": source}
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
            try:
                amount = Decimal(str(fact["value"]))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise InputError("INVALID_COST", "planning.options.facts", "Cost fact needs a numeric amount") from exc
            if not amount.is_finite() or amount < 0:
                raise InputError("INVALID_COST", "planning.options.facts", "Cost fact needs a nonnegative amount")
            if currency is not None and fact.get("unit") != currency:
                raise InputError("CURRENCY_MISMATCH", "planning.options.facts", "Cost fact currency differs from the budget currency")
            if cost_scope is not None and fact.get("context", {}).get("scope") != cost_scope:
                raise InputError("INVALID_COST_SCOPE", "planning.options.facts", "Cost fact scope differs from the budget scope")


def _answer_text(value: object, question: dict, path: str) -> str:
    if isinstance(value, dict):
        choice_id = require_text(value.get("choice_id"), f"{path}.choice_id")
        if choice_id not in question["choices"]:
            raise InputError("UNKNOWN_CHOICE", path, "Answer references a choice outside this question")
        return question["choices"][choice_id]
    text = require_text(value, path)
    if question["choices"] and text not in question["choices"].values() and text not in question["choices"]:
        raise InputError("UNKNOWN_CHOICE", path, "Answer must use a declared choice")
    return question["choices"].get(text, text)


def _dates(value: object, path: str) -> list[dict] | None:
    if isinstance(value, list):
        intervals = []
        for i, raw in enumerate(value):
            item = require_object(raw, f"{path}[{i}]")
            start = require_text(item.get("start_date"), f"{path}[{i}].start_date")
            end = require_text(item.get("end_date"), f"{path}[{i}].end_date")
            try:
                if date.fromisoformat(start) > date.fromisoformat(end):
                    raise ValueError
            except ValueError as exc:
                raise InputError("INVALID_DATE", f"{path}[{i}]", "Expected ordered ISO dates") from exc
            intervals.append({"start_date": start, "end_date": end})
        return intervals or None
    text = require_text(value, path)
    match = DATE_RANGE_RE.fullmatch(text)
    if match is None:
        return None
    try:
        start = date.fromisoformat(match.group(1))
        end = date.fromisoformat(match.group(2) or match.group(1))
    except ValueError:
        return None
    if start > end:
        return None
    return [{"start_date": start.isoformat(), "end_date": end.isoformat()}]


def _budget(text: str, currency: str | None) -> dict | None:
    normalized = text.casefold().strip()
    if normalized in {"unlimited", "no limit", "no budget limit"}:
        return {"kind": "unlimited"}
    match = re.fullmatch(r"(?:(?P<prefix>[a-z]{3}|[$£€])\s*)?(?P<amount>[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?P<suffix>[a-z]{3})?", normalized)
    if not match:
        return None
    explicit = match.group("suffix") or match.group("prefix")
    if explicit and explicit not in {"$", "£", "€"} and currency and explicit.upper() != currency:
        return None
    if explicit in {"£", "€"} and currency and {"£": "GBP", "€": "EUR"}[explicit] != currency:
        return None
    if explicit == "$" and currency and currency not in {"SGD", "USD", "CAD", "AUD", "NZD", "HKD"}:
        return None
    try:
        amount = Decimal(match.group("amount").replace(",", ""))
    except InvalidOperation:
        return None
    if amount < 0:
        return None
    return {"kind": "limited", "amount": str(amount), "currency": currency}


def _duration(text: str) -> dict | None:
    normalized = text.casefold().strip()
    if normalized in NO_PREFERENCE:
        return {"kind": "indifferent"}
    match = re.fullmatch(r"(\d+)\s*(?:days?|nights?)?", normalized)
    if not match or not 1 <= int(match.group(1)) <= 365:
        return None
    return {"kind": "preferred", "days": int(match.group(1))}


def _scenario_requests(candidates: list[dict], roster: list[str], constraints: list[dict], preferences: list[dict], questions: list[dict]) -> list[dict]:
    """Combine shared availability with offered durations when both exist."""
    if not any(q["criterion"] == "availability" for q in questions):
        return []
    by_member = {member_id: [] for member_id in roster}
    for constraint in constraints:
        if constraint["criterion"] == "availability":
            by_member[constraint["participant_id"]].extend(constraint["value"])
    if any(not windows for windows in by_member.values()):
        return []
    common = [(date.fromisoformat(x["start_date"]), date.fromisoformat(x["end_date"])) for x in by_member[roster[0]]]
    for member_id in roster[1:]:
        other = [(date.fromisoformat(x["start_date"]), date.fromisoformat(x["end_date"])) for x in by_member[member_id]]
        common = [(max(a, c), min(b, d)) for a, b in common for c, d in other if max(a, c) <= min(b, d)]
    durations = set()
    for q in questions:
        if q["criterion"] == "duration_days":
            durations.update(parsed["days"] for label in q["choices"].values() if (parsed := _duration(label)) and parsed["kind"] == "preferred")
    durations.update(p["value"]["days"] for p in preferences if p["criterion"] == "duration_days" and p["value"]["kind"] == "preferred")
    result = []
    for candidate in candidates:
        for days in sorted(durations):
            for start, end in sorted(set(common)):
                latest = end - timedelta(days=days - 1)
                if latest >= start:
                    result.append({"option_id": candidate["option_id"], "duration_days": days,
                                   "earliest_start_date": start.isoformat(), "latest_start_date": latest.isoformat(),
                                   "cost_evidence_status": "unknown"})
    return result


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
) -> dict:
    issues: list[dict] = []
    try:
        planning = require_object(planning_snapshot, "planning")
        responses = require_object(response_snapshot, "responses")
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
            assessments = require_object(semantic_evidence.get("question_assessments"), "semantic_evidence.question_assessments")
            extracted = require_object(semantic_evidence.get("answer_assessments"), "semantic_evidence.answer_assessments")
            suggestions = require_object(semantic_evidence.get("option_suggestions", {}), "semantic_evidence.option_suggestions")
            date_assessments = require_object(semantic_evidence.get("date_assessments", {}), "semantic_evidence.date_assessments")
        else:
            assessments, extracted, suggestions, date_assessments = {}, {}, {}, {}

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
            if "role" in item or "criterion" in item:
                explicit = {"role": item.get("role"), "criterion": item.get("criterion"),
                            "relevance": item.get("relevance", 0.0),
                            "reason": item.get("reason", "Defined by the leader")}
                inferred = validate_sparse_question_assessment(explicit, path)
                source = "leader"
            elif qid in assessments:
                inferred = validate_sparse_question_assessment(assessments[qid], f"semantic.questions.{qid}")
                source = "model"
            elif semantic_provider is not None:
                if not hasattr(semantic_provider, "classify_question"):
                    raise SemanticServiceError("Sparse questions require classify_question on the semantic provider")
                assessments[qid] = semantic_provider.classify_question({"label": label, "choices": choices}, context)
                inferred = validate_sparse_question_assessment(assessments[qid], f"semantic.questions.{qid}")
                source = "model"
            else:
                inferred = _local_question(label)
                source = "rules"
                if inferred is None:
                    inferred = {"role": "unclassified", "criterion": "unclassified", "relevance": 0.0, "reason": "Question role needs review"}
                    issues.append(_issue("UNKNOWN_QUESTION_ROLE", path, "Question needs classification"))
                    source = "unclassified"
            weight = item.get("leader_weight")
            if weight is not None and (isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight < 0):
                raise InputError("INVALID_WEIGHT", f"{path}.leader_weight", "Weight must be finite and nonnegative")
            if weight is not None and inferred["role"] != "soft":
                raise InputError("HARD_WEIGHT_UNSUPPORTED", path, "Only soft questions can carry a weight")
            questions.append({"question_id": qid, "label": label, "choices": choices, "role": inferred["role"],
                              "criterion": inferred["criterion"], "relevance": inferred["relevance"],
                              "reason": inferred["reason"], "inference_source": source,
                              "leader_weight": weight, "required": item.get("required", inferred["role"] != "informational")})
            if type(questions[-1]["required"]) is not bool:
                raise InputError("INVALID_TYPE", f"{path}.required", "Expected true or false")
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

        members = {}
        for i, raw in enumerate(require_list(responses.get("participants"), "responses.participants")):
            member = require_object(raw, f"responses.participants[{i}]")
            member_id = require_text(member.get("participant_id"), f"responses.participants[{i}].participant_id")
            if member_id in members:
                raise InputError("DUPLICATE_ID", "responses.participants", "Duplicate participant ID")
            members[member_id] = member
        if set(members) != set(roster):
            issues.append(_issue("ROSTER_MISMATCH", "responses.participants", "Response roster differs from approved roster"))
        constraints, preferences, informational, unclassified_answers = [], [], [], []
        for member_id in roster:
            member = members.get(member_id)
            if member is None:
                continue
            if member.get("response_status") != "complete":
                issues.append(_issue("INCOMPLETE_RESPONSE", f"responses.participants.{member_id}", "Response is not complete"))
            answers = {}
            for ai, raw in enumerate(require_list(member.get("answers"), f"responses.participants.{member_id}.answers")):
                answer = require_object(raw, f"responses.participants.{member_id}.answers[{ai}]")
                qid = require_text(answer.get("question_id"), "responses.answers.question_id")
                if qid not in ids or qid in answers:
                    raise InputError("INVALID_ANSWER", f"responses.participants.{member_id}.answers[{ai}]", "Unknown or repeated question ID")
                answers[qid] = answer.get("value")
            for q in questions:
                qid = q["question_id"]
                path = f"responses.participants.{member_id}.answers.{qid}"
                if qid not in answers:
                    if q["required"]:
                        issues.append(_issue("MISSING_ANSWER", path, "Required question was not answered"))
                    continue
                value = answers[qid]
                criterion = q["criterion"]
                if criterion == "availability" and q["role"] == "hard":
                    parsed = _dates(value, path)
                    if parsed is None and isinstance(value, str):
                        saved_dates = date_assessments.get(member_id, {}).get(qid) if isinstance(date_assessments.get(member_id, {}), dict) else None
                        if saved_dates is None and semantic_provider is not None and hasattr(semantic_provider, "extract_sparse_dates"):
                            saved_dates = semantic_provider.extract_sparse_dates(q, value, context)
                            date_assessments.setdefault(member_id, {})[qid] = saved_dates
                        if saved_dates is not None:
                            date_result = validate_sparse_dates(saved_dates, value, f"semantic.dates.{member_id}.{qid}")
                            if date_result["status"] == "resolved":
                                parsed = date_result["intervals"]
                    if parsed is None:
                        issues.append(_issue("AMBIGUOUS_AVAILABILITY", path, "Provide exact dates or date intervals"))
                    else:
                        constraints.append({"participant_id": member_id, "question_id": qid, "criterion": criterion, "value": parsed})
                    continue
                answer_text = _answer_text(value, q, path)
                if criterion == "max_cost" and q["role"] == "hard":
                    parsed = _budget(answer_text, currency)
                    if parsed is None:
                        issues.append(_issue("AMBIGUOUS_BUDGET", path, "Provide a numeric budget or unlimited"))
                    else:
                        constraints.append({"participant_id": member_id, "question_id": qid, "criterion": criterion, "value": parsed})
                    continue
                if criterion == "duration_days" and q["role"] == "soft":
                    parsed = _duration(answer_text)
                    if parsed is None:
                        issues.append(_issue("AMBIGUOUS_DURATION", path, "Provide a number of days or no preference"))
                    else:
                        preferences.append({"participant_id": member_id, "question_id": qid, "criterion": criterion, "value": parsed, "evidence": answer_text})
                    continue
                if q["role"] == "informational":
                    informational.append({"participant_id": member_id, "question_id": qid, "value": answer_text})
                    continue
                if q["role"] == "unclassified":
                    unclassified_answers.append({"participant_id": member_id, "question_id": qid, "value": answer_text})
                    continue
                if answer_text.casefold().strip() in NO_PREFERENCE and q["role"] == "soft":
                    preferences.append({"participant_id": member_id, "question_id": qid, "criterion": criterion, "value": {"kind": "indifferent"}, "evidence": answer_text})
                    continue
                saved = extracted.get(member_id, {}).get(qid) if isinstance(extracted.get(member_id, {}), dict) else None
                if saved is None and semantic_provider is not None:
                    if not hasattr(semantic_provider, "extract_sparse_answer"):
                        raise SemanticServiceError("Sparse answers require extract_sparse_answer on the semantic provider")
                    saved = semantic_provider.extract_sparse_answer(q, answer_text, context)
                    extracted.setdefault(member_id, {})[qid] = saved
                if saved is None:
                    issues.append(_issue("SEMANTIC_PROVIDER_REQUIRED", path, "Open answer needs semantic extraction"))
                    continue
                result = validate_sparse_answer_assessment(saved, answer_text, f"semantic.answers.{member_id}.{qid}", criterion)
                if result["status"] == "unresolved" or not result["interpretations"]:
                    issues.append(_issue("AMBIGUOUS_ANSWER", path, "Open answer needs clarification"))
                    continue
                for interpretation in result["interpretations"]:
                    entry = {"participant_id": member_id, "question_id": qid, **interpretation}
                    if interpretation["must_have"] or q["role"] == "hard":
                        entry["status"] = "needs_confirmation"
                        issues.append(_issue("CONFIRM_REQUIREMENT", path, "Confirm whether this is a hard requirement"))
                        constraints.append(entry)
                    else:
                        preferences.append(entry)

        has_schedule_questions = {"availability", "duration_days"} <= {q["criterion"] for q in questions}
        scenario_requests = _scenario_requests(candidates, roster, constraints, preferences, questions) if has_schedule_questions else []
        scenario_criteria = {"availability", "duration_days", "max_cost"} if has_schedule_questions else set()
        criteria = sorted({q["criterion"] for q in questions if q["role"] in {"hard", "soft"} and q["criterion"] not in scenario_criteria} |
                          {p["criterion"] for p in preferences if p["criterion"] not in scenario_criteria})
        for candidate in candidates:
            known = {f["criterion"] for f in candidate["facts"]}
            candidate["missing_criteria"] = [c for c in criteria if c not in known]
            option_id = candidate["option_id"]
            requested = sorted({q["criterion"] for q in questions if q["role"] == "soft" and q["criterion"] not in scenario_criteria})
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
        if any(q["criterion"] == "max_cost" for q in questions) and currency is None:
            issues.append(_issue("MISSING_CURRENCY", "planning.currency", "Specify the budget currency"))
        if any(q["criterion"] == "max_cost" for q in questions) and context["cost_scope"] is None:
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
        if assessments or extracted or suggestions or date_assessments or semantic_evidence is not None:
            frozen = semantic_evidence or {"option_snapshot_id": option_snapshot_id, "response_snapshot_id": response_snapshot_id,
                                           "processing_version": VERSION, "model": getattr(semantic_provider, "model", None),
                                           "question_assessments": assessments, "answer_assessments": extracted,
                                           "option_suggestions": suggestions, "date_assessments": date_assessments}
        artifact_id = hashlib.sha256(json.dumps(frozen, sort_keys=True, ensure_ascii=False).encode()).hexdigest() if frozen else None
        handoff = {"context": {"schema_version": VERSION, "round_id": round_id, "option_revision": revision,
                                "option_snapshot_id": option_snapshot_id, "response_snapshot_id": response_snapshot_id,
                                "decision_question": decision, "currency": currency, "cost_scope": context["cost_scope"],
                                "details": context["details"],
                                "semantic_artifact_id": artifact_id},
                   "candidates": candidates, "scenario_requests": scenario_requests,
                   "participants": [{"participant_id": x, "response_status": members.get(x, {}).get("response_status", "incomplete")} for x in roster],
                   "constraints": constraints, "preferences": preferences, "informational_answers": informational,
                   "unclassified_answers": unclassified_answers,
                   "scoring_model": {"questions": questions, "missing_fact_policy": "unresolved"}}
        member_codes = {"ROSTER_MISMATCH", "INCOMPLETE_RESPONSE", "MISSING_ANSWER", "AMBIGUOUS_AVAILABILITY", "AMBIGUOUS_BUDGET", "AMBIGUOUS_DURATION", "AMBIGUOUS_ANSWER", "CONFIRM_REQUIREMENT"}
        status = "needs_clarification" if any(i["code"] in member_codes for i in issues) else "provisional" if issues else "ready"
        return {"status": status, "issues": issues, "algorithm_input": handoff, "semantic_evidence": frozen}
    except InputError as exc:
        return {"status": "invalid_input", "issues": [exc.as_issue()], "algorithm_input": None}
    except SemanticServiceError as exc:
        return {"status": "upstream_unavailable", "issues": [_issue("SEMANTIC_SERVICE_UNAVAILABLE", "semantic_provider", str(exc))], "algorithm_input": None}
