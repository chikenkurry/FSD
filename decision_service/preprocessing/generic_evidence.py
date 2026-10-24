"""Keep extracted requirements grounded in the clause about their own value."""

from __future__ import annotations

import re

from .common import InputError
from .comparatives import comparative_direction


CLAUSE_BREAK = re.compile(
    r"[!?;\n]+|\.(?!\d)|\b(?:but|however|whereas)\b|"
    r"\band\s+(?=(?:I|we|they|you|must|need|cannot|can't)\b)", re.I,
)
REQUIREMENT = re.compile(r"\b(?:must|need|needs|required|require|essential|mandatory|cannot|have to|only if|non-negotiable)\b|\bcan't\b", re.I)
OPTIONAL = re.compile(r"\b(?:(?:not|isn't|aren't) (?:required|essential|mandatory)|don't need|do not need|need not|needn't)\b", re.I)
PREFERENCE = re.compile(r"\b(?:prefer|favour|favor|like|enjoy|want|avoid|dislike|hate)\b", re.I)


def scoped_interpretation(item: dict, answer_text: str, role: str, path: str, *, question_criterion: str | None = None) -> dict:
    """Preserve a model excerpt, narrowing broad evidence when a value locates it.

    This is an English grounding check, not a general language classifier. It
    rejects uncertain hard evidence instead of inventing a confirmed requirement.
    """
    evidence = item["evidence"]
    value_pattern = re.compile(r"(?<!\w)" + re.escape(item["value"]) + r"(?!\w)", re.I)
    clauses = [clause.strip(" ,") for clause in CLAUSE_BREAK.split(evidence) if clause.strip(" ,")]
    matching = [clause for clause in clauses if value_pattern.search(clause)]
    if len(clauses) == 1:
        evidence = clauses[0]
    elif len(matching) == 1:
        evidence = matching[0]
    result = {**item, "evidence": evidence}
    if not item["must_have"] or role == "hard":
        return result

    # A narrow excerpt such as "coding" must be checked in its surrounding
    # clause, rather than borrowing "must" from another part of the answer.
    enclosing = [clause.strip(" ,") for clause in CLAUSE_BREAK.split(answer_text)
                 if evidence.casefold() in clause.casefold()]
    if len(enclosing) != 1:
        raise InputError("AMBIGUOUS_ANSWER", path, "Hard requirement evidence must identify one supporting clause")
    clause = enclosing[0]
    plain_label = (role == "soft" and question_criterion == item["criterion"] and bool(item["value"].strip())
                   and answer_text.casefold().strip(" .!?") == item["value"].casefold().strip(" .!?")
                   and not re.search(r"\b(?:not|never|without|don't)\b", clause, re.I))
    if OPTIONAL.search(clause) or ((plain_label or PREFERENCE.search(clause) or comparative_direction(clause)) and not REQUIREMENT.search(clause)):
        return {**result, "must_have": False}
    if not REQUIREMENT.search(clause):
        raise InputError("AMBIGUOUS_ANSWER", path, "Hard requirement needs explicit wording in its own clause")
    return {**result, "evidence": clause}

def answer_provenance(answer: dict, member_id: str, snapshot_id: str, source_type: str, evidence: str) -> dict:
    return {
        "participant_id": member_id, "source_question_id": answer["question_id"],
        "source_answer_id": answer.get("answer_id") or f"{snapshot_id}:{member_id}:{answer['question_id']}",
        "source_type": source_type, "evidence": evidence,
    }
