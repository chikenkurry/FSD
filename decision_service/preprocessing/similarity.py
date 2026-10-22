"""Model-judged meaning similarity between preferred values and option facts.

Word overlap cannot tell that "ramen" satisfies "japanese". For each criterion,
pairs that word matching does not already settle are judged once by the
semantic provider. The scores are frozen with the run's semantic evidence, so
recalculation and replay never call the model again and the ranking stays
reproducible. Without a provider (or on failure) word matching still applies.
"""

from __future__ import annotations

import logging
import math

from decision_service.generic_algorithm.run import _phrase_similarity

from .semantics import SemanticServiceError

TEXT_RULES = {"attribute_match_v1", "tag_overlap_v1"}
MAX_PAIRS_PER_CRITERION = 60


def _values(value: object) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [v for v in values if isinstance(v, str) and v.strip()]


def similarity_pairs(handoff: dict) -> dict[str, list[dict]]:
    """Unsettled (preferred, actual) pairs per criterion, in a stable order."""
    facts: dict[str, set[str]] = {}
    for candidate in handoff.get("candidates", []):
        for fact in candidate.get("facts", []):
            if fact.get("status") == "confirmed":
                facts.setdefault(fact["attribute_id"], set()).update(_values(fact.get("value")))
    wanted: dict[str, set[tuple[str, str]]] = {}
    for preference in handoff.get("preferences", []):
        if preference.get("utility_rule") not in TEXT_RULES or preference.get("kind") == "indifferent":
            continue
        aid = preference["attribute_id"]
        for preferred in _values(preference.get("preferred_value")):
            for actual in facts.get(aid, ()):
                if _phrase_similarity(actual, preferred) < 1.0:
                    wanted.setdefault(aid, set()).add((preferred, actual))
    return {aid: [{"preferred": p, "actual": a} for p, a in sorted(pairs)][:MAX_PAIRS_PER_CRITERION]
            for aid, pairs in sorted(wanted.items())}


def validate_similarity(raw: object, pairs: list[dict]) -> list[dict]:
    """Keep only scores for the pairs that were asked about, clamped to 0..1."""
    rows = raw.get("scores") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        raise SemanticServiceError("Similarity result needs a scores list")
    scored = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        index, score = row.get("index"), row.get("score")
        if type(index) is not int or not 0 <= index < len(pairs):
            continue
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            continue
        scored.append({**pairs[index], "score": round(min(1.0, max(0.0, float(score))), 2)})
    return list({(r["preferred"], r["actual"]): r for r in scored}.values())


def assess_similarity(handoff: dict, assessments: dict, provider, context: dict) -> list[dict]:
    """Fill ``assessments`` (frozen evidence) and return matcher similarity rows.

    ``provider`` is None when replaying frozen evidence: stored scores are used
    as-is and nothing new is requested.
    """
    pairs_by_criterion = similarity_pairs(handoff)
    if provider is not None and hasattr(provider, "assess_similarity"):
        for aid, pairs in pairs_by_criterion.items():
            if aid in assessments or not pairs:
                continue
            payload = {"criterion": aid, "decision_question": context.get("decision_question"),
                       "pairs": [{"index": i, **pair} for i, pair in enumerate(pairs)]}
            try:
                assessments[aid] = validate_similarity(provider.assess_similarity(payload), pairs)
            except SemanticServiceError as exc:
                # Word matching still scores these pairs; the run is not blocked.
                logging.warning("similarity_unavailable criterion=%s error=%s", aid, exc)
    rows = []
    for aid in sorted(assessments):
        known = {(p["preferred"], p["actual"]) for p in pairs_by_criterion.get(aid, [])}
        for row in assessments[aid]:
            if isinstance(row, dict) and (row.get("preferred"), row.get("actual")) in known:
                rows.append({"attribute_id": aid, "preferred": row["preferred"], "actual": row["actual"],
                             "score": row["score"], "source": "semantic_model"})
    return rows
