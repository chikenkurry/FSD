"""Rank generic options using declared constraints, utilities and group objectives."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone
import re
from uuid import uuid4

from decision_service.algorithm.scoring import group_objective_metrics
from decision_service.generic_option_contract import ContractError, validate_handoff
from decision_service.ranking import primary_score_key, primary_ties


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
        utility = position if rule == "numeric_maximize_v1" else Decimal(1) - position
        return float(max(Decimal(0), min(Decimal(1), utility)))
    bounds = preference["preferred_value"]
    if _in_range(actual, bounds):
        return 1.0
    lower, upper = params.get("lower_bound"), params.get("upper_bound")
    if lower is None or upper is None or _decimal(lower) == _decimal(upper):
        return 0.0
    distance = _decimal(bounds["lower"]) - actual if bounds.get("lower") is not None and actual < _decimal(bounds["lower"]) else actual - _decimal(bounds["upper"])
    return float(max(Decimal(0), Decimal(1) - distance / (_decimal(upper) - _decimal(lower))))


_STOP_TOKENS = frozenset({
    "a", "an", "the", "and", "or", "of", "in", "on", "with", "for", "to", "by", "at",
    "that", "from", "style", "themed", "inspired", "incorporate", "incorporates", "influences",
})


def _stem_token(word: str) -> str:
    if word == "cozy":
        return "cosy"
    if len(word) > 5 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 4 and word.endswith("es"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _content_tokens(text: object) -> set[str]:
    if not isinstance(text, str):
        return set()
    raw = [_stem_token(w) for w in re.findall(r"[a-z0-9]+", text.casefold())]
    filtered = {w for w in raw if w and w not in _STOP_TOKENS}
    return filtered or set(raw)


def _phrase_similarity(actual: object, preferred: object) -> float:
    if actual == preferred:
        return 1.0
    if not isinstance(actual, str) or not isinstance(preferred, str):
        return 0.0
    a_tokens = _content_tokens(actual)
    p_tokens = _content_tokens(preferred)
    if not a_tokens or not p_tokens:
        return 0.0
    if p_tokens <= a_tokens or a_tokens <= p_tokens:
        return 1.0
    overlap = len(a_tokens & p_tokens)
    return overlap / len(p_tokens) if overlap else 0.0


def similarity_table(handoff: dict) -> dict[tuple[str, str, str], float]:
    """Frozen model judgements of how well a fact value meets a preferred value."""
    return {(row["attribute_id"], row["preferred"], row["actual"]): float(row["score"])
            for row in handoff.get("similarity", []) if isinstance(row, dict)}


def _similarity(attribute_id: str, actual: object, preferred: object, table: dict | None) -> float:
    lexical = _phrase_similarity(actual, preferred)
    if lexical >= 1.0 or not table or not isinstance(actual, str) or not isinstance(preferred, str):
        return lexical
    return max(lexical, table.get((attribute_id, preferred, actual), 0.0))


def _utility(fact: dict, preference: dict, table: dict | None = None) -> float:
    rule = preference["utility_rule"]
    aid = preference.get("attribute_id", fact.get("attribute_id", ""))
    if rule == "option_rating_v1":
        # The fact is the option's own identity; each member rated options directly.
        return float(preference.get("preferred_value", {}).get(fact.get("value"), 0.5))
    if rule == "attribute_match_v1":
        score = _similarity(aid, fact.get("value"), preference.get("preferred_value"), table)
        return 1.0 - score if preference.get("polarity") == "avoid" else score
    if rule == "tag_overlap_v1":
        preferred = list(preference.get("preferred_value", []))
        actual = list(fact.get("value", []))
        if not preferred:
            overlap = 0.0
        else:
            overlap = sum(
                max((_similarity(aid, a, p, table) for a in actual), default=0.0)
                for p in preferred
            ) / len(preferred)
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


def _metric(value: float) -> float:
    """Use the same precision for ordering and reported tie groups."""
    return round(value, 12)


def _primary_key(row: tuple, mode: str) -> tuple[float, ...]:
    _, minimum, average, group_score, _ = row
    return primary_score_key(minimum, average, group_score, mode)


def _start_key(candidate: dict) -> datetime:
    value = candidate.get("start_at")
    if value is None:
        return datetime.max.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _ranking_key(row: tuple, sort_order: list[str]) -> tuple:
    candidate, minimum, average, group_score, _ = row
    values = {
        "highest_group_score": -_metric(group_score),
        "highest_min_member_score": -_metric(minimum),
        "highest_average_member_score": -_metric(average),
        "lowest_estimated_cost": candidate.get("estimated_cost_minor")
        if candidate.get("estimated_cost_minor") is not None else float("inf"),
        "earliest_start": _start_key(candidate),
        "stable_candidate_id": candidate["option_id"],
    }
    return tuple(values[field] for field in sort_order)


def _scoring_rows(handoff: dict, required: list[str]) -> dict[str, list[tuple[dict, list[dict]]]]:
    """Index candidate-independent answers/weights once, preserving their order."""
    by_member_criterion = {}
    for preference in handoff["preferences"]:
        by_member_criterion.setdefault((preference["participant_id"], preference["source_question_id"], preference["attribute_id"]), []).append(preference)
    rows = {participant_id: [] for participant_id in required}
    for weight in handoff["scoring_model"]["member_weights"]:
        participant_id = weight.get("participant_id")
        if participant_id in rows and weight.get("status") == "resolved":
            key = (participant_id, weight["source_question_id"], weight["attribute_id"])
            rows[participant_id].append((weight, by_member_criterion.get(key, [])))
    return rows


def _score(candidate: dict, rows_by_member: dict, table: dict | None = None) -> tuple[dict[str, float], tuple[str, ...]]:
    facts = _facts(candidate)
    scores = {}
    for participant_id, rows in rows_by_member.items():
        total = 0.0
        active_weight = 0.0
        for row, answers in rows:
            if not answers:
                return {}, ("MISSING_SOFT_ANSWER",)
            if all(answer.get("kind") == "indifferent" for answer in answers):
                continue
            fact = facts.get(row["attribute_id"])
            if fact is None or fact.get("status") != "confirmed":
                return {}, ("MISSING_SOFT_OPTION_FACT",)
            active_answers = [a for a in answers if a.get("kind") != "indifferent"]
            utilities = [_utility(fact, answer, table) for answer in active_answers]
            total += row["effective_weight"] * sum(utilities) / len(utilities)
            active_weight += row["effective_weight"]
        scores[participant_id] = round(total / active_weight, 12) if active_weight > 0 else 0.5
    return scores, ()


def run_decision(handoff: dict) -> GenericDecisionResult:
    """Evaluate feasible options under the declared common fairness objective."""
    run_id = str(uuid4())
    try:
        validate_handoff(handoff)
    except ContractError as exc:
        return GenericDecisionResult("invalid_input", run_id, "generic-option-baseline-v2", None, (), (), (str(exc),))
    required = _required_participants(handoff)
    if not required:
        return GenericDecisionResult("invalid_input", run_id, "generic-option-baseline-v2", handoff["context"].get("policy_version"), (), (), ("NO_REQUIRED_PARTICIPANTS",))
    if any(p.get("response_status", "complete") != "complete" for p in handoff["participants"] if p["participant_id"] in required):
        return GenericDecisionResult("blocked", run_id, handoff["context"].get("algorithm_version"), handoff["context"].get("policy_version"), (), (), ("INCOMPLETE_RESPONSE",))
    required_set = set(required)
    scoring_rows = None
    table = similarity_table(handoff)
    results, scored = [], []
    for candidate in handoff["candidates"]:
        state, codes = _feasibility(candidate, handoff["constraints"], required_set)
        flags = {flag["flag"] for flag in handoff.get("option_flags", [])
                 if flag["participant_id"] in required_set and flag["activity_id"] == candidate.get("source_option_id", candidate["option_id"])}
        if "cannot_join" in flags:
            state, codes = "infeasible", tuple(sorted(set(codes) | {"CANNOT_JOIN"}))
        elif "needs_information" in flags and state != "infeasible":
            state, codes = "unresolved", tuple(sorted(set(codes) | {"NEEDS_INFORMATION"}))
        result = {"option_id": candidate["option_id"], "feasibility": state, "explanation_codes": list(codes)}
        if state == "feasible":
            if scoring_rows is None:
                scoring_rows = _scoring_rows(handoff, required)
            scores, score_codes = _score(candidate, scoring_rows, table)
            if score_codes:
                result.update(feasibility="unresolved", explanation_codes=list(score_codes))
            else:
                minimum, average = min(scores.values()), sum(scores.values()) / len(scores)
                group_score, variance = group_objective_metrics(minimum, average, scores, handoff["scoring_model"]["group_objective"])
                scored.append((candidate, minimum, average, group_score, variance))
        results.append(result)
    if not scored or any(row["feasibility"] == "unresolved" for row in results):
        status = "blocked" if any(row["feasibility"] == "unresolved" for row in results) else "no_feasible_candidate"
        return GenericDecisionResult(status, run_id, handoff["context"].get("algorithm_version"), handoff["context"].get("policy_version"), (), tuple(results))
    model = handoff["scoring_model"]
    sort_order = model["ranking_policy"]["sort_order"]
    mode = model["group_objective"]["mode"]
    ordered = sorted(scored, key=lambda row: _ranking_key(row, sort_order))
    primary_keys = [_primary_key(row, mode) for row in ordered]
    ties = primary_ties(primary_keys)
    ranked = tuple({"option_id": row[0]["option_id"], "rank": index,
                    "primary_rank": ties[key][0],
                    "primary_objective_tie_size": ties[key][1],
                    "min_member_score": round(row[1], 12), "average_member_score": round(row[2], 12),
                    "group_score": round(row[3], 12), "fairness_penalty": round(row[4], 12)}
                   for index, (row, key) in enumerate(zip(ordered, primary_keys), 1))
    return GenericDecisionResult("ranked", run_id, handoff["context"].get("algorithm_version"), handoff["context"].get("policy_version"),
                                 ranked, tuple(results), pareto_frontier=_pareto_frontier(scored))
