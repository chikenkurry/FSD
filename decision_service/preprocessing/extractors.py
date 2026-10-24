"""Small, auditable baseline for supported open-answer meanings.

An LLM extractor can implement the same interface later. Its output must pass
the same normalization and validation as this rules baseline.
"""

from __future__ import annotations

import re

from .common import InputError
from .money import minor_amount, parse_budget


ATTRIBUTE_PHRASES: dict[str, tuple[str, ...]] = {
    "vegetarian_option": ("vegetarian", "veggie"),
    "step_free_access": ("step-free", "step free", "wheelchair accessible"),
    "indoor": ("indoor", "indoors", "inside"),
    "quiet": ("quiet", "peaceful"),
}

OPPOSITE_PHRASES = {
    "indoor": ("outdoor", "outdoors", "outside"),
    "quiet": ("noisy", "loud"),
}


def _phrase_matches(text: str, phrase: str) -> list[bool]:
    """Return whether each occurrence is negated within its short clause."""
    results = []
    pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
    for match in re.finditer(pattern, text):
        prefix = text[: match.start()]
        prefix = re.split(r"[,.!?;]|\b(?:and|but|or)\b", prefix)[-1][-35:]
        negated = re.search(r"\b(?:not|no|never|avoid|without|don['’]?t|do not)\b(?:\W+\w+){0,3}\W*$", prefix) is not None
        results.append(negated)
    return results


def _attribute_values(text: str, allowed: set[str]) -> list[tuple[str, str]]:
    found = []
    for attr_id in sorted(allowed):
        if attr_id not in ATTRIBUTE_PHRASES:
            raise InputError("UNSUPPORTED_CRITERION", "planning.questions", f"Unsupported attribute {attr_id}")
        positive = False
        negative = False
        for phrase in ATTRIBUTE_PHRASES[attr_id]:
            for negated in _phrase_matches(text, phrase):
                negative |= negated
                positive |= not negated
        for phrase in OPPOSITE_PHRASES.get(attr_id, ()):
            for negated in _phrase_matches(text, phrase):
                positive |= negated
                negative |= not negated
        if positive and negative:
            raise InputError("CONFLICTING_ANSWER", "answer", f"Both values stated for {attr_id}")
        if positive or negative:
            found.append((attr_id, "yes" if positive else "no"))
    return found


def extract_requirement(text: str, allowed: set[str]) -> list[dict]:
    normalized = text.casefold().strip().strip(" .!?")
    if normalized in {"none", "no requirements", "nothing", "no special requirements"}:
        return []
    if re.search(r"\b(?:don['’]?t|do not)\s+(?:need|require)\b", normalized):
        if re.search(r"\b(?:must|have to)\b", normalized):
            raise InputError("AMBIGUOUS_ANSWER", "answer", "Separate required and unneeded attributes")
        return []
    if not re.search(r"\b(?:must|need|require|requires|required|have to)\b", normalized):
        raise InputError("AMBIGUOUS_ANSWER", "answer", "State whether this is a requirement")
    values = _attribute_values(normalized, allowed)
    if not values:
        raise InputError("UNSUPPORTED_ANSWER", "answer", "No supported requirement was found")
    return [{"attribute_id": attr_id, "required_value": value} for attr_id, value in values]


def extract_preference(text: str, allowed: set[str]) -> list[dict]:
    normalized = text.casefold().strip().strip(" .!?")
    if normalized in {"no preference", "indifferent", "either is fine", "anything is fine"}:
        return [{"kind": "indifferent", "utility_rule": "neutral_v1"}]
    values = _attribute_values(normalized, allowed)
    if not values:
        raise InputError("UNSUPPORTED_ANSWER", "answer", "No supported preference was found")
    return [
        {
            "kind": "attribute_preference",
            "attribute_id": attr_id,
            "preferred_value": value,
            "utility_rule": "attribute_match_v1",
        }
        for attr_id, value in values
    ]


def extract_budget(text: str, currency: str, *, minor_digits: int = 2) -> dict:
    budget = parse_budget(text, currency, "answer", open_text=True)
    if budget["kind"] == "unlimited":
        return budget
    return {"kind": "limited", "max_cost_minor": minor_amount(budget["amount"], minor_digits, "answer"),
            "currency": currency}
