"""Aggregate a "which dates work?" poll without exposing who answered what.

Dates are a separate dimension from the options being ranked: members say
whether each proposed date works, works if needed, or cannot work, and the
shared result is only the per-date counts and the best date.
"""

from __future__ import annotations

from datetime import date

ANSWERS = {"yes", "maybe", "no"}


def _choice_values(question: dict) -> list[str]:
    values = []
    for choice in question.get("choices") or []:
        value = choice.get("choice_id") if isinstance(choice, dict) else choice
        if isinstance(value, str):
            try:
                date.fromisoformat(value)
            except ValueError:
                continue
            values.append(value)
    return sorted(set(values))


def date_poll_summary(questions: list[dict], participants: list[dict]) -> dict | None:
    poll = next((q for q in questions if q.get("answer_format") == "date_poll"), None)
    if poll is None:
        return None
    dates = _choice_values(poll)
    counts = {d: {"date": d, "works": 0, "maybe": 0, "cannot": 0} for d in dates}
    respondents = 0
    for member in participants:
        if not member.get("is_required_for_decision", True) or member.get("response_status") != "complete":
            continue
        answer = next((a for a in member.get("answers", []) if a.get("question_id") == poll["question_id"]), None)
        value = answer.get("value") if isinstance(answer, dict) else None
        if not isinstance(value, dict):
            continue
        respondents += 1
        for day, choice in value.items():
            if day in counts and choice in ANSWERS:
                counts[day][{"yes": "works", "maybe": "maybe", "no": "cannot"}[choice]] += 1
    rows = [counts[d] for d in dates]
    # Most "works" (an "if needed" counts half), then fewest "cannot", then earliest.
    best = min(rows, key=lambda r: (-(r["works"] + r["maybe"] / 2), r["cannot"], r["date"]), default=None) if respondents else None
    return {"question_id": poll["question_id"], "respondents": respondents, "dates": rows,
            "best_date": best["date"] if best else None}
