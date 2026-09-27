from __future__ import annotations

from .models import ParetoCandidate
from .scoring import ScoredCandidate


def compute_pareto_frontier(
    scored_candidates: tuple[ScoredCandidate, ...],
) -> tuple[ParetoCandidate, ...]:
    frontier: list[ParetoCandidate] = []

    for candidate in scored_candidates:
        if any(
            dominates(other, candidate)
            for other in scored_candidates
            if other.candidate.candidate_id != candidate.candidate.candidate_id
        ):
            continue

        frontier.append(
            ParetoCandidate(
                candidate_id=candidate.candidate.candidate_id,
                explanation=(
                    "Not dominated across minimum rating, average rating, and cost."
                ),
            )
        )

    return tuple(sorted(frontier, key=lambda item: item.candidate_id))


def dominates(left: ScoredCandidate, right: ScoredCandidate) -> bool:
    left_cost = _cost_for_comparison(left)
    right_cost = _cost_for_comparison(right)

    at_least_as_good = (
        left.min_rating >= right.min_rating
        and left.average_rating >= right.average_rating
        and left_cost <= right_cost
    )
    strictly_better = (
        left.min_rating > right.min_rating
        or left.average_rating > right.average_rating
        or left_cost < right_cost
    )

    return at_least_as_good and strictly_better


def _cost_for_comparison(candidate: ScoredCandidate) -> float:
    if candidate.candidate.estimated_cost_minor is None:
        return float("inf")
    return candidate.candidate.estimated_cost_minor

