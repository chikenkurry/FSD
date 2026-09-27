"""Build all activity and start-time candidates from frozen option facts."""

from __future__ import annotations

from datetime import timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .common import (
    InputError,
    require_in,
    require_instant,
    require_int,
    require_list,
    require_object,
    require_text,
    utc_string,
)


def generate_candidates(
    activities: list[dict], option_revision: str, timezone_name: str, grid_minutes: int = 30
) -> list[dict]:
    try:
        local_zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise InputError("INVALID_TIMEZONE", "planning.timezone", "Unknown IANA timezone") from exc
    step = timedelta(minutes=grid_minutes)
    candidates: list[dict] = []
    seen: set[str] = set()
    activity_ids: set[str] = set()

    for ai, raw_activity in enumerate(activities):
        path = f"planning.activities[{ai}]"
        activity = require_object(raw_activity, path)
        activity_id = require_text(activity.get("activity_id"), f"{path}.activity_id")
        if activity_id in activity_ids:
            raise InputError("DUPLICATE_ID", f"{path}.activity_id", "Duplicate activity ID")
        activity_ids.add(activity_id)
        title = require_text(activity.get("title"), f"{path}.title")
        description = activity.get("description", "")
        if not isinstance(description, str):
            raise InputError("INVALID_TYPE", f"{path}.description", "Expected text")
        duration = require_int(activity.get("duration_minutes"), f"{path}.duration_minutes", minimum=30)
        if duration % grid_minutes:
            raise InputError("INVALID_DURATION", f"{path}.duration_minutes", "Duration must align to the time grid")
        cost = activity.get("estimated_cost_minor")
        if cost is not None:
            require_int(cost, f"{path}.estimated_cost_minor")
        currency = require_text(activity.get("currency"), f"{path}.currency").upper()
        attrs = []
        attr_ids: set[str] = set()
        for xi, raw_attr in enumerate(require_list(activity.get("attributes", []), f"{path}.attributes")):
            attr_path = f"{path}.attributes[{xi}]"
            attr = require_object(raw_attr, attr_path)
            attr_id = require_text(attr.get("attribute_id"), f"{attr_path}.attribute_id")
            if attr_id in attr_ids:
                raise InputError("DUPLICATE_ID", f"{attr_path}.attribute_id", "Duplicate attribute ID")
            attr_ids.add(attr_id)
            attrs.append({"attribute_id": attr_id, "value": require_in(attr.get("value"), {"yes", "no", "unknown"}, f"{attr_path}.value")})

        for wi, raw_window in enumerate(require_list(activity.get("windows"), f"{path}.windows")):
            window_path = f"{path}.windows[{wi}]"
            window = require_object(raw_window, window_path)
            start = require_instant(window.get("start_at"), f"{window_path}.start_at")
            end = require_instant(window.get("end_at"), f"{window_path}.end_at")
            if start >= end:
                raise InputError("INVALID_TIME", window_path, "Window end must follow start")
            if end - start > timedelta(days=14):
                raise InputError("LIMIT_EXCEEDED", window_path, "Window cannot exceed 14 days")
            cursor = start.astimezone(timezone.utc)
            local_cursor = cursor.astimezone(local_zone)
            minutes_to_next = (-local_cursor.minute) % grid_minutes
            if cursor.second or cursor.microsecond:
                minutes_to_next = (minutes_to_next or grid_minutes)
                cursor = cursor.replace(second=0, microsecond=0)
            cursor += timedelta(minutes=minutes_to_next)
            while cursor + timedelta(minutes=duration) <= end:
                local = cursor.astimezone(local_zone)
                if local.minute % grid_minutes == 0 and local.second == 0 and local.microsecond == 0:
                    start_at = utc_string(cursor)
                    candidate_id = f"{activity_id}@{start_at}"
                    if candidate_id not in seen:
                        seen.add(candidate_id)
                        candidates.append({
                            "candidate_id": candidate_id,
                            "activity_id": activity_id,
                            "option_revision": option_revision,
                            "title": title,
                            "description": description,
                            "start_at": start_at,
                            "end_at": utc_string(cursor + timedelta(minutes=duration)),
                            "duration_minutes": duration,
                            "estimated_cost_minor": cost,
                            "currency": currency,
                            "attributes": attrs,
                        })
                        if len(candidates) > 10000:
                            raise InputError("LIMIT_EXCEEDED", "planning.activities", "Too many candidates")
                cursor += step

    return sorted(candidates, key=lambda c: (c["start_at"], c["activity_id"], c["candidate_id"]))
