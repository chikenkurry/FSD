"""Stable ordering using the validated objective and tie breakers."""

from __future__ import annotations

from decision_service.contract import timestamp
from decision_service.ranking import primary_score_key, primary_ties

from .models import CandidateScore, RankedCandidate


def rank_candidates(scored: list[CandidateScore], sort_order: list[str]) -> tuple[RankedCandidate, ...]:
    keys = {
        "highest_group_score": lambda row: -round(row.group_score, 12),
        "highest_min_member_score": lambda row: -round(row.minimum, 12),
        "highest_average_member_score": lambda row: -round(row.average, 12),
        "lowest_estimated_cost": lambda row: (
            row.candidate["estimated_cost_minor"]
            if row.candidate["estimated_cost_minor"] is not None else float("inf")
        ),
        "earliest_start": lambda row: timestamp(row.candidate["start_at"]),
        "stable_candidate_id": lambda row: row.candidate["candidate_id"],
    }
    ordered = sorted(scored, key=lambda row: tuple(keys[field](row) for field in sort_order))
    mode = "weighted_fairness" if sort_order[0] == "highest_group_score" else "maximin_then_average"
    primary_keys = [primary_score_key(row.minimum, row.average, row.group_score, mode) for row in ordered]
    ties = primary_ties(primary_keys)
    return tuple(
        RankedCandidate(
            row.candidate["candidate_id"], rank,
            round(row.minimum, 12), round(row.average, 12),
            round(row.group_score, 12), round(row.fairness_penalty, 12),
            row.candidate["estimated_cost_minor"], row.candidate["start_at"],
            primary_rank=ties[key][0], primary_objective_tie_size=ties[key][1],
        )
        for rank, (row, key) in enumerate(zip(ordered, primary_keys), 1)
    )
