from __future__ import annotations

from .models import RankedCandidate
from .scoring import ScoredCandidate


def rank_candidates(
    scored_candidates: tuple[ScoredCandidate, ...],
) -> tuple[RankedCandidate, ...]:
    ordered = sorted(
        scored_candidates,
        key=lambda scored: (
            -scored.min_rating,
            -scored.average_rating,
            scored.candidate.estimated_cost_minor
            if scored.candidate.estimated_cost_minor is not None
            else float("inf"),
            scored.candidate.start_at,
            scored.candidate.candidate_id,
        ),
    )

    return tuple(
        RankedCandidate(
            candidate_id=scored.candidate.candidate_id,
            rank=index + 1,
            min_rating=scored.min_rating,
            average_rating=round(scored.average_rating, 4),
            average_preference_score=round(scored.average_preference_score, 1),
            estimated_cost_minor=scored.candidate.estimated_cost_minor,
            start_at=scored.candidate.start_at,
            rating_counts=scored.rating_counts,
        )
        for index, scored in enumerate(ordered)
    )

