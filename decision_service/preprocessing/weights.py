"""Resolve optional leader weights without giving hard constraints a score."""

from __future__ import annotations

import math

from .common import InputError


SOFT_KINDS = {"activity_rating", "open_preference"}


def resolve_weights(questions: list[dict]) -> list[dict]:
    soft = [q for q in questions if q["kind"] in SOFT_KINDS]
    supplied = [q for q in soft if q.get("leader_weight") is not None]
    if supplied and len(supplied) != len(soft):
        raise InputError("PARTIAL_WEIGHTS", "planning.questions", "Supply every soft-question weight or none")
    if supplied:
        raw = []
        for q in soft:
            value = q["leader_weight"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise InputError("INVALID_WEIGHT", f"planning.questions.{q['question_id']}.leader_weight", "Weight must be finite and nonnegative")
            raw.append(float(value))
        total = sum(raw)
        if total <= 0 or not math.isfinite(total):
            raise InputError("INVALID_WEIGHT", "planning.questions", "Soft-question weights must have a positive finite sum")
        source = "leader"
    else:
        raw = [1.0] * len(soft)
        total = float(len(soft))
        source = "equal_default"

    weights = {q["question_id"]: value / total for q, value in zip(soft, raw)}
    return [
        {
            "question_id": q["question_id"],
            "label": q["label"],
            "kind": q["kind"],
            "weight": weights.get(q["question_id"]),
            "weight_source": source if q["question_id"] in weights else None,
            "aggregation": "average" if q["kind"] == "open_preference" else "direct",
            "is_hard_constraint": q["kind"] not in SOFT_KINDS,
        }
        for q in questions
    ]
