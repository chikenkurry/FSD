"""Compare normalized answers with each concrete decision candidate."""

from __future__ import annotations

from datetime import datetime


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _record(participant_id: str, candidate_id: str, question_id: str, state: str, fit: float | None, reason_code: str, source: str = "deterministic", evidence: str | None = None) -> dict:
    result = {
        "participant_id": participant_id,
        "candidate_id": candidate_id,
        "question_id": question_id,
        "state": state,
        "fit": fit,
        "reason_code": reason_code,
        "source": source,
    }
    if evidence is not None:
        result["evidence"] = evidence
    return result


def build_question_matches(
    questions: list[dict],
    candidates: list[dict],
    constraints: list[dict],
    preferences: list[dict],
    semantic_matches: dict[tuple[str, str, str], dict] | None = None,
) -> list[dict]:
    """Return one auditable comparison per member, candidate, and question."""
    semantic_matches = semantic_matches or {}
    by_member = {item["participant_id"]: item for item in constraints}
    grouped_preferences: dict[tuple[str, str], list[dict]] = {}
    for preference in preferences:
        grouped_preferences.setdefault((preference["participant_id"], preference["source_question_id"]), []).append(preference)

    results = []
    for participant_id, constraint in by_member.items():
        for candidate in candidates:
            candidate_id = candidate["candidate_id"]
            attrs = {a["attribute_id"]: a["value"] for a in candidate["attributes"]}
            for question in questions:
                question_id = question["question_id"]
                kind = question["kind"]
                key = (question_id, participant_id, candidate_id)
                if kind in {"semantic_preference", "semantic_requirement"}:
                    match = semantic_matches[key]
                    results.append(_record(participant_id, candidate_id, question_id, match["state"], match["fit"], match["reason_code"], "model", match["evidence"]))
                elif kind == "availability":
                    start, end = _instant(candidate["start_at"]), _instant(candidate["end_at"])
                    available = any(_instant(interval["start_at"]) <= start and end <= _instant(interval["end_at"]) for interval in constraint["availability"]["available_intervals"])
                    results.append(_record(participant_id, candidate_id, question_id, "pass" if available else "fail", None, "AVAILABLE" if available else "NO_TIME_OVERLAP"))
                elif kind in {"budget", "open_budget"}:
                    budget = constraint["budget"]
                    cost = candidate["estimated_cost_minor"]
                    if cost is None:
                        results.append(_record(participant_id, candidate_id, question_id, "unresolved", None, "MISSING_COST"))
                    elif budget["kind"] == "unlimited" or cost <= budget["max_cost_minor"]:
                        results.append(_record(participant_id, candidate_id, question_id, "pass", None, "BUDGET_OK"))
                    else:
                        results.append(_record(participant_id, candidate_id, question_id, "fail", None, "BUDGET_CONFLICT"))
                elif kind == "open_requirement":
                    requirements = [r for r in constraint["required_attributes"] if r["source_question_id"] == question_id]
                    values = [attrs.get(r["attribute_id"], "unknown") for r in requirements]
                    if any(value != "unknown" and value != r["required_value"] for value, r in zip(values, requirements)):
                        state, reason = "fail", "REQUIRED_ATTRIBUTE_NOT_MET"
                    elif "unknown" in values:
                        state, reason = "unresolved", "MISSING_OPTION_FACT"
                    else:
                        state, reason = "pass", "REQUIREMENT_MET"
                    results.append(_record(participant_id, candidate_id, question_id, state, None, reason))
                elif kind == "candidate_flag":
                    flags = [f["flag"] for f in constraint["candidate_flags"] if f["candidate_id"] == candidate_id and f["source_question_id"] == question_id]
                    if "cannot_join" in flags:
                        state, reason = "fail", "CANNOT_JOIN"
                    elif "needs_information" in flags:
                        state, reason = "unresolved", "NEEDS_INFORMATION"
                    else:
                        state, reason = "pass", "NO_FLAG"
                    results.append(_record(participant_id, candidate_id, question_id, state, None, reason))
                elif kind == "activity_rating":
                    rating = next((p["rating"] for p in grouped_preferences.get((participant_id, question_id), []) if p.get("activity_id") == candidate["activity_id"] and p["kind"] == "rating"), None)
                    if rating is None:
                        results.append(_record(participant_id, candidate_id, question_id, "skipped", None, "OPTION_FLAGGED"))
                    else:
                        results.append(_record(participant_id, candidate_id, question_id, "known", rating / 4, "RATING"))
                elif kind == "open_preference":
                    prefs = grouped_preferences.get((participant_id, question_id), [])
                    if any(p["kind"] == "indifferent" for p in prefs):
                        results.append(_record(participant_id, candidate_id, question_id, "known", 0.5, "NO_PREFERENCE"))
                    else:
                        values = [attrs.get(p["attribute_id"], "unknown") for p in prefs]
                        if "unknown" in values:
                            results.append(_record(participant_id, candidate_id, question_id, "unresolved", None, "MISSING_OPTION_FACT"))
                        else:
                            fit = sum(value == p["preferred_value"] for value, p in zip(values, prefs)) / len(prefs)
                            results.append(_record(participant_id, candidate_id, question_id, "known", fit, "ATTRIBUTE_PREFERENCE"))
    return results
