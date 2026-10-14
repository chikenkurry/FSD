"""A job-local monotonic budget, also respected by individual model transports."""
from contextvars import ContextVar
import time

deadline = ContextVar("decision_deadline", default=None)


def remaining_timeout(limit: float) -> float:
    ends = deadline.get()
    if ends is None:
        return limit
    remaining = ends - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Execution deadline exceeded")
    return min(limit, remaining)
