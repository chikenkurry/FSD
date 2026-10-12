"""Validate service identities and map Participation records to processor inputs."""
from copy import deepcopy
from decimal import Decimal
import re

from decision_service.preprocessing.money import decimal_string


class SnapshotError(ValueError):
    pass


def _validate_metadata(snapshot: dict) -> None:
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != "planning-snapshot-v1":
        raise SnapshotError("Expected planning-snapshot-v1")
    for key in ("plan_id", "round_id", "option_snapshot_id", "cost_scope"):
        if not isinstance(snapshot.get(key), str) or not snapshot[key].strip():
            raise SnapshotError(f"Missing {key}")
    if type(snapshot.get("option_revision")) is not int or snapshot["option_revision"] < 1:
        raise SnapshotError("Invalid option revision")
    if snapshot.get("execution_mode", "options") not in {"options", "scheduled", "scenarios"}:
        raise SnapshotError("Unknown execution mode")
    currency = snapshot.get("currency")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        raise SnapshotError("Currency must be a three-letter uppercase code")
    digits = snapshot.get("currency_minor_digits")
    if type(digits) is not int or not 0 <= digits <= 9:
        raise SnapshotError("Invalid currency precision")
    roster = snapshot.get("roster")
    if (not isinstance(roster, list) or not 1 <= len(roster) <= 30
            or any(not isinstance(pid, str) or not pid for pid in roster) or len(set(roster)) != len(roster)):
        raise SnapshotError("Published roster needs 1-30 unique member IDs")
    for key, identity, limit in (("questions", "question_id", 100), ("options", "option_id", 8)):
        rows = snapshot.get(key)
        if not isinstance(rows, list) or not 1 <= len(rows) <= limit:
            raise SnapshotError(f"Invalid {key} list")
        ids = [row.get(identity) for row in rows if isinstance(row, dict)]
        if len(ids) != len(rows) or any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
            raise SnapshotError(f"Invalid or duplicate {identity}")


