"""Find alternatives not dominated across satisfaction and supplied cost."""

from __future__ import annotations

from .models import CandidateScore, ParetoCandidate


def _metrics(row: CandidateScore) -> tuple[float, float, float]:
    cost = row.candidate["estimated_cost_minor"]
    return row.minimum, row.average, -cost if cost is not None else float("-inf")


def pareto_frontier(scored: list[CandidateScore]) -> tuple[ParetoCandidate, ...]:
    metrics = {row.candidate["candidate_id"]: _metrics(row) for row in scored}
    result = []
    for candidate_id, values in metrics.items():
        dominated = any(
            all(other >= value for other, value in zip(other_values, values))
            and any(other > value for other, value in zip(other_values, values))
            for other_id, other_values in metrics.items() if other_id != candidate_id
        )
        if not dominated:
            result.append(ParetoCandidate(candidate_id, "Not dominated across minimum score, average score, and cost."))
    return tuple(sorted(result, key=lambda row: row.candidate_id))
