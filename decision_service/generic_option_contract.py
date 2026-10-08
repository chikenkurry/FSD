"""Contract checks for the initial generic option executor.

This is intentionally narrower than the generic preparation packet.  It makes
the executable subset explicit while numeric, tag-set, avoidance, and scenario
rules are added in later increments.
"""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "generic-option-v1"
SUPPORTED_VALUE_TYPES = {"category", "boolean", "number", "decimal", "tag_set"}
SUPPORTED_SOFT_RULES = {
    "attribute_match_v1", "neutral_v1", "numeric_target_v1",
    "numeric_maximize_v1", "numeric_minimize_v1", "numeric_range_v1",
    "tag_overlap_v1",
}
SUPPORTED_HARD_RULES = {
    "equals_v1", "not_equals_v1", "maximum_v1", "minimum_v1",
    "less_than_v1", "greater_than_v1", "within_range_v1",
    "contains_all_v1", "excludes_all_v1",
}


class ContractError(ValueError):
    pass


def validate_handoff(handoff: dict[str, Any]) -> None:
    if not isinstance(handoff, dict):
        raise ContractError("Handoff must be an object")
    if handoff.get("context", {}).get("schema_version") != SCHEMA_VERSION:
        raise ContractError("Unsupported generic option schema version")
    for field in ("candidates", "participants", "constraints", "preferences"):
        if not isinstance(handoff.get(field), list):
            raise ContractError(f"{field} must be a list")
    if not handoff["candidates"] or not handoff["participants"]:
        raise ContractError("At least one candidate and participant are required")
    option_ids = [item.get("option_id") for item in handoff["candidates"]]
    if any(not isinstance(option_id, str) or not option_id for option_id in option_ids) or len(set(option_ids)) != len(option_ids):
        raise ContractError("Candidates need unique option_id values")
    participant_ids = [item.get("participant_id") for item in handoff["participants"]]
    if any(not isinstance(pid, str) or not pid for pid in participant_ids) or len(set(participant_ids)) != len(participant_ids):
        raise ContractError("Participants need unique participant_id values")
    weights = handoff.get("scoring_model", {}).get("member_weights")
    if not isinstance(weights, list):
        raise ContractError("scoring_model.member_weights must be a list")
