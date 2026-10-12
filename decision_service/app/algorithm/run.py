from __future__ import annotations

from .feasibility import evaluate_all_candidates
from .models import (
    Candidate,
    CandidateResult,
    DecisionAlgorithmInput,
    DecisionAlgorithmOutput,
    ExplanationCode,
    Feasibility,
    Status,
)
from .pareto import compute_pareto_frontier
from .ranking import rank_candidates
from .readiness import check_required_participant_readiness
from .scoring import score_candidates
from .validation import validate_input


def run_decision_algorithm(
    input_data: DecisionAlgorithmInput,
    run_id: str = "local-run",
) -> DecisionAlgorithmOutput:
    validation = validate_input(input_data)
    if not validation.ok:
        return _blocked_output(input_data, run_id, validation.explanation_codes)

    readiness = check_required_participant_readiness(input_data.participants)
    if not readiness.ok:
        return _blocked_output(input_data, run_id, readiness.explanation_codes)

    candidate_results = evaluate_all_candidates(
        input_data.candidates,
        input_data.participants,
        input_data.constraints,
    )

    feasible_candidates = _feasible_candidates(input_data.candidates, candidate_results)

    if not feasible_candidates:
        unresolved_codes = _unresolved_explanation_codes(candidate_results)
        if unresolved_codes:
            return _blocked_output(
                input_data,
                run_id,
                unresolved_codes,
                candidate_results=candidate_results,
            )

        return DecisionAlgorithmOutput(
            run_id=run_id,
            algorithm_version=input_data.context.algorithm_version,
            policy_version=input_data.context.policy_version,
            status=Status.NO_FEASIBLE_CANDIDATE,
            ranked_candidates=(),
            candidate_results=candidate_results,
        )

    try:
        scored_candidates = score_candidates(
            feasible_candidates,
            input_data.participants,
            input_data.preferences,
        )
    except ValueError:
        return _blocked_output(
            input_data,
            run_id,
            (ExplanationCode.INCOMPLETE_RESPONSE,),
            candidate_results=candidate_results,
        )

    ranked_candidates = rank_candidates(scored_candidates)
    pareto_candidates = compute_pareto_frontier(scored_candidates)

    return DecisionAlgorithmOutput(
        run_id=run_id,
        algorithm_version=input_data.context.algorithm_version,
        policy_version=input_data.context.policy_version,
        status=Status.RANKED,
        ranked_candidates=ranked_candidates,
        candidate_results=candidate_results,
        pareto_candidates=pareto_candidates,
    )


def _blocked_output(
    input_data: DecisionAlgorithmInput,
    run_id: str,
    explanation_codes: tuple[ExplanationCode, ...],
    candidate_results: tuple[CandidateResult, ...] = (),
) -> DecisionAlgorithmOutput:
    return DecisionAlgorithmOutput(
        run_id=run_id,
        algorithm_version=input_data.context.algorithm_version,
        policy_version=input_data.context.policy_version,
        status=Status.BLOCKED,
        ranked_candidates=(),
        candidate_results=candidate_results,
        explanation_codes=explanation_codes,
    )


def _feasible_candidates(
    candidates: tuple[Candidate, ...],
    candidate_results: tuple[CandidateResult, ...],
) -> tuple[Candidate, ...]:
    feasible_ids = {
        result.candidate_id
        for result in candidate_results
        if result.feasibility == Feasibility.FEASIBLE
    }
    return tuple(candidate for candidate in candidates if candidate.candidate_id in feasible_ids)


def _unresolved_explanation_codes(
    candidate_results: tuple[CandidateResult, ...],
) -> tuple[ExplanationCode, ...]:
    codes = {
        code
        for result in candidate_results
        if result.feasibility == Feasibility.UNRESOLVED
        for code in result.explanation_codes
    }
    return tuple(sorted(codes))
