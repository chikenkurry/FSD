from __future__ import annotations

from typing import Any

from .models import RankedCandidate


def rank_candidates(scored: list[tuple[dict[str, Any], float, float, float, float]]) -> tuple[RankedCandidate, ...]:
    ordered = sorted(scored, key=lambda x: (-x[3], -x[1], -x[2], x[0].get("estimated_cost_minor") if x[0].get("estimated_cost_minor") is not None else float("inf"), x[0]["start_at"], x[0]["candidate_id"]))
    return tuple(RankedCandidate(c[0]["candidate_id"], i, round(c[1], 12), round(c[2], 12), round(c[3], 12), round(c[4], 12), c[0].get("estimated_cost_minor"), c[0]["start_at"]) for i, c in enumerate(ordered, 1))
