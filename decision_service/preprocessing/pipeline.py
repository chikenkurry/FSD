"""Validate frozen snapshots and prepare the matching algorithm's input."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from decision_service.contract import (
    ContractError, MISSING_VALUE_POLICY, SCHEMA_VERSION,
    group_objective, ranking_order, validate_handoff,
)

from .candidates import generate_candidates
from .common import (
    InputError,
    issue as _issue,
    require_in,
    require_instant,
    require_int,
    require_list,
    require_object,
    require_text,
    utc_string,
)
from .extractors import ATTRIBUTE_PHRASES, extract_budget, extract_preference, extract_requirement
from .normalization import (
    execution_candidates, normalize_semantic, preference_metadata,
    provenance, requirement_metadata, semantic_binding,
)
from .semantics import (
    SemanticProvider,
    SemanticServiceError,
    answer_as_text,
    validate_answer_assessment,
    validate_question_assessment,
)
from .sparse import preprocess_sparse
from .money import validate_minor_digits
from .weights import SOFT_KINDS, resolve_weights


QUESTION_KINDS = {
    "availability", "budget", "activity_rating", "candidate_flag",
    "open_requirement", "open_preference", "open_budget",
    "semantic_preference", "semantic_requirement",
}
REQUIRED_STATUSES = {"complete", "incomplete", "stale", "needs_clarification"}
PROCESSING_VERSION = "semantic-v6"
WEIGHT_POLICY_VERSION = "goal-option-relevance-v2"


def _intervals(value: Any, path: str) -> list[dict[str, str]]:
    pairs = []
    for i, raw_interval in enumerate(require_list(value, path)):
        item_path = f"{path}[{i}]"
        interval = require_object(raw_interval, item_path)
        start = require_instant(interval.get("start_at"), f"{item_path}.start_at")
        end = require_instant(interval.get("end_at"), f"{item_path}.end_at")
        if start >= end:
            raise InputError("INVALID_TIME", item_path, "Interval end must follow start")
        pairs.append((start, end))
    pairs.sort(key=lambda pair: pair[0])
    merged = []
    for start, end in pairs:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return [{"start_at": utc_string(start), "end_at": utc_string(end)} for start, end in merged]


def _budget(value: Any, currency: str, path: str) -> dict:
    raw = require_object(value, path)
    kind = require_in(raw.get("kind"), {"limited", "unlimited", "missing"}, f"{path}.kind")
    if kind == "limited":
        amount = require_int(raw.get("max_cost_minor"), f"{path}.max_cost_minor")
        answer_currency = require_text(raw.get("currency"), f"{path}.currency").upper()
        if answer_currency != currency:
            raise InputError("CURRENCY_MISMATCH", path, "Budget and plan currencies differ")
        return {"kind": "limited", "max_cost_minor": amount, "currency": currency}
    return {"kind": kind}


def _questions(raw_questions: Any) -> list[dict]:
    questions = []
    ids: set[str] = set()
    for i, raw_question in enumerate(require_list(raw_questions, "planning.questions")):
        path = f"planning.questions[{i}]"
        q = require_object(raw_question, path)
        question_id = require_text(q.get("question_id"), f"{path}.question_id")
        if question_id in ids:
            raise InputError("DUPLICATE_ID", f"{path}.question_id", "Duplicate question ID")
        ids.add(question_id)
        kind = require_in(q.get("kind"), QUESTION_KINDS, f"{path}.kind")
        allowed = require_list(q.get("supported_attributes", []), f"{path}.supported_attributes")
        if kind in {"open_requirement", "open_preference"}:
            if not allowed:
                raise InputError("MISSING_MAPPING", path, "Open attribute questions need supported_attributes")
            for attr in allowed:
                if not isinstance(attr, str) or attr not in ATTRIBUTE_PHRASES:
                    raise InputError("UNSUPPORTED_CRITERION", path, f"Unsupported attribute {attr}")
            if len(set(allowed)) != len(allowed):
                raise InputError("DUPLICATE_ID", path, "Duplicate supported attribute")
        required = q.get("required", kind not in {"open_requirement", "candidate_flag"})
        if type(required) is not bool:
            raise InputError("INVALID_TYPE", f"{path}.required", "Expected true or false")
        if kind in {"activity_rating", "open_preference"} and not required:
            raise InputError("UNSUPPORTED_POLICY", path, "Soft questions must require an explicit answer in v1")
        if kind in {"semantic_preference", "semantic_requirement"} and not required:
            raise InputError("UNSUPPORTED_POLICY", path, "Semantic questions must require an explicit answer in v1")
        if kind not in {"activity_rating", "open_preference", "semantic_preference"} and q.get("leader_weight") is not None:
            raise InputError("HARD_WEIGHT_UNSUPPORTED", path, "Hard questions are mandatory checks and cannot carry a score weight")
        answer_format = q.get("answer_format", "text")
        choices = {}
        if kind in {"semantic_preference", "semantic_requirement"}:
            answer_format = require_in(answer_format, {"text", "choice"}, f"{path}.answer_format")
            if answer_format == "choice":
                for ci, raw_choice in enumerate(require_list(q.get("choices"), f"{path}.choices")):
                    choice_path = f"{path}.choices[{ci}]"
                    choice = require_object(raw_choice, choice_path)
                    choice_id = require_text(choice.get("choice_id"), f"{choice_path}.choice_id")
                    if choice_id in choices:
                        raise InputError("DUPLICATE_ID", choice_path, "Duplicate choice ID")
                    choices[choice_id] = require_text(choice.get("label"), f"{choice_path}.label")
                if not choices:
                    raise InputError("MISSING_MAPPING", path, "Choice question needs choices")
        questions.append({
            "question_id": question_id,
            "label": require_text(q.get("label"), f"{path}.label"),
            "kind": kind,
            "required": required,
            "supported_attributes": allowed,
            "leader_weight": q.get("leader_weight"),
            "answer_format": answer_format,
            "choices": choices,
            "semantic_binding": semantic_binding(q.get("semantic_binding"), f"{path}.semantic_binding"),
        })
    return questions


def _process_member(
    member_id: str,
    member: dict,
    questions: list[dict],
    candidates: list[dict],
    activity_ids: set[str],
    currency: str,
    issues: list[dict],
    minor_digits: int = 2,
) -> tuple[dict, list[dict], dict[str, str]]:
    member_path = f"responses.participants.{member_id}"
    answers = {}
    question_ids = {q["question_id"] for q in questions}
    for i, raw_answer in enumerate(require_list(member.get("answers"), f"{member_path}.answers")):
        path = f"{member_path}.answers[{i}]"
        answer = require_object(raw_answer, path)
        question_id = require_text(answer.get("question_id"), f"{path}.question_id")
        require_text(answer.get("answer_id"), f"{path}.answer_id")
        if question_id not in question_ids:
            raise InputError("UNKNOWN_QUESTION", path, "Answer references an unknown question")
        if question_id in answers:
            raise InputError("DUPLICATE_ANSWER", path, "Multiple answers for the same question")
        answers[question_id] = answer

    constraint = {
        "participant_id": member_id,
        "availability": {"available_intervals": []},
        "budget": {"kind": "missing"},
        "required_attributes": [],
        "candidate_flags": [],
        "answer_sources": [],
    }
    preferences = []
    semantic_answers: dict[str, str] = {}
    budget_values: list[dict] = []
    flagged_activities: dict[str, tuple[str, str]] = {}
    for q in questions:
        if q["kind"] != "candidate_flag" or q["question_id"] not in answers:
            continue
        path = f"{member_path}.answers.{q['question_id']}"
        for i, raw_flag in enumerate(require_list(answers[q["question_id"]].get("value"), path)):
            flag_path = f"{path}[{i}]"
            flag = require_object(raw_flag, flag_path)
            activity_id = require_text(flag.get("activity_id"), f"{flag_path}.activity_id")
            if activity_id not in activity_ids:
                raise InputError("UNKNOWN_ACTIVITY", flag_path, "Flag references an unknown activity")
            flag_value = require_in(flag.get("flag"), {"cannot_join", "needs_information"}, f"{flag_path}.flag")
            if activity_id in flagged_activities and flagged_activities[activity_id][0] != flag_value:
                issues.append(_issue("CONFLICTING_ANSWER", flag_path, "Activity has conflicting flags"))
            flagged_activities[activity_id] = (flag_value, q["question_id"])
    for candidate in candidates:
        if candidate["activity_id"] in flagged_activities:
            constraint["candidate_flags"].append({
                "candidate_id": candidate["candidate_id"],
                "flag": flagged_activities[candidate["activity_id"]][0],
                **provenance(answers[flagged_activities[candidate["activity_id"]][1]]),
            })

    for q in questions:
        question_id = q["question_id"]
        kind = q["kind"]
        answer = answers.get(question_id)
        path = f"{member_path}.answers.{question_id}"
        if answer is None:
            if q["required"] and not (kind == "activity_rating" and set(flagged_activities) == activity_ids):
                issues.append(_issue("MISSING_ANSWER", path, "Required question was not answered"))
            continue
        value = answer.get("value")
        if kind not in SOFT_KINDS and not kind.startswith("semantic_"):
            constraint["answer_sources"].append(provenance(answer))
        try:
            if kind == "availability":
                constraint["availability"]["available_intervals"] = _intervals(value, path)
            elif kind == "budget":
                budget_values.append(_budget(value, currency, path))
            elif kind == "open_budget":
                budget_values.append(extract_budget(require_text(value, path), currency, minor_digits=minor_digits))
            elif kind == "open_requirement":
                extracted = extract_requirement(require_text(value, path), set(q["supported_attributes"]))
                for requirement in extracted:
                    requirement = requirement_metadata(requirement, member_id, answer)
                    existing = next((r for r in constraint["required_attributes"] if r["attribute_id"] == requirement["attribute_id"]), None)
                    if existing and existing["required_value"] != requirement["required_value"]:
                        issues.append(_issue("CONFLICTING_ANSWER", path, "Requirements conflict"))
                    else:
                        constraint["required_attributes"].append(requirement)
            elif kind == "open_preference":
                for extracted in extract_preference(require_text(value, path), set(q["supported_attributes"])):
                    preferences.append(preference_metadata({"participant_id": member_id, **extracted}, answer))
            elif kind == "activity_rating":
                ratings = require_object(value, path)
                unanswered = activity_ids - set(ratings) - set(flagged_activities)
                if unanswered:
                    issues.append(_issue("INCOMPLETE_RATINGS", path, "Rate every activity or use an explicit flag"))
                for activity_id, raw_rating in ratings.items():
                    if activity_id not in activity_ids:
                        raise InputError("UNKNOWN_ACTIVITY", path, "Rating references an unknown activity")
                    if activity_id in flagged_activities:
                        issues.append(_issue("CONFLICTING_ANSWER", path, "Activity has both a rating and a flag"))
                    if raw_rating == "no_preference":
                        preferences.append(preference_metadata({"participant_id": member_id, "activity_id": activity_id,
                                                               "kind": "indifferent", "utility_rule": "neutral_v1"}, answer))
                        continue
                    rating = require_int(raw_rating, f"{path}.{activity_id}")
                    if rating > 4:
                        raise InputError("INVALID_RATING", f"{path}.{activity_id}", "Rating must be 0 to 4")
                    preferences.append(preference_metadata({"participant_id": member_id, "activity_id": activity_id,
                                                           "rating": rating, "kind": "rating"}, answer))
            elif kind == "candidate_flag":
                pass  # Flags were processed before ratings, regardless of question order.
            elif kind in {"semantic_preference", "semantic_requirement"}:
                semantic_answers[question_id] = answer_as_text(q, value, path)
        except InputError as exc:
            if exc.code in {"AMBIGUOUS_ANSWER", "AMBIGUOUS_BUDGET", "UNIT_MISMATCH", "UNSUPPORTED_ANSWER", "CONFLICTING_ANSWER"}:
                issues.append(_issue(exc.code, path, exc.message))
            else:
                raise

    usable_budgets = [b for b in budget_values if b["kind"] != "missing"]
    if usable_budgets and any(b != usable_budgets[0] for b in usable_budgets[1:]):
        issues.append(_issue("CONFLICTING_ANSWER", member_path, "Budget answers conflict"))
    if usable_budgets:
        constraint["budget"] = usable_budgets[0]
    else:
        issues.append(_issue("MISSING_BUDGET", member_path, "No usable budget answer"))
    return constraint, preferences, semantic_answers


def preprocess(
    planning_snapshot: dict,
    response_snapshot: dict,
    policy: dict | None = None,
    semantic_provider: SemanticProvider | None = None,
    semantic_evidence: dict | None = None,
) -> dict:
    """Return status/issues and, when ready, a DecisionAlgorithmInput.

    A supplied semantic provider may call a model for generic questions.
    Persist returned semantic_evidence and reuse it on retries.
    """
    if isinstance(planning_snapshot, dict) and "options" in planning_snapshot and "activities" not in planning_snapshot:
        return preprocess_sparse(planning_snapshot, response_snapshot, semantic_provider, semantic_evidence, policy=policy)
    issues: list[dict] = []
    try:
        planning = require_object(planning_snapshot, "planning")
        responses = require_object(response_snapshot, "responses")
        policy = require_object({} if policy is None else policy, "policy")
        objective = group_objective(policy.get("group_objective"))
        round_id = require_text(planning.get("round_id"), "planning.round_id")
        option_revision = require_text(planning.get("option_revision"), "planning.option_revision")
        option_snapshot_id = require_text(planning.get("option_snapshot_id"), "planning.option_snapshot_id")
        response_snapshot_id = require_text(responses.get("response_snapshot_id"), "responses.response_snapshot_id")
        if responses.get("round_id") != round_id or responses.get("option_revision") != option_revision:
            raise InputError("STALE_SNAPSHOT", "responses", "Response round or option revision does not match planning")
        timezone_name = require_text(planning.get("timezone"), "planning.timezone")
        currency = require_text(planning.get("currency"), "planning.currency").upper()
        minor_digits = validate_minor_digits(planning.get("currency_minor_digits", 2), "planning.currency_minor_digits")
        questions = _questions(planning.get("questions"))
        if sum(q["kind"] == "availability" for q in questions) != 1:
            raise InputError("INVALID_QUESTION_CONFIG", "planning.questions", "Exactly one availability question is required")
        if not any(q["kind"] in {"budget", "open_budget"} for q in questions):
            raise InputError("MISSING_QUESTION", "planning.questions", "Budget question is required")
        activities = require_list(planning.get("activities"), "planning.activities")
        candidates = generate_candidates(activities, option_revision, timezone_name)
        model_questions = [q for q in questions if q["kind"].startswith("semantic_") or (semantic_provider is not None and q["kind"] in SOFT_KINDS and q["leader_weight"] is None)]
        if model_questions and len(candidates) > 100:
            raise InputError("LIMIT_EXCEEDED", "planning.activities", "Model-assisted questions support at most 100 candidates per run")
        activity_ids = {a["activity_id"] for a in activities}
        if any(require_text(a.get("currency"), "planning.activities.currency").upper() != currency for a in activities):
            raise InputError("CURRENCY_MISMATCH", "planning.activities", "Activity and plan currencies differ")

        roster = [require_text(member_id, "planning.roster") for member_id in require_list(planning.get("roster"), "planning.roster")]
        if not roster or len(roster) != len(set(roster)):
            raise InputError("INVALID_ROSTER", "planning.roster", "Roster must contain unique member IDs")
        response_by_id = {}
        for i, raw_member in enumerate(require_list(responses.get("participants"), "responses.participants")):
            member = require_object(raw_member, f"responses.participants[{i}]")
            member_id = require_text(member.get("participant_id"), f"responses.participants[{i}].participant_id")
            if member_id in response_by_id:
                raise InputError("DUPLICATE_ID", "responses.participants", "Duplicate participant ID")
            response_by_id[member_id] = member
        if set(response_by_id) != set(roster):
            issues.append(_issue("ROSTER_MISMATCH", "responses.participants", "Response roster differs from approved roster"))

        participants = []
        constraints = []
        preferences = []
        semantic_answers: dict[tuple[str, str], str] = {}
        for member_id in roster:
            member = response_by_id.get(member_id)
            if member is None:
                participants.append({"participant_id": member_id, "response_status": "incomplete", "is_required_for_decision": True})
                continue
            status = require_in(member.get("response_status"), REQUIRED_STATUSES, f"responses.participants.{member_id}.response_status")
            participants.append({"participant_id": member_id, "response_status": status, "is_required_for_decision": True})
            if status != "complete":
                issues.append(_issue("INCOMPLETE_RESPONSE", f"responses.participants.{member_id}", "Participant response is not complete and current"))
            constraint, member_preferences, member_semantic = _process_member(
                member_id, member, questions, candidates, activity_ids, currency, issues, minor_digits)
            constraints.append(constraint)
            preferences.extend(member_preferences)
            semantic_answers.update({(member_id, qid): answer for qid, answer in member_semantic.items()})

        if issues:
            return {"status": "needs_clarification", "issues": issues, "algorithm_input": None}
        semantic_questions = [q for q in questions if q["kind"].startswith("semantic_")]
        if semantic_questions and semantic_provider is None and semantic_evidence is None:
            return {"status": "needs_clarification", "issues": [_issue("SEMANTIC_PROVIDER_REQUIRED", "planning.questions", "Generic semantic questions need a configured model provider")], "algorithm_input": None}
        if semantic_evidence is not None:
            semantic_evidence = require_object(semantic_evidence, "semantic_evidence")
            if semantic_evidence.get("option_snapshot_id") != option_snapshot_id or semantic_evidence.get("response_snapshot_id") != response_snapshot_id or semantic_evidence.get("processing_version") != PROCESSING_VERSION:
                raise InputError("STALE_SEMANTIC_EVIDENCE", "semantic_evidence", "Semantic evidence does not match the input snapshots or processing version")
            saved_questions = require_object(semantic_evidence.get("question_assessments"), "semantic_evidence.question_assessments")
            saved_answers = require_object(semantic_evidence.get("answer_assessments"), "semantic_evidence.answer_assessments")
        else:
            saved_questions = {}
            saved_answers = {}
        decision_question = planning.get("decision_question")
        if decision_question is not None:
            decision_question = require_text(decision_question, "planning.decision_question")
        else:
            decision_question = planning.get("plan_description") or planning.get("plan_title") or "Choose the best activity and time for this group"
        semantic_context = {
            "decision_question": decision_question,
            "plan_title": planning.get("plan_title", ""),
            "plan_description": planning.get("plan_description", ""),
            "timezone": timezone_name,
            "currency": currency,
        }
        if not isinstance(semantic_context["decision_question"], str) or not semantic_context["decision_question"].strip():
            raise InputError("INVALID_DECISION_QUESTION", "planning.decision_question", "Decision question must be nonempty text")
        # With a model, missing leader weights are assessed against the plan goal
        # even for structured and controlled-vocabulary questions. Without one,
        # the deterministic option-relevance baseline remains available.
        model_weight_questions = [q for q in questions if q["kind"] in SOFT_KINDS and q["leader_weight"] is None]
        if semantic_evidence is not None:
            assessed_ids = set(saved_questions)
            allowed_ids = {q["question_id"] for q in semantic_questions + model_weight_questions}
            required_ids = {q["question_id"] for q in semantic_questions} if candidates else set()
            if not required_ids <= assessed_ids or not assessed_ids <= allowed_ids:
                raise InputError("INVALID_SEMANTIC_EVIDENCE", "semantic_evidence.question_assessments", "Evidence question IDs differ from this run")
            assessed_questions = [q for q in questions if q["question_id"] in assessed_ids]
        elif semantic_provider is not None:
            assessed_ids = {q["question_id"] for q in semantic_questions + model_weight_questions}
            assessed_questions = [q for q in questions if q["question_id"] in assessed_ids]
        else:
            assessed_questions = []
        interpretations = []
        for question in assessed_questions:
            if candidates:
                if semantic_evidence is None:
                    saved_questions[question["question_id"]] = semantic_provider.assess_question(question, semantic_context, candidates)
                assessed = validate_question_assessment(saved_questions.get(question["question_id"]), f"semantic.questions.{question['question_id']}")
                question["semantic_relevance"] = assessed["relevance"]
                question["semantic_criterion"] = assessed["criterion"]
                question["semantic_relevance_reason"] = assessed["reason"]
            else:
                question["semantic_relevance"] = 0.0
                question["semantic_criterion"] = question["label"]
        for question in semantic_questions:
            for member_id in roster:
                answer_text = semantic_answers[(member_id, question["question_id"])]
                if semantic_evidence is None:
                    saved_answers.setdefault(member_id, {})[question["question_id"]] = semantic_provider.extract_answer(question, answer_text, semantic_context)
                member_evidence = require_object(saved_answers.get(member_id), f"semantic_evidence.answer_assessments.{member_id}")
                response = member_evidence.get(question["question_id"])
                interpretation = validate_answer_assessment(response, answer_text, f"semantic.answers.{member_id}.{question['question_id']}")
                if interpretation["status"] == "unresolved":
                    issues.append(_issue("AMBIGUOUS_ANSWER", f"responses.participants.{member_id}.answers.{question['question_id']}", "Semantic answer needs clarification"))
                else:
                    answer = next(a for a in response_by_id[member_id]["answers"] if a["question_id"] == question["question_id"])
                    try:
                        preference, requirement = normalize_semantic(question, interpretation, member_id, answer)
                        if preference is not None:
                            preferences.append(preference)
                        if requirement is not None:
                            next(c for c in constraints if c["participant_id"] == member_id)["required_attributes"].append(requirement)
                    except InputError as exc:
                        issues.append(exc.as_issue())
                interpretations.append({"participant_id": member_id, "question_id": question["question_id"], "kind": question["kind"], **interpretation})

        if semantic_evidence is not None:
            expected_question_ids = {q["question_id"] for q in semantic_questions}
            if set(saved_answers) != (set(roster) if semantic_questions else set()):
                raise InputError("INVALID_SEMANTIC_EVIDENCE", "semantic_evidence", "Evidence question or member IDs differ from this run")
            if semantic_questions:
                for member_id in roster:
                    if set(saved_answers[member_id]) != expected_question_ids:
                        raise InputError("INVALID_SEMANTIC_EVIDENCE", f"semantic_evidence.answer_assessments.{member_id}", "Evidence question IDs differ from this run")

        frozen_evidence = None
        artifact_id = None
        if semantic_questions or assessed_questions:
            frozen_evidence = semantic_evidence or {
                "option_snapshot_id": option_snapshot_id,
                "response_snapshot_id": response_snapshot_id,
                "processing_version": PROCESSING_VERSION,
                "model": getattr(semantic_provider, "model", None),
                "question_assessments": saved_questions,
                "answer_assessments": saved_answers,
            }
            canonical = json.dumps(frozen_evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            artifact_id = hashlib.sha256(canonical).hexdigest()

        if issues:
            return {"status": "needs_clarification", "issues": issues, "algorithm_input": None,
                    "semantic_evidence": frozen_evidence, "semantic_interpretations": interpretations}

        scoring_questions = resolve_weights(questions, candidates)
        for scoring_question in scoring_questions:
            original = next(q for q in questions if q["question_id"] == scoring_question["question_id"])
            binding = original["semantic_binding"]
            scoring_question["criteria"] = [binding["attribute_id"]] if binding else original["supported_attributes"]
            if "semantic_criterion" in original:
                scoring_question["criterion"] = original["semantic_criterion"]
                scoring_question["relevance_reason"] = original.get("semantic_relevance_reason")
        prepared_candidates, criteria = execution_candidates(candidates, questions)
        algorithm_input = {
            "context": {
                "schema_version": SCHEMA_VERSION,
                "activity_ids": sorted(activity_ids),
                "round_id": round_id,
                "option_snapshot_id": option_snapshot_id,
                "response_snapshot_id": response_snapshot_id,
                "timezone": timezone_name,
                "algorithm_version": require_text(policy.get("algorithm_version", "baseline-v2"), "policy.algorithm_version"),
                "policy_version": require_text(policy.get("policy_version", WEIGHT_POLICY_VERSION), "policy.policy_version"),
                "processing_version": PROCESSING_VERSION,
                "semantic_model": frozen_evidence.get("model") if frozen_evidence else None,
                "semantic_artifact_id": artifact_id,
            },
            "candidates": prepared_candidates,
            "criteria": criteria,
            "participants": participants,
            "constraints": constraints,
            "preferences": preferences,
            "scoring_model": {
                "questions": scoring_questions,
                "group_objective": objective,
                "ranking_policy": {
                    "feasibility_policy": "all_required_participants",
                    "sort_order": ranking_order(objective),
                },
                "missing_value_policy": dict(MISSING_VALUE_POLICY),
            },
        }
        if "currency_minor_digits" in planning:
            algorithm_input["context"]["currency_minor_digits"] = minor_digits
        validate_handoff(algorithm_input)
        return {"status": "ready", "issues": [], "algorithm_input": algorithm_input,
                "semantic_evidence": frozen_evidence, "semantic_interpretations": interpretations}
    except InputError as exc:
        return {"status": "invalid_input", "issues": [exc.as_issue()], "algorithm_input": None}
    except ContractError as exc:
        return {"status": "invalid_input", "issues": [_issue("INVALID_HANDOFF", "algorithm_input", str(exc))], "algorithm_input": None}
    except SemanticServiceError as exc:
        return {"status": "upstream_unavailable", "issues": [_issue("SEMANTIC_SERVICE_UNAVAILABLE", "semantic_provider", str(exc))], "algorithm_input": None}
