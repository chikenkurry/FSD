from __future__ import annotations

from typing import Any

from .models import ParetoCandidate


def pareto_frontier(scored: list[tuple[dict[str, Any], float, float, float, float]]) -> tuple[ParetoCandidate, ...]:
    result = []
    for candidate, minimum, average, _group_score, _penalty in scored:
        cost = candidate.get("estimated_cost_minor")
        cost_value = cost if cost is not None else float("inf")
        dominated = False
        for other, other_minimum, other_average, _other_group_score, _other_penalty in scored:
            if other["candidate_id"] == candidate["candidate_id"]:
                continue
            other_cost = other.get("estimated_cost_minor")
            other_cost_value = other_cost if other_cost is not None else float("inf")
            at_least = other_minimum >= minimum and other_average >= average and other_cost_value <= cost_value
            strictly = other_minimum > minimum or other_average > average or other_cost_value < cost_value
            if at_least and strictly:
                dominated = True
                break
        if not dominated:
            result.append(ParetoCandidate(candidate["candidate_id"], "Not dominated across minimum score, average score, and cost."))
    return tuple(sorted(result, key=lambda x: x.candidate_id))
