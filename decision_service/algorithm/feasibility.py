from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import CandidateResult, Feasibility


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def evaluate_candidate(candidate: dict[str, Any], participant_ids: set[str], constraints: dict[str, dict[str, Any]]) -> CandidateResult:
    failures: list[str] = []
    unresolved: list[str] = []
    start, end = _time(candidate["start_at"]), _time(candidate["end_at"])
    attributes = {a["attribute_id"]: a.get("value", "unknown") for a in candidate.get("attributes", [])}
    for participant_id in participant_ids:
        constraint = constraints.get(participant_id)
        if constraint is None:
            unresolved.append("INCOMPLETE_RESPONSE")
            continue
        intervals = constraint.get("availability", {}).get("available_intervals", [])
        if not any(_time(x["start_at"]) <= start and end <= _time(x["end_at"]) for x in intervals):
            failures.append("NO_TIME_OVERLAP")
        budget = constraint.get("budget", {"kind": "missing"})
        if budget.get("kind") == "missing":
            unresolved.append("MISSING_BUDGET")
        elif budget.get("kind") == "limited":
            cost = candidate.get("estimated_cost_minor")
            if cost is None:
                unresolved.append("MISSING_COST")
            elif cost > budget.get("max_cost_minor", -1):
                failures.append("BUDGET_CONFLICT")
        for requirement in constraint.get("required_attributes", []):
            actual = attributes.get(requirement["attribute_id"], "unknown")
            if actual == "unknown":
                unresolved.append("MISSING_OPTION_FACT")
            elif actual != requirement["required_value"]:
                failures.append("REQUIRED_ATTRIBUTE_NOT_MET")
        for flag in constraint.get("candidate_flags", []):
            if flag["candidate_id"] != candidate["candidate_id"]:
                continue
            if flag["flag"] == "cannot_join":
                failures.append("CANNOT_JOIN")
            elif flag["flag"] == "needs_information":
                unresolved.append("NEEDS_INFORMATION")
    codes = tuple(sorted(set(failures + unresolved)))
    if failures:
        state = Feasibility.INFEASIBLE
    elif unresolved:
        state = Feasibility.UNRESOLVED
    else:
        state = Feasibility.FEASIBLE
    return CandidateResult(candidate["candidate_id"], state, codes)
