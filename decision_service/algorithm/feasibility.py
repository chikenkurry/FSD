from __future__ import annotations

from typing import Any

from decision_service.contract import candidate_fact, timestamp

from .models import CandidateResult, Feasibility


def evaluate_candidate(
    candidate: dict[str, Any],
    participant_ids: set[str],
    constraints: dict[str, dict[str, Any]],
) -> CandidateResult:
    failures: list[str] = []
    unresolved: list[str] = []
    start, end = timestamp(candidate["start_at"]), timestamp(candidate["end_at"])
    for participant_id in participant_ids:
        constraint = constraints[participant_id]
        intervals = constraint["availability"]["available_intervals"]
        if not any(timestamp(x["start_at"]) <= start and end <= timestamp(x["end_at"]) for x in intervals):
            failures.append("NO_TIME_OVERLAP")
        budget = constraint["budget"]
        if budget.get("kind") == "missing":
            unresolved.append("MISSING_BUDGET")
        elif budget.get("kind") == "limited":
            cost = candidate_fact(candidate, "estimated_cost")
            if cost["status"] == "unknown":
                unresolved.append("MISSING_COST")
            elif cost["status"] == "estimated":
                unresolved.append("ESTIMATED_COST")
            elif cost["value"] > budget["max_cost_minor"]:
                failures.append("BUDGET_CONFLICT")
        for requirement in constraint["required_attributes"]:
            fact = candidate_fact(candidate, requirement["attribute_id"])
            if fact is None or fact["status"] != "confirmed":
                unresolved.append("MISSING_OPTION_FACT")
            elif fact["value"] != requirement["required_value"]:
                failures.append("REQUIRED_ATTRIBUTE_NOT_MET")
        for flag in constraint["candidate_flags"]:
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
