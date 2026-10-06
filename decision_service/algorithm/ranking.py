"""Stable ordering using the validated objective and tie breakers."""

from __future__ import annotations

from decision_service.contract import timestamp

from .models import CandidateScore, RankedCandidate


def rank_candidates(scored: list[CandidateScore], sort_order: list[str]) -> tuple[RankedCandidate, ...]:
    keys = {
        "highest_group_score": lambda row: -row.group_score,
        "highest_min_member_score": lambda row: -row.minimum,
        "highest_average_member_score": lambda row: -row.average,
        "lowest_estimated_cost": lambda row: (
            row.candidate["estimated_cost_minor"]
            if row.candidate["estimated_cost_minor"] is not None else float("inf")
        ),
        "earliest_start": lambda row: timestamp(row.candidate["start_at"]),
        "stable_candidate_id": lambda row: row.candidate["candidate_id"],
    }
    ordered = sorted(scored, key=lambda row: tuple(keys[field](row) for field in sort_order))
    return tuple(
        RankedCandidate(
            row.candidate["candidate_id"], rank,
            round(row.minimum, 12), round(row.average, 12),
            round(row.group_score, 12), round(row.fairness_penalty, 12),
            row.candidate["estimated_cost_minor"], row.candidate["start_at"],
        )
        for rank, row in enumerate(ordered, 1)
    )
