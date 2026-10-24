"""Conservative English comparative grammar, independent of decision domains.

The semantic provider still selects the criterion. These rules recognize the
direction and preference strength in its supporting clause, not option facts.
"""

from __future__ import annotations

import re


DIRECTION_WORDS = {
    "more": "maximize", "greater": "maximize", "higher": "maximize",
    "larger": "maximize", "longer": "maximize", "heavier": "maximize",
    "less": "minimize", "lower": "minimize", "smaller": "minimize",
    "shorter": "minimize", "lighter": "minimize", "cheaper": "minimize",
}
COMPARATIVE = r"\b(" + "|".join(DIRECTION_WORDS) + r")\b"
PREFERENCE_VERB = r"\b(?:prefer|favour|favor|like|want|choose|pick)\b"
NEGATED = re.compile(r"\b(?:not|never|avoid|dislike|hate|without|don't|cannot|can't)\b", re.I)


def comparative_direction(clause: str) -> str | None:
    """Recognize an unbounded comparative preference in one supporting clause.

    Negation, numbers, explicit comparisons against another value, and several
    comparative words stay with semantic extraction/clarification. A grammatical
    comparative is not sufficient evidence of a hard feasibility requirement.
    """
    text = " ".join(clause.casefold().split()).strip(" .!?")
    if NEGATED.search(text) or re.search(r"\d|\bthan\b|[.;!?]", text):
        return None
    matches = list(re.finditer(COMPARATIVE, text))
    if len(matches) != 1:
        return None
    comparative = matches[0]
    correlative = re.fullmatch(r"the\s+" + COMPARATIVE + r"\s+.+,\s*(?:the\s+)?better", text)
    better = re.fullmatch(COMPARATIVE + r"(?:\s+.+?)?\s+(?:is|would be)\s+better", text)
    preferred = re.search(PREFERENCE_VERB, text[:comparative.start()])
    if preferred and re.search(r"\band\b|\bor\b", text):
        preferred = None
    if correlative or better or preferred:
        return DIRECTION_WORDS[comparative.group(1)]
    return None
