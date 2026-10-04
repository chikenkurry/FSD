from __future__ import annotations

from typing import Any

from .feasibility import evaluate_candidate
from .models import CandidateResult, DecisionResult, Feasibility, Status
from .pareto import pareto_frontier
from .ranking import rank_candidates
from .scoring import score_candidate
from .validation import AlgorithmInputError, validate_algorithm_input


def run_decision(algorithm_input: dict[str, Any], run_id: str = "local-run") -> DecisionResult:
    try:
        validate_algorithm_input(algorithm_input)
    except AlgorithmInputError as exc:
        return DecisionResult(Status.INVALID_INPUT, run_id, "baseline-v1", "unknown", (), (), issues=(str(exc),))
    context = algorithm_input["context"]
    algorithm_version = context.get("algorithm_version", "baseline-v1")
    policy_version = context.get("policy_version", "unknown")
    if context.get("schema_version") == "sparse-v2":
        return DecisionResult(Status.BLOCKED, run_id, algorithm_version, policy_version, (), (), issues=("SPARSE_HANDOFF_NOT_SUPPORTED",))
    participants = algorithm_input["participants"]
    required_ids = {p["participant_id"] for p in participants if p.get("is_required_for_decision", True)}
    readiness = []
    for participant in participants:
        if participant.get("is_required_for_decision", True) and participant.get("response_status") != "complete":
            readiness.append("STALE_RESPONSE" if participant.get("response_status") == "stale" else "INCOMPLETE_RESPONSE")
    if readiness:
        return DecisionResult(Status.BLOCKED, run_id, algorithm_version, policy_version, (), (), issues=tuple(sorted(set(readiness))))
    constraints = {c["participant_id"]: c for c in algorithm_input["constraints"]}
    results: list[CandidateResult] = []
    scored = []
    questions = algorithm_input["scoring_model"].get("questions", [])
    objective = algorithm_input["scoring_model"].get("group_objective", {})
    for candidate in algorithm_input["candidates"]:
        result = evaluate_candidate(candidate, required_ids, constraints)
        results.append(result)
        if result.feasibility is Feasibility.FEASIBLE:
            minimum, average, group_score, fairness_penalty, _ = score_candidate(candidate, participants, algorithm_input["preferences"], questions, objective)
            scored.append((candidate, minimum, average, group_score, fairness_penalty))
    if not scored:
        status = Status.BLOCKED if any(r.feasibility is Feasibility.UNRESOLVED for r in results) else Status.NO_FEASIBLE_CANDIDATE
        return DecisionResult(status, run_id, algorithm_version, policy_version, (), tuple(results))
    ranked = rank_candidates(scored)
    return DecisionResult(Status.RANKED, run_id, algorithm_version, policy_version, ranked, tuple(results), pareto_frontier(scored))
