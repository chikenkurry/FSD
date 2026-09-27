"""Validate frozen snapshots and prepare the matching algorithm's input."""

from __future__ import annotations

from typing import Any

from .candidates import generate_candidates
from .common import (
    InputError,
    require_in,
    require_instant,
    require_int,
    require_list,
    require_object,
    require_text,
    utc_string,
)
from .extractors import ATTRIBUTE_PHRASES, extract_budget, extract_preference, extract_requirement
from .weights import resolve_weights


QUESTION_KINDS = {
    "availability", "budget", "activity_rating", "candidate_flag",
    "open_requirement", "open_preference", "open_budget",
}
REQUIRED_STATUSES = {"complete", "incomplete", "stale", "needs_clarification"}
PROCESSING_VERSION = "rules-v1"
WEIGHT_POLICY_VERSION = "equal-or-leader-v1"


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


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
        questions.append({
            "question_id": question_id,
            "label": require_text(q.get("label"), f"{path}.label"),
            "kind": kind,
            "required": required,
            "supported_attributes": allowed,
            "leader_weight": q.get("leader_weight"),
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
) -> tuple[dict, list[dict]]:
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
    }
    preferences = []
    budget_values: list[dict] = []
    flagged_activities: dict[str, str] = {}
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
            if activity_id in flagged_activities and flagged_activities[activity_id] != flag_value:
                issues.append(_issue("CONFLICTING_ANSWER", flag_path, "Activity has conflicting flags"))
            flagged_activities[activity_id] = flag_value
    for candidate in candidates:
        if candidate["activity_id"] in flagged_activities:
            constraint["candidate_flags"].append({
                "candidate_id": candidate["candidate_id"],
                "flag": flagged_activities[candidate["activity_id"]],
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
        try:
            if kind == "availability":
                constraint["availability"]["available_intervals"] = _intervals(value, path)
            elif kind == "budget":
                budget_values.append(_budget(value, currency, path))
            elif kind == "open_budget":
                budget_values.append(extract_budget(require_text(value, path), currency))
            elif kind == "open_requirement":
                extracted = extract_requirement(require_text(value, path), set(q["supported_attributes"]))
                for requirement in extracted:
                    existing = next((r for r in constraint["required_attributes"] if r["attribute_id"] == requirement["attribute_id"]), None)
                    if existing and existing["required_value"] != requirement["required_value"]:
                        issues.append(_issue("CONFLICTING_ANSWER", path, "Requirements conflict"))
                    elif not existing:
                        constraint["required_attributes"].append(requirement)
            elif kind == "open_preference":
                for extracted in extract_preference(require_text(value, path), set(q["supported_attributes"])):
                    preferences.append({"participant_id": member_id, "source_question_id": question_id, **extracted})
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
                    rating = 2 if raw_rating == "no_preference" else require_int(raw_rating, f"{path}.{activity_id}")
                    if rating > 4:
                        raise InputError("INVALID_RATING", f"{path}.{activity_id}", "Rating must be 0 to 4")
                    preferences.append({"participant_id": member_id, "activity_id": activity_id, "rating": rating, "kind": "rating", "source_question_id": question_id})
            elif kind == "candidate_flag":
                pass  # Flags were processed before ratings, regardless of question order.
        except InputError as exc:
            if exc.code in {"AMBIGUOUS_ANSWER", "UNSUPPORTED_ANSWER", "CONFLICTING_ANSWER"}:
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
    return constraint, preferences


def preprocess(planning_snapshot: dict, response_snapshot: dict, policy: dict | None = None) -> dict:
    """Return status/issues and, when ready, a DecisionAlgorithmInput.

    No network or model calls occur here. Callers can cache this result by
    snapshot IDs and processing/policy versions.
    """
    issues: list[dict] = []
    try:
        planning = require_object(planning_snapshot, "planning")
        responses = require_object(response_snapshot, "responses")
        policy = require_object(policy or {}, "policy")
        round_id = require_text(planning.get("round_id"), "planning.round_id")
        option_revision = require_text(planning.get("option_revision"), "planning.option_revision")
        option_snapshot_id = require_text(planning.get("option_snapshot_id"), "planning.option_snapshot_id")
        response_snapshot_id = require_text(responses.get("response_snapshot_id"), "responses.response_snapshot_id")
        if responses.get("round_id") != round_id or responses.get("option_revision") != option_revision:
            raise InputError("STALE_SNAPSHOT", "responses", "Response round or option revision does not match planning")
        timezone_name = require_text(planning.get("timezone"), "planning.timezone")
        currency = require_text(planning.get("currency"), "planning.currency").upper()
        questions = _questions(planning.get("questions"))
        if sum(q["kind"] == "availability" for q in questions) != 1:
            raise InputError("INVALID_QUESTION_CONFIG", "planning.questions", "Exactly one availability question is required")
        if not any(q["kind"] in {"budget", "open_budget"} for q in questions):
            raise InputError("MISSING_QUESTION", "planning.questions", "Budget question is required")
        scoring_questions = resolve_weights(questions)
        activities = require_list(planning.get("activities"), "planning.activities")
        candidates = generate_candidates(activities, option_revision, timezone_name)
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
        for member_id in roster:
            member = response_by_id.get(member_id)
            if member is None:
                participants.append({"participant_id": member_id, "response_status": "incomplete", "is_required_for_decision": True})
                continue
            status = require_in(member.get("response_status"), REQUIRED_STATUSES, f"responses.participants.{member_id}.response_status")
            participants.append({"participant_id": member_id, "response_status": status, "is_required_for_decision": True})
            if status != "complete":
                issues.append(_issue("INCOMPLETE_RESPONSE", f"responses.participants.{member_id}", "Participant response is not complete and current"))
            constraint, member_preferences = _process_member(member_id, member, questions, candidates, activity_ids, currency, issues)
            constraints.append(constraint)
            preferences.extend(member_preferences)

        if issues:
            return {"status": "needs_clarification", "issues": issues, "algorithm_input": None}
        algorithm_input = {
            "context": {
                "round_id": round_id,
                "option_snapshot_id": option_snapshot_id,
                "response_snapshot_id": response_snapshot_id,
                "timezone": timezone_name,
                "algorithm_version": require_text(policy.get("algorithm_version", "baseline-v1"), "policy.algorithm_version"),
                "policy_version": require_text(policy.get("policy_version", WEIGHT_POLICY_VERSION), "policy.policy_version"),
                "processing_version": PROCESSING_VERSION,
            },
            "candidates": candidates,
            "participants": participants,
            "constraints": constraints,
            "preferences": preferences,
            "scoring_model": {
                "questions": scoring_questions,
                "ranking_policy": {
                    "feasibility_policy": "all_required_participants",
                    "sort_order": ["highest_min_member_score", "highest_average_member_score", "lowest_estimated_cost", "earliest_start", "stable_candidate_id"],
                },
                "missing_value_policy": {
                    "missing_budget": "incomplete",
                    "missing_rating": "incomplete",
                    "missing_required_attribute": "unresolved",
                    "missing_availability": "unavailable",
                    "no_preference": "neutral",
                },
            },
        }
        return {"status": "ready", "issues": [], "algorithm_input": algorithm_input}
    except InputError as exc:
        return {"status": "invalid_input", "issues": [exc.as_issue()], "algorithm_input": None}
