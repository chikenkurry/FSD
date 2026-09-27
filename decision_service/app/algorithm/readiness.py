from __future__ import annotations

from dataclasses import dataclass

from .models import ExplanationCode, Participant


@dataclass(frozen=True)
class ReadinessResult:
    ok: bool
    explanation_codes: tuple[ExplanationCode, ...] = ()


def check_required_participant_readiness(
    participants: tuple[Participant, ...],
) -> ReadinessResult:
    codes: set[ExplanationCode] = set()

    for participant in participants:
        if not participant.is_required_for_decision:
            continue
        if participant.response_status == "complete":
            continue
        if participant.response_status == "stale":
            codes.add(ExplanationCode.STALE_RESPONSE)
        elif participant.response_status == "needs_clarification":
            codes.add(ExplanationCode.NEEDS_CLARIFICATION)
        else:
            codes.add(ExplanationCode.INCOMPLETE_RESPONSE)

    return ReadinessResult(ok=not codes, explanation_codes=tuple(sorted(codes)))

