"""Build bounded, whole-day scenarios from supplied member availability."""

from __future__ import annotations

import math
from datetime import date, timedelta

from .common import InputError, require_int
from .durations import parse_duration_choice


DEFAULT_MAX_SCENARIO_REQUESTS = 10_000


def _shared_windows(roster: list[str], constraints: list[dict]) -> list[tuple[date, date]]:
    by_member = {member_id: [] for member_id in roster}
    for constraint in constraints:
        if constraint["criterion"] == "availability":
            by_member[constraint["participant_id"]].extend(constraint["value"])
    if not roster or any(not windows for windows in by_member.values()):
        return []
    common = {(date.fromisoformat(w["start_date"]), date.fromisoformat(w["end_date"])) for w in by_member[roster[0]]}
    for member_id in roster[1:]:
        other = [(date.fromisoformat(w["start_date"]), date.fromisoformat(w["end_date"])) for w in by_member[member_id]]
        common = {(max(a, c), min(b, d)) for a, b in common for c, d in other if max(a, c) <= min(b, d)}
        if not common:
            break
    return sorted(common)


def _durations(questions: list[dict], preferences: list[dict], longest_window: int, limit: int) -> list[int]:
    durations = set()
    for question in questions:
        if question["criterion"] == "duration_days":
            durations.update(days for label in question["choices"].values()
                             if (days := parse_duration_choice(label)) is not None and days <= longest_window)
    for preference in preferences:
        if preference["criterion"] != "duration_days":
            continue
        value = preference["value"]
        if isinstance(value, dict) and value.get("kind") == "preferred":
            value = value["days"]
        if type(value) in {int, float} and value == int(value):
            if 1 <= value <= longest_window:
                durations.add(int(value))
        elif preference.get("intent") == "range":
            lower, upper = value.get("lower"), value.get("upper")
            if lower is None or upper is None:
                continue
            first = math.ceil(lower) + int(not value["lower_inclusive"] and lower == math.ceil(lower))
            last = math.floor(upper) - int(not value["upper_inclusive"] and upper == math.floor(upper))
            first, last = max(1, first), min(longest_window, last)
            if last - first + 1 > limit:
                raise InputError("LIMIT_EXCEEDED", "responses.duration", "Duration range produces too many scenarios")
            durations.update(range(first, last + 1))
        if len(durations) > limit:
            raise InputError("LIMIT_EXCEEDED", "responses.duration", "Too many distinct scenario durations")
    return sorted(durations)


def build_scenario_requests(candidates: list[dict], roster: list[str], constraints: list[dict],
                            preferences: list[dict], questions: list[dict], *,
                            max_requests: int = DEFAULT_MAX_SCENARIO_REQUESTS) -> list[dict]:
    require_int(max_requests, "policy.max_scenario_requests", minimum=1)
    windows = _shared_windows(roster, constraints)
    if not candidates or not windows:
        return []
    longest = max((end - start).days + 1 for start, end in windows)
    durations = _durations(questions, preferences, longest, max_requests)
    requests = []
    for candidate in candidates:
        for days in durations:
            for start, end in windows:
                if days > (end - start).days + 1:
                    continue
                if len(requests) == max_requests:
                    raise InputError("LIMIT_EXCEEDED", "preparation.scenario_requests", "Scenario request limit exceeded")
                requests.append({"option_id": candidate["option_id"], "duration_days": days,
                                 "earliest_start_date": start.isoformat(),
                                 "latest_start_date": (end - timedelta(days=days - 1)).isoformat(),
                                 "cost_evidence_status": "unknown"})
    return requests
