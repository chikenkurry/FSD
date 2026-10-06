from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Status(str, Enum):
    RANKED = "ranked"
    BLOCKED = "blocked"
    NO_FEASIBLE_CANDIDATE = "no_feasible_candidate"
    INVALID_INPUT = "invalid_input"


class Feasibility(str, Enum):
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class CandidateResult:
    candidate_id: str
    feasibility: Feasibility
    explanation_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateScore:
    candidate: dict[str, Any]
    minimum: float
    average: float
    group_score: float
    fairness_penalty: float


@dataclass(frozen=True)
class RankedCandidate:
    candidate_id: str
    rank: int
    min_member_score: float
    average_member_score: float
    group_score: float
    fairness_penalty: float
    estimated_cost_minor: int | None
    start_at: str
    explanation_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParetoCandidate:
    candidate_id: str
    explanation: str


@dataclass(frozen=True)
class DecisionResult:
    status: Status
    run_id: str
    algorithm_version: str
    policy_version: str
    ranked_candidates: tuple[RankedCandidate, ...]
    candidate_results: tuple[CandidateResult, ...]
    pareto_frontier: tuple[ParetoCandidate, ...] = ()
    issues: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "run_id": self.run_id,
            "algorithm_version": self.algorithm_version,
            "policy_version": self.policy_version,
            "ranked_candidates": [r.__dict__ for r in self.ranked_candidates],
            "candidate_results": [
                {**r.__dict__, "feasibility": r.feasibility.value}
                for r in self.candidate_results
            ],
            "pareto_frontier": [p.__dict__ for p in self.pareto_frontier],
            "issues": list(self.issues),
        }
