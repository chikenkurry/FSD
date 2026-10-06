"""Shared validation helpers for the preprocessing boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Collection


class InputError(ValueError):
    def __init__(self, code: str, path: str, message: str):
        super().__init__(message)
        self.code = code
        self.path = path
        self.message = message

    def as_issue(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


def require_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError("INVALID_TYPE", path, "Expected an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise InputError("INVALID_TYPE", path, "Expected a list")
    return value


def require_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError("INVALID_TYPE", path, "Expected non-empty text")
    return value.strip()


def require_int(value: Any, path: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise InputError("INVALID_VALUE", path, f"Expected an integer >= {minimum}")
    return value


def require_in(value: Any, options: Collection[str], path: str) -> str:
    if not isinstance(value, str) or value not in options:
        raise InputError("INVALID_VALUE", path, f"Expected one of {sorted(options)}")
    return value


def require_instant(value: Any, path: str) -> datetime:
    raw = require_text(value, path)
    try:
        result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputError("INVALID_TIME", path, "Expected an ISO 8601 timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise InputError("INVALID_TIME", path, "Timestamp must include a UTC offset")
    return result


def utc_string(value: datetime) -> str:
    from datetime import timezone

    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