def map_snapshots(planning: dict, responses: dict) -> tuple[dict, dict]:
    if not isinstance(planning, dict) or not isinstance(responses, dict):
        raise SnapshotError("Snapshots must be objects")
    if planning.get("schema_version") != "planning-snapshot-v1" or responses.get("schema_version") != "response-snapshot-v2":
        raise SnapshotError("Unsupported service snapshot version")
    _validate_metadata(planning)
    for key in ("plan_id", "round_id"):
        if not planning.get(key) or planning[key] != responses.get(key):
            raise SnapshotError(f"Snapshot {key} mismatch")
    if type(responses.get("option_revision")) is not int or planning["option_revision"] != responses["option_revision"]:
        raise SnapshotError("Option revision mismatch")
    if planning.get("option_snapshot_id") != responses.get("option_snapshot_id"):
        raise SnapshotError("Option snapshot mismatch")
    if not isinstance(responses.get("snapshot_id"), str) or not responses["snapshot_id"]:
        raise SnapshotError("Response snapshot ID required")
    participants = responses.get("participants")
    roster = planning.get("roster")
    if not isinstance(participants, list) or not isinstance(roster, list) or not roster:
        raise SnapshotError("Snapshots need a roster and participants")
    ids = [p.get("participant_id") for p in participants if isinstance(p, dict)]
    if (len(ids) != len(participants) or any(not isinstance(pid, str) for pid in ids)
            or len(set(ids)) != len(ids) or set(ids) != set(roster)):
        raise SnapshotError("Response roster must match the published roster exactly")
    if (responses.get("currency") != planning["currency"] or type(responses.get("minor_digits")) is not int
            or responses["minor_digits"] != planning["currency_minor_digits"]):
        raise SnapshotError("Currency or minor-unit convention mismatch")
    plan = deepcopy(planning)
    plan["option_revision"] = str(plan["option_revision"])
    reply = {"round_id": plan["round_id"], "option_revision": plan["option_revision"],
             "response_snapshot_id": responses["snapshot_id"], "participants": []}
    known = {q["question_id"] for q in plan["questions"]}
    rows = responses.get("constraints")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise SnapshotError("Constraints must be a list of member records")
    if any(not isinstance(c.get("participant_id"), str) for c in rows):
        raise SnapshotError("Constraint records need member IDs")
    constraints = {c["participant_id"]: c for c in rows}
    if len(constraints) != len(rows) or set(constraints) != set(roster):
        raise SnapshotError("Constraint roster must match the published roster exactly")
    for row in rows:
        budget = row.get("budget", {})
        if not isinstance(budget, dict) or budget.get("kind", "missing") not in {"limited", "unlimited", "missing"}:
            raise SnapshotError("Invalid member budget")
        if budget.get("currency", plan["currency"]) != plan["currency"]:
            raise SnapshotError("Member budget currency mismatch")
        flags = row.get("activity_flags", [])
        options = {option["option_id"] for option in plan["options"]}
        if (not isinstance(flags, list) or any(not isinstance(flag, dict)
                or flag.get("activity_id") not in options or flag.get("flag") not in {"cannot_join", "needs_information"} for flag in flags)):
            raise SnapshotError("Invalid member activity flag")
    budget_question = "__participation_budget"
    uses_budget = any(c.get("budget", {}).get("kind") in {"limited", "unlimited"} for c in constraints.values())
    if uses_budget:
        if plan.get("cost_scope") != "per_person_total":
            raise SnapshotError("Participation budgets require per_person_total cost scope")
        plan["questions"].append({"question_id": budget_question, "label": "Maximum per-person budget?",
                                  "role": "hard", "criterion": "max_cost", "relevance": 0,
                                  "numeric_intent": "maximum", "required": False})
    for member in participants:
        if member.get("response_status") not in {"complete", "incomplete", "stale"}:
            raise SnapshotError("Invalid member response status")
        answers = deepcopy(member.get("answers", []))
        if not isinstance(answers, list):
            raise SnapshotError("Member answers must be a list")
        seen = set()
        for answer in answers:
            if not isinstance(answer, dict) or answer.get("question_id") not in known or answer["question_id"] in seen or "value" not in answer:
                raise SnapshotError("Unknown, duplicate or malformed question answer")
            seen.add(answer["question_id"])
            answer["answer_id"] = f"{responses['snapshot_id']}:{member['participant_id']}:{answer['question_id']}"
        budget = constraints.get(member["participant_id"], {}).get("budget", {})
        if uses_budget and budget.get("kind") in {"limited", "unlimited"}:
            if budget["kind"] == "limited":
                cap = budget.get("max_cost_minor")
                if type(cap) is not int or cap < 0:
                    raise SnapshotError("Invalid budget cap")
                value = decimal_string(format(Decimal(cap).scaleb(-responses["minor_digits"]), "f"), "participation.budget")
            else:
                value = "no limit"
            answers.append({"question_id": budget_question, "answer_id": f"{responses['snapshot_id']}:{member['participant_id']}:budget", "value": value})
        reply["participants"].append({"participant_id": member["participant_id"],
                                       "response_status": member.get("response_status", "incomplete"), "answers": answers})
    return plan, reply


def validate_planning_snapshot(snapshot: dict) -> None:
    from decision_service.preprocessing import preprocess
    _validate_metadata(snapshot)
    # Exercise the same structural validation that later processing uses.
    planning = deepcopy(snapshot)
    planning["option_revision"] = str(snapshot["option_revision"])
    reply = {"round_id": snapshot["round_id"], "option_revision": planning["option_revision"],
             "response_snapshot_id": "definition-validation", "participants": [
                 {"participant_id": pid, "response_status": "complete", "answers": []} for pid in snapshot.get("roster", [])]}
    policy = {"group_objective": snapshot["group_objective"]} if snapshot.get("group_objective") else None
    result = preprocess(planning, reply, policy=policy)
    if result["status"] == "invalid_input":
        raise SnapshotError(result["issues"][0]["message"])
