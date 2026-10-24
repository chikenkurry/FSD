from __future__ import annotations

from typing import Any

from decision_service.contract import ContractError, validate_handoff

from .feasibility import evaluate_candidate
from .models import CandidateResult, CandidateScore, DecisionResult, Feasibility, Status
from .pareto import pareto_frontier
from .ranking import rank_candidates
from .scoring import UnresolvedScore, score_candidate


def run_decision(algorithm_input: dict[str, Any], run_id: str = "local-run") -> DecisionResult:
    if (isinstance(algorithm_input, dict)
            and isinstance(algorithm_input.get("context"), dict)
            and algorithm_input["context"].get("schema_version") in ("sparse-v2", "sparse-v3", "sparse-v4")):
        return DecisionResult(Status.BLOCKED, run_id, "baseline-v2", "unknown", (), (), issues=("SPARSE_HANDOFF_NOT_SUPPORTED",))
    try:
        validate_handoff(algorithm_input)
    except ContractError as exc:
        return DecisionResult(Status.INVALID_INPUT, run_id, "baseline-v2", "unknown", (), (), issues=(str(exc),))
    context = algorithm_input["context"]
    algorithm_version = context.get("algorithm_version", "baseline-v2")
    policy_version = context.get("policy_version", "unknown")
    participants = algorithm_input["participants"]
    required_ids = {p["participant_id"] for p in participants if p["is_required_for_decision"]}
    readiness = []
    for participant in participants:
        if participant["is_required_for_decision"] and participant["response_status"] != "complete":
            readiness.append("STALE_RESPONSE" if participant.get("response_status") == "stale" else "INCOMPLETE_RESPONSE")
    if readiness:
        return DecisionResult(Status.BLOCKED, run_id, algorithm_version, policy_version, (), (), issues=tuple(sorted(set(readiness))))
    constraints = {c["participant_id"]: c for c in algorithm_input["constraints"]}
    results: list[CandidateResult] = []
    scored: list[CandidateScore] = []
    model = algorithm_input["scoring_model"]
    for candidate in algorithm_input["candidates"]:
        result = evaluate_candidate(candidate, required_ids, constraints)
        if result.feasibility is Feasibility.FEASIBLE:
            try:
                scored.append(score_candidate(
                    candidate, participants, algorithm_input["preferences"],
                    model["questions"], model["group_objective"],
                ))
            except UnresolvedScore as exc:
                result = CandidateResult(candidate["candidate_id"], Feasibility.UNRESOLVED, (exc.code,))
        results.append(result)
    if any(r.feasibility is Feasibility.UNRESOLVED for r in results):
        # A missing comparison could change the winner; do not rank a subset.
        return DecisionResult(Status.BLOCKED, run_id, algorithm_version, policy_version, (), tuple(results))
    if not scored:
        return DecisionResult(Status.NO_FEASIBLE_CANDIDATE, run_id, algorithm_version, policy_version, (), tuple(results))
    ranked = rank_candidates(scored, model["ranking_policy"]["sort_order"])
    return DecisionResult(Status.RANKED, run_id, algorithm_version, policy_version, ranked, tuple(results), pareto_frontier(scored))
