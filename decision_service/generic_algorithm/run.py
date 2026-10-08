"""Rank equality-based generic option decisions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from decision_service.algorithm.scoring import group_objective_metrics
from decision_service.generic_option_contract import ContractError, validate_handoff


@dataclass(frozen=True)
class GenericDecisionResult:
    status: str
    run_id: str
    algorithm_version: str
    policy_version: str | None
    ranked_candidates: tuple[dict, ...]
    candidate_results: tuple[dict, ...]
    issues: tuple[str, ...] = ()
    pareto_frontier: tuple[dict, ...] = ()

    def as_dict(self) -> dict:
        return {**self.__dict__, "ranked_candidates": list(self.ranked_candidates),
                "candidate_results": list(self.candidate_results), "pareto_frontier": list(self.pareto_frontier),
                "issues": list(self.issues)}


def _facts(candidate: dict) -> dict:
    return {fact["attribute_id"]: fact for fact in candidate.get("facts", [])}


def _required_participants(handoff: dict) -> list[str]:
    return [p["participant_id"] for p in handoff["participants"] if p.get("is_required_for_decision", True)]


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _in_range(value: object, bounds: dict) -> bool:
    numeric = _decimal(value)
    lower, upper = bounds.get("lower"), bounds.get("upper")
    if lower is not None and (numeric < _decimal(lower) or numeric == _decimal(lower) and not bounds.get("lower_inclusive", True)):
        return False
    if upper is not None and (numeric > _decimal(upper) or numeric == _decimal(upper) and not bounds.get("upper_inclusive", True)):
        return False
    return True


def _constraint_matches(value: object, constraint: dict) -> bool:
    rule, required = constraint["constraint_rule"], constraint.get("required_value")
    if rule == "equals_v1":
        return value == required
    if rule == "not_equals_v1":
        return value != required
    if rule == "within_range_v1":
        return _in_range(value, required)
    if rule == "contains_all_v1":
        return set(required) <= set(value)
    if rule == "excludes_all_v1":
        return not set(required) & set(value)
    actual, bound = _decimal(value), _decimal(required)
    return {
        "maximum_v1": actual <= bound,
        "minimum_v1": actual >= bound,
        "less_than_v1": actual < bound,
        "greater_than_v1": actual > bound,
    }[rule]


def _feasibility(candidate: dict, constraints: list[dict], required: set[str]) -> tuple[str, tuple[str, ...]]:
    facts = _facts(candidate)
    codes = []
    for constraint in constraints:
        if constraint.get("participant_id") not in required or constraint.get("kind") == "unlimited":
            continue
        fact = facts.get(constraint["attribute_id"])
        if fact is None or fact.get("status") != "confirmed":
            codes.append("MISSING_HARD_OPTION_FACT")
        elif not _constraint_matches(fact.get("value"), constraint):
            codes.append("REQUIRED_ATTRIBUTE_NOT_MET")
    if "MISSING_HARD_OPTION_FACT" in codes:
        return "unresolved", tuple(sorted(set(codes)))
    if codes:
        return "infeasible", tuple(sorted(set(codes)))
    return "feasible", ()


def _numeric_utility(value: object, preference: dict) -> float:
    """Return a bounded scalar utility using preprocessing's declared scale/bounds."""
    rule, params = preference["utility_rule"], preference.get("utility_parameters", {})
    actual = _decimal(value)
    if rule == "numeric_target_v1":
        scale = _decimal(params["scale"])
        return float(max(Decimal(0), Decimal(1) - abs(actual - _decimal(preference["preferred_value"])) / scale))
    if rule in {"numeric_maximize_v1", "numeric_minimize_v1"}:
        lower, upper = _decimal(params["lower_bound"]), _decimal(params["upper_bound"])
        if lower == upper:
            return 1.0
        position = (actual - lower) / (upper - lower)
        return float(position if rule == "numeric_maximize_v1" else Decimal(1) - position)
    bounds = preference["preferred_value"]
    if _in_range(actual, bounds):
        return 1.0
    lower, upper = params.get("lower_bound"), params.get("upper_bound")
    if lower is None or upper is None or _decimal(lower) == _decimal(upper):
        return 0.0
    distance = _decimal(lower) - actual if bounds.get("lower") is not None and actual < _decimal(bounds["lower"]) else actual - _decimal(bounds["upper"])
    return float(max(Decimal(0), Decimal(1) - distance / (_decimal(upper) - _decimal(lower))))


