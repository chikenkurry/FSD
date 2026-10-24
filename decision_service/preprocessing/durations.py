"""Validate calendar-day durations and parse offered duration choices."""

from __future__ import annotations

import re
from decimal import Decimal

from .common import InputError


def validate_duration(value: object, path: str, *, interval: bool = False) -> None:
    endpoints = (value.get("lower"), value.get("upper")) if interval else (value,)
    for endpoint in endpoints:
        if endpoint is None:
            continue
        number = Decimal(str(endpoint))
        if number < 1 or (not interval and number != number.to_integral_value()):
            raise InputError("AMBIGUOUS_DURATION", path, "Specify positive whole days or a range containing whole days")


def parse_duration_choice(text: str) -> int | None:
    match = re.fullmatch(r"\s*(\d+)\s*(?:days?)?\s*", text, re.I)
    if match and int(match.group(1)) > 0:
        return int(match.group(1))
    return None
