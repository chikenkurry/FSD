"""Versioned metadata for how preprocessing produced member weights."""

from __future__ import annotations

from copy import deepcopy
from collections import Counter


WEIGHTING_POLICY_V1 = {
    "version": "v1",
    "base_strategy": "question_relevance_v1",
    "organiser_levels": {"less": 0.25, "normal": 0.5, "more": 1.0},
    "duplicate_criterion_policy": "automatic_topic_share_v1",
    "member_importance_policy": "question_share_times_importance_v1",
    "ordinal_importance_policy": "longest_path_tiers_v1",
}

WEIGHTING_POLICY_V2 = {
    "version": "v2",
    "base_strategy": "criterion_max_relevance_v2",
    "organiser_levels": {"less": 0.25, "normal": 0.5, "more": 1.0},
    "duplicate_criterion_policy": "criterion_mass_split_equally_v2",
    "member_importance_policy": "question_share_times_importance_v1",
    "ordinal_importance_policy": "longest_path_tiers_v1",
}


def v1_policy() -> dict:
    """Return a caller-owned v1 policy record for a frozen handoff."""
    return deepcopy(WEIGHTING_POLICY_V1)


def v2_policy() -> dict:
    """Return a caller-owned v2 policy record for an opt-in handoff."""
    return deepcopy(WEIGHTING_POLICY_V2)


def resolve_question_weights(questions: list[dict], version: str) -> tuple[dict[str, float], dict[str, str]]:
    """Resolve normalised soft-question weights under one frozen policy version."""
    if version not in {"v1", "v2"}:
        raise ValueError(f"Unsupported weighting policy version: {version}")
    soft = [q for q in questions if q["role"] == "soft"]
    if not soft:
        return {}, {}
    topic_counts = Counter(q["criterion"] for q in soft if q["leader_weight"] is None)
    leader_scale = max([1.0] + [float(q["leader_weight"])
                                for q in soft if q["leader_weight"] is not None])
    raw = {
        q["question_id"]: (
            float(q["leader_weight"]) / leader_scale
            if q["leader_weight"] is not None
            else q["relevance"] / topic_counts[q["criterion"]]
        )
        for q in soft
    }
    if version == "v1":
        total = sum(raw.values())
        sources = {
            q["question_id"]: "leader" if q["leader_weight"] is not None else q["inference_source"]
            for q in soft
        }
        return ({qid: value / total for qid, value in raw.items()} if total else {}, sources)

    # v2 allocates shared mass to the underlying criterion first. The highest
    # declared question relevance is the criterion's organiser priority;
    # repeated wording cannot increase that criterion's total influence.
    criterion_questions: dict[str, list[dict]] = {}
    criterion_priority: dict[str, float] = {}
    for question in soft:
        criterion = question["criterion"]
        criterion_questions.setdefault(criterion, []).append(question)
        priority = (
            float(question["leader_weight"]) / leader_scale
            if question["leader_weight"] is not None
            else float(question["relevance"])
        )
        criterion_priority[criterion] = max(criterion_priority.get(criterion, 0.0), priority)
    total = sum(criterion_priority.values())
    if not total:
        return {}, {q["question_id"]: "criterion_mass_v2" for q in soft}
    weights = {}
    for criterion, grouped in criterion_questions.items():
        share = criterion_priority[criterion] / total / len(grouped)
        for question in grouped:
            weights[question["question_id"]] = share
    return weights, {q["question_id"]: "criterion_mass_v2" for q in soft}
