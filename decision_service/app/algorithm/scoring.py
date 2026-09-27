from __future__ import annotations

from dataclasses import dataclass

from .models import Candidate, Participant, ParticipantPreference, RatingCounts


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: Candidate
    min_rating: int
    average_rating: float
    average_preference_score: float
    rating_counts: RatingCounts


def score_candidates(
    candidates: tuple[Candidate, ...],
    participants: tuple[Participant, ...],
    preferences: tuple[ParticipantPreference, ...],
) -> tuple[ScoredCandidate, ...]:
    required_participants = tuple(
        participant for participant in participants if participant.is_required_for_decision
    )

    return tuple(
        score_candidate(candidate, required_participants, preferences)
        for candidate in candidates
    )


def score_candidate(
    candidate: Candidate,
    participants: tuple[Participant, ...],
    preferences: tuple[ParticipantPreference, ...],
) -> ScoredCandidate:
    ratings = [
        find_rating(candidate, participant, preferences) for participant in participants
    ]

    # Readiness checks should prevent missing ratings from reaching this point.
    if any(rating is None for rating in ratings):
        raise ValueError(f"missing rating for candidate {candidate.candidate_id}")

    numeric_ratings = [rating for rating in ratings if rating is not None]
    average_rating = sum(numeric_ratings) / len(numeric_ratings)

    return ScoredCandidate(
        candidate=candidate,
        min_rating=min(numeric_ratings),
        average_rating=average_rating,
        average_preference_score=100 * average_rating / 4,
        rating_counts=count_ratings(numeric_ratings),
    )


def find_rating(
    candidate: Candidate,
    participant: Participant,
    preferences: tuple[ParticipantPreference, ...],
) -> int | None:
    candidate_match = next(
        (
            preference.rating
            for preference in preferences
            if preference.participant_id == participant.participant_id
            and preference.candidate_id == candidate.candidate_id
        ),
        None,
    )
    if candidate_match is not None:
        return candidate_match

    return next(
        (
            preference.rating
            for preference in preferences
            if preference.participant_id == participant.participant_id
            and preference.activity_id == candidate.activity_id
        ),
        None,
    )


def count_ratings(ratings: list[int]) -> RatingCounts:
    return RatingCounts(
        strongly_dislike=ratings.count(0),
        dislike=ratings.count(1),
        neutral=ratings.count(2),
        like=ratings.count(3),
        love=ratings.count(4),
    )

