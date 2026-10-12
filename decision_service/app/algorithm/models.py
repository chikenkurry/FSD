from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Status(StrEnum):
    RANKED = "ranked"
    BLOCKED = "blocked"
    NO_FEASIBLE_CANDIDATE = "no_feasible_candidate"


class Feasibility(StrEnum):
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    UNRESOLVED = "unresolved"


class ExplanationCode(StrEnum):
    INCOMPLETE_RESPONSE = "INCOMPLETE_RESPONSE"
    STALE_RESPONSE = "STALE_RESPONSE"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    NO_TIME_OVERLAP = "NO_TIME_OVERLAP"
    BUDGET_CONFLICT = "BUDGET_CONFLICT"
    MISSING_BUDGET = "MISSING_BUDGET"
    MISSING_COST = "MISSING_COST"
    MISSING_OPTION_FACT = "MISSING_OPTION_FACT"
    REQUIRED_ATTRIBUTE_NOT_MET = "REQUIRED_ATTRIBUTE_NOT_MET"
    CANNOT_JOIN = "CANNOT_JOIN"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True)
class DecisionContext:
    round_id: str
    option_snapshot_id: str
    response_snapshot_id: str
    timezone: str
    algorithm_version: str = "mvp-constraint-ranking-v1"
    policy_version: str = "all-required-min-avg-cost-time-v1"


@dataclass(frozen=True)
class CandidateAttribute:
    attribute_id: str
    value: str  # yes | no | unknown


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    activity_id: str
    option_revision: str
    title: str
    start_at: datetime
    end_at: datetime
    duration_minutes: int
    estimated_cost_minor: int | None
    currency: str
    attributes: tuple[CandidateAttribute, ...] = ()


@dataclass(frozen=True)
class Participant:
    participant_id: str
    response_status: str  # complete | incomplete | stale | needs_clarification
    is_required_for_decision: bool = True
    display_label: str | None = None


@dataclass(frozen=True)
class TimeInterval:
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class BudgetConstraint:
    kind: str  # limited | unlimited | missing
    max_cost_minor: int | None = None
    currency: str | None = None


@dataclass(frozen=True)
class RequiredAttributeConstraint:
    attribute_id: str
    required_value: str = "yes"


@dataclass(frozen=True)
class CandidateFlag:
    candidate_id: str
    flag: str  # cannot_join | needs_information


@dataclass(frozen=True)
class ParticipantConstraint:
    participant_id: str
    availability: tuple[TimeInterval, ...]
    budget: BudgetConstraint
    required_attributes: tuple[RequiredAttributeConstraint, ...] = ()
    candidate_flags: tuple[CandidateFlag, ...] = ()


@dataclass(frozen=True)
class ParticipantPreference:
    participant_id: str
    rating: int
    candidate_id: str | None = None
    activity_id: str | None = None
    source_question_id: str | None = None


@dataclass(frozen=True)
class ScoringModel:
    feasibility_policy: str = "all_required_participants"
    sort_order: tuple[str, ...] = (
        "highest_min_rating",
        "highest_average_rating",
        "lowest_estimated_cost",
        "earliest_start",
        "stable_candidate_id",
    )


@dataclass(frozen=True)
class DecisionAlgorithmInput:
    context: DecisionContext
    candidates: tuple[Candidate, ...]
    participants: tuple[Participant, ...]
    constraints: tuple[ParticipantConstraint, ...]
    preferences: tuple[ParticipantPreference, ...]
    scoring_model: ScoringModel = field(default_factory=ScoringModel)


@dataclass(frozen=True)
class CandidateResult:
    candidate_id: str
    feasibility: Feasibility
    explanation_codes: tuple[ExplanationCode, ...] = ()


@dataclass(frozen=True)
class RatingCounts:
    strongly_dislike: int = 0
    dislike: int = 0
    neutral: int = 0
    like: int = 0
    love: int = 0


@dataclass(frozen=True)
class RankedCandidate:
    candidate_id: str
    rank: int
    min_rating: int
    average_rating: float
    average_preference_score: float
    estimated_cost_minor: int | None
    start_at: datetime
    rating_counts: RatingCounts
    explanation_codes: tuple[ExplanationCode, ...] = ()


@dataclass(frozen=True)
class ParetoCandidate:
    candidate_id: str
    explanation: str


@dataclass(frozen=True)
class DecisionAlgorithmOutput:
    run_id: str
    algorithm_version: str
    policy_version: str
    status: Status
    ranked_candidates: tuple[RankedCandidate, ...]
    candidate_results: tuple[CandidateResult, ...]
    pareto_candidates: tuple[ParetoCandidate, ...] = ()
    explanation_codes: tuple[ExplanationCode, ...] = ()