def _utility(fact: dict, preference: dict) -> float:
    rule = preference["utility_rule"]
    if rule == "attribute_match_v1":
        matched = fact.get("value") == preference.get("preferred_value")
        return float(not matched) if preference.get("polarity") == "avoid" else float(matched)
    if rule == "tag_overlap_v1":
        preferred = set(preference.get("preferred_value", []))
        overlap = len(preferred & set(fact.get("value", []))) / len(preferred) if preferred else 0.0
        return 1.0 - overlap if preference.get("polarity") == "avoid" else overlap
    return _numeric_utility(fact.get("value"), preference)


def _pareto_frontier(scored: list[tuple]) -> tuple[dict, ...]:
    """Keep options not dominated on minimum and average member satisfaction."""
    frontier = []
    for candidate, minimum, average, _, _ in scored:
        dominated = any(
            other_minimum >= minimum and other_average >= average
            and (other_minimum > minimum or other_average > average)
            for other, other_minimum, other_average, _, _ in scored if other["option_id"] != candidate["option_id"]
        )
        if not dominated:
            frontier.append({"option_id": candidate["option_id"],
                             "explanation": "Not dominated across minimum and average member satisfaction."})
    return tuple(sorted(frontier, key=lambda row: row["option_id"]))


def _score(candidate: dict, handoff: dict, required: list[str]) -> tuple[dict[str, float], tuple[str, ...]]:
    facts = _facts(candidate)
    preferences = handoff["preferences"]
    member_weights = handoff["scoring_model"]["member_weights"]
    by_member_criterion = {}
    for preference in preferences:
        by_member_criterion.setdefault((preference["participant_id"], preference["source_question_id"], preference["attribute_id"]), []).append(preference)
    scores = {}
    for participant_id in required:
        total = 0.0
        for row in member_weights:
            if row.get("participant_id") != participant_id or row.get("status") != "resolved":
                continue
            key = (participant_id, row["source_question_id"], row["attribute_id"])
            answers = by_member_criterion.get(key, [])
            if not answers:
                return {}, ("MISSING_SOFT_ANSWER",)
            if all(answer.get("kind") == "indifferent" for answer in answers):
                total += row["effective_weight"] * 0.5
                continue
            fact = facts.get(row["attribute_id"])
            if fact is None or fact.get("status") != "confirmed":
                return {}, ("MISSING_SOFT_OPTION_FACT",)
            utilities = []
            for answer in answers:
                if answer.get("kind") == "indifferent":
                    utilities.append(0.5)
                else:
                    utilities.append(_utility(fact, answer))
            total += row["effective_weight"] * sum(utilities) / len(utilities)
        scores[participant_id] = round(total, 12)
    return scores, ()


def run_decision(handoff: dict) -> GenericDecisionResult:
    """Evaluate feasible options under the declared common fairness objective."""
    run_id = str(uuid4())
    try:
        validate_handoff(handoff)
    except ContractError as exc:
        return GenericDecisionResult("invalid_input", run_id, "generic-option-baseline-v1", None, (), (), (str(exc),))
    required = _required_participants(handoff)
    if not required:
        return GenericDecisionResult("invalid_input", run_id, "generic-option-baseline-v1", handoff["context"].get("policy_version"), (), (), ("NO_REQUIRED_PARTICIPANTS",))
    results, scored = [], []
    for candidate in handoff["candidates"]:
        state, codes = _feasibility(candidate, handoff["constraints"], set(required))
        result = {"option_id": candidate["option_id"], "feasibility": state, "explanation_codes": list(codes)}
        if state == "feasible":
            scores, score_codes = _score(candidate, handoff, required)
            if score_codes:
                result.update(feasibility="unresolved", explanation_codes=list(score_codes))
            else:
                minimum, average = min(scores.values()), sum(scores.values()) / len(scores)
                group_score, variance = group_objective_metrics(minimum, average, scores, handoff["scoring_model"]["group_objective"])
                scored.append((candidate, minimum, average, group_score, variance))
        results.append(result)
    if not scored:
        status = "blocked" if any(row["feasibility"] == "unresolved" for row in results) else "no_feasible_candidate"
        return GenericDecisionResult(status, run_id, handoff["context"].get("algorithm_version"), handoff["context"].get("policy_version"), (), tuple(results))
    ordered = sorted(scored, key=lambda row: (-row[3], -row[1], -row[2], row[0]["option_id"]))
    ranked = tuple({"option_id": row[0]["option_id"], "rank": index, "min_member_score": round(row[1], 12),
                    "average_member_score": round(row[2], 12), "group_score": round(row[3], 12),
                    "fairness_penalty": round(row[4], 12)} for index, row in enumerate(ordered, 1))
    return GenericDecisionResult("ranked", run_id, handoff["context"].get("algorithm_version"), handoff["context"].get("policy_version"),
                                 ranked, tuple(results), pareto_frontier=_pareto_frontier(scored))
