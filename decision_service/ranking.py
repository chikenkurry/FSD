"""Shared score precision and primary-objective ties for both matchers."""
from collections import Counter


def primary_score_key(minimum: float, average: float, group_score: float, mode: str) -> tuple:
    metrics = (group_score, minimum, average) if mode == "weighted_fairness" else (minimum, average)
    return tuple(round(value, 12) for value in metrics)


def primary_ties(ordered_keys: list[tuple]) -> dict[tuple, tuple[int, int]]:
    """Count once; first occurrence in policy order determines the dense rank."""
    counts = Counter(ordered_keys)
    return {key: (rank, count) for rank, (key, count) in enumerate(counts.items(), 1)}
