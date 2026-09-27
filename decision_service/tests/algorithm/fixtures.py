from __future__ import annotations

from datetime import datetime

from app.algorithm import (
    BudgetConstraint,
    Candidate,
    DecisionAlgorithmInput,
    DecisionContext,
    Participant,
    ParticipantConstraint,
    ParticipantPreference,
    TimeInterval,
)


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def project_plan_fixture() -> DecisionAlgorithmInput:
    participants = tuple(
        Participant(participant_id=f"p{index}", response_status="complete")
        for index in range(1, 7)
    )

    candidates = (
        Candidate(
            candidate_id="board_game_cafe_fri_1900",
            activity_id="board_game_cafe",
            option_revision="1",
            title="Board-game cafe",
            start_at=dt("2026-10-02T19:00:00+08:00"),
            end_at=dt("2026-10-02T21:00:00+08:00"),
            duration_minutes=120,
            estimated_cost_minor=2000,
            currency="SGD",
        ),
        Candidate(
            candidate_id="picnic_sat_1400",
            activity_id="picnic",
            option_revision="1",
            title="Picnic",
            start_at=dt("2026-10-03T14:00:00+08:00"),
            end_at=dt("2026-10-03T16:00:00+08:00"),
            duration_minutes=120,
            estimated_cost_minor=1500,
            currency="SGD",
        ),
        Candidate(
            candidate_id="dinner_fri_1900",
            activity_id="dinner",
            option_revision="1",
            title="Dinner",
            start_at=dt("2026-10-02T19:00:00+08:00"),
            end_at=dt("2026-10-02T21:00:00+08:00"),
            duration_minutes=120,
            estimated_cost_minor=3500,
            currency="SGD",
        ),
    )

    budget_caps = (4000, 3000, 3500, 2500, 3000, 5000)
    constraints = tuple(
        ParticipantConstraint(
            participant_id=f"p{index}",
            availability=(
                TimeInterval(
                    start_at=dt("2026-10-02T19:00:00+08:00"),
                    end_at=dt("2026-10-02T21:00:00+08:00"),
                ),
                *(
                    ()
                    if index == 2
                    else (
                        TimeInterval(
                            start_at=dt("2026-10-03T14:00:00+08:00"),
                            end_at=dt("2026-10-03T16:00:00+08:00"),
                        ),
                    )
                ),
            ),
            budget=BudgetConstraint(
                kind="limited",
                max_cost_minor=budget_caps[index - 1],
                currency="SGD",
            ),
        )
        for index in range(1, 7)
    )

    ratings_by_activity = {
        "board_game_cafe": (4, 3, 3, 2, 4, 3),
        "picnic": (4, 4, 3, 3, 4, 4),
        "dinner": (4, 4, 4, 4, 4, 4),
    }
    preferences = tuple(
        ParticipantPreference(
            participant_id=f"p{participant_index}",
            activity_id=activity_id,
            rating=rating,
        )
        for activity_id, ratings in ratings_by_activity.items()
        for participant_index, rating in enumerate(ratings, start=1)
    )

    return DecisionAlgorithmInput(
        context=DecisionContext(
            round_id="round_1",
            option_snapshot_id="options_1",
            response_snapshot_id="responses_1",
            timezone="Asia/Singapore",
        ),
        candidates=candidates,
        participants=participants,
        constraints=constraints,
        preferences=preferences,
    )

