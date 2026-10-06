"""Compile typed generic preferences, constraints, and missing-fact requests."""

from __future__ import annotations

import re

from .common import InputError, require_object
from .generic_mapping import HARD_RULES, SOFT_RULES, normalize_answer, typed_value


MEMBER_ISSUES = {
    "ROSTER_MISMATCH", "INCOMPLETE_RESPONSE", "MISSING_ANSWER", "AMBIGUOUS_AVAILABILITY",
    "AMBIGUOUS_BUDGET", "AMBIGUOUS_DURATION", "AMBIGUOUS_ANSWER", "CONFIRM_REQUIREMENT",
    "UNIT_MISMATCH", "CONFLICTING_ANSWER",
}


def issue(code: str, path: str, message: str) -> dict:
    return {"code": code, "path": path, "message": message}


def answer_provenance(answer: dict, member_id: str, snapshot_id: str, source_type: str, evidence: str) -> dict:
    return {
        "participant_id": member_id, "source_question_id": answer["question_id"],
        "source_answer_id": answer.get("answer_id") or f"{snapshot_id}:{member_id}:{answer['question_id']}",
        "source_type": source_type, "evidence": evidence,
    }


def compile_answers(entries: list[dict], questions: dict, hard: bool, issues: list[dict]) -> list[dict]:
    groups = {}
    for entry in entries:
        groups.setdefault((entry["participant_id"], entry["question_id"], entry.get("polarity", "prefer")), []).append(entry)
    result = []
    for (member_id, qid, polarity), answers in groups.items():
        question = questions[qid]
        mapping = question["mapping"]
        if mapping["status"] != "resolved":
            continue
        path = f"responses.participants.{member_id}.answers.{qid}"
        original = answers[0]
        provenance = dict(original["provenance"])
        excerpts = list(dict.fromkeys(answer["provenance"]["evidence"] for answer in answers))
        if len(excerpts) > 1:
            provenance["evidence_excerpts"] = excerpts
        raw_values = [answer["value"] for answer in answers]
        try:
            if mapping["attribute_id"] == "availability":
                value, kind = raw_values[0], "available_dates"
            elif isinstance(raw_values[0], dict) and raw_values[0].get("kind") in {"indifferent", "unlimited"}:
                result.append({**provenance, "kind": "indifferent" if not hard else "unlimited",
                               "attribute_id": mapping["attribute_id"], "scope": "all",
                               "status": "explicitly_indifferent" if not hard else "confirmed",
                               "utility_rule": "neutral_v1" if not hard else None,
                               "unit": mapping["unit"]})
                continue
            else:
                if mapping["attribute_id"] == "max_cost" and isinstance(raw_values[0], dict):
                    raw_values = [raw_values[0]["amount"]]
                elif mapping["attribute_id"] == "duration_days" and isinstance(raw_values[0], dict):
                    raw_values = [raw_values[0]["days"]]
                if mapping["value_type"] == "tag_set":
                    raw = [item for value in raw_values for item in (value if isinstance(value, list) else [value])]
                else:
                    if len(raw_values) != 1:
                        raise InputError("CONFLICTING_ANSWER", path, "Scalar question has several different values")
                    raw = raw_values[0]
                value = normalize_answer(raw, mapping, path)
                kind = "attribute_requirement" if hard else "attribute_preference"
            compiled = {
                **provenance, "attribute_id": mapping["attribute_id"], "kind": kind,
                "value_type": mapping["value_type"], "unit": mapping["unit"], "scope": "all",
                "status": "estimated" if provenance["source_type"] == "semantic_model" else "confirmed",
                "polarity": polarity,
            }
            if hard:
                rule = mapping["comparison_rule"]
                if question["role"] != "hard":
                    rules = HARD_RULES[mapping["value_type"]]
                    if len(rules) == 1:
                        rule = next(iter(rules))
                    elif re.search(r"\b(at least|minimum)\b", provenance["evidence"], re.I):
                        rule = "minimum_v1"
                    elif re.search(r"\b(at most|maximum)\b", provenance["evidence"], re.I):
                        rule = "maximum_v1"
                    else:
                        rule = "equals_v1"
                if polarity == "avoid":
                    if mapping["value_type"] in {"number", "decimal"}:
                        raise InputError("AMBIGUOUS_ANSWER", path, "Clarify the numeric boundary instead of an avoided numeric value")
                    rule = "excludes_all_v1" if mapping["value_type"] == "tag_set" else "not_equals_v1"
                compiled.update(required_value=value, constraint_rule=rule)
                confirmation = original.get("confirmation")
                expected = {"attribute_id": mapping["attribute_id"], "required_value": value,
                            "constraint_rule": rule, "unit": mapping["unit"]}
                if provenance["source_type"] == "semantic_model":
                    confirmed = False
                    if isinstance(confirmation, dict) and set(confirmation) == set(expected):
                        try:
                            confirmed_value = confirmation["required_value"] if kind == "available_dates" else normalize_answer(confirmation["required_value"], mapping, path)
                            confirmed = {**confirmation, "required_value": confirmed_value} == expected
                        except InputError:
                            pass
                else:
                    confirmed = True
                compiled["confirmation_status"] = "confirmed" if confirmed else "needs_confirmation"
                compiled["status"] = "confirmed" if confirmed else "needs_confirmation"
                if not confirmed:
                    issues.append(issue("CONFIRM_REQUIREMENT", path, "Confirm the interpreted criterion, rule, value, and unit"))
            else:
                compiled.update(preferred_value=value, utility_rule=mapping["comparison_rule"])
            result.append(compiled)
        except InputError as exc:
            issues.append(exc.as_issue())
    return result


def compile_preparation(handoff: dict, registry: dict, issues: list[dict]) -> dict:
    questions = {q["question_id"]: q for q in handoff["scoring_model"]["questions"]}
    for candidate in handoff["candidates"]:
        facts = []
        for fact in candidate["facts"]:
            definition = registry[fact["criterion"]]
            facts.append({**definition, "value": None if fact["status"] == "unknown" else typed_value(fact["value"], definition["value_type"], "fact.value"),
                          "status": fact["status"], "source": fact["source"], "context": fact.get("context", {})})
        candidate["facts"] = facts
    for question in questions.values():
        mapping = question["mapping"]
        hard = question["role"] == "hard"
        question.update(is_hard_constraint=hard, aggregation="average" if mapping.get("value_type") == "tag_set" else "direct",
                        utility_rule=mapping.get("comparison_rule") if question["role"] == "soft" else None,
                        constraint_rule=mapping.get("comparison_rule") if hard else None,
                        missing_value_policy="unresolved")
    hard_entries = list(handoff["constraints"])
    soft_entries = list(handoff["preferences"])
    # A must-have found in a soft answer retains that question's shared weight
    # for soft values; the confirmed hard value is emitted separately.
    handoff["constraints"] = compile_answers(hard_entries, questions, True, issues)
    handoff["preferences"] = compile_answers(soft_entries, questions, False, issues)
    for question in questions.values():
        counts = [sum(p["source_question_id"] == question["question_id"] and p["participant_id"] == member["participant_id"]
                      for p in handoff["preferences"]) for member in handoff["participants"]]
        if counts and max(counts) > 1:
            question["aggregation"] = "average"
    handoff["criteria"] = [registry[aid] for aid in sorted(registry)]
    handoff["fact_requests"] = []
    for candidate in handoff["candidates"]:
        estimated = [f["attribute_id"] for f in candidate["facts"] if f["status"] == "estimated"
                     and (any(q["criterion"] == f["attribute_id"] and (q["role"] == "hard" or q["weight"])
                              for q in questions.values())
                          or any(c["attribute_id"] == f["attribute_id"] for c in handoff["constraints"]))]
        for aid in sorted(set(candidate["missing_criteria"] + estimated)):
            related = [q for q in questions.values() if q["criterion"] == aid]
            definition = registry.get(aid, {"attribute_id": aid, "value_type": None, "unit": None})
            handoff["fact_requests"].append({
                "option_id": candidate["option_id"], **definition,
                "source_question_ids": [q["question_id"] for q in related],
                "priority": "hard_constraint" if any(q["role"] == "hard" for q in related) else "soft_preference",
                "required_status": "confirmed", "context": {"cost_scope": handoff["context"]["cost_scope"]} if aid == "max_cost" else {},
            })
    if any(q["criterion"] == "max_cost" for q in questions.values()):
        for scenario in handoff["scenario_requests"]:
            if scenario["cost_evidence_status"] != "confirmed":
                handoff["fact_requests"].append({
                    "option_id": scenario["option_id"], **registry["max_cost"], "scope": "scenario",
                    "source_question_ids": [q["question_id"] for q in questions.values() if q["criterion"] == "max_cost"],
                    "priority": "hard_constraint", "required_status": "confirmed",
                    "context": {key: scenario[key] for key in ("duration_days", "earliest_start_date", "latest_start_date")}
                               | {"cost_scope": handoff["context"]["cost_scope"]},
                })
    for member in handoff["participants"]:
        for question in questions.values():
            if question["role"] != "soft" or not question["weight"] or question["mapping"]["status"] != "resolved":
                continue
            if not any(p["participant_id"] == member["participant_id"] and p["source_question_id"] == question["question_id"] for p in handoff["preferences"]):
                path = f"responses.participants.{member['participant_id']}.answers.{question['question_id']}"
                if any(i["path"] == path for i in issues):
                    continue
                issues.append(issue("MISSING_ANSWER", path,
                                    "An active soft question needs a normalized answer or explicit indifference"))
    processing_issues = [i for i in issues if i["code"] != "EXECUTION_ADAPTER_REQUIRED"]
    handoff["status"] = "needs_clarification" if any(i["code"] in MEMBER_ISSUES for i in processing_issues) else "needs_information" if processing_issues else "ready"
    validate_preparation(handoff)
    return handoff


def validate_preparation(handoff: dict) -> None:
    """Reject invalid references and declarations before exporting preparation."""
    require_object(handoff, "preparation")
    registry = {entry["attribute_id"]: entry for entry in handoff["criteria"]}
    participants = {p["participant_id"] for p in handoff["participants"]}
    questions = {q["question_id"]: q for q in handoff["scoring_model"]["questions"]}
    for question in questions.values():
        mapping = question["mapping"]
        if mapping["status"] != "resolved":
            continue
        if mapping["attribute_id"] not in registry or registry[mapping["attribute_id"]]["unit"] != mapping["unit"]:
            raise InputError("INVALID_PREPARATION", "preparation.questions", "Question mapping has an unknown criterion or unit")
        allowed = {SOFT_RULES.get(mapping["value_type"])} if question["role"] == "soft" else HARD_RULES[mapping["value_type"]]
        if mapping["comparison_rule"] not in allowed:
            raise InputError("UNSUPPORTED_UTILITY_RULE", "preparation.questions", "Comparison does not support the question type")
    seen_requirements = {}
    for collection in (handoff["preferences"], handoff["constraints"]):
        seen = set()
        for entry in collection:
            key = (entry["participant_id"], entry["source_question_id"], entry["attribute_id"], entry.get("polarity", "prefer"))
            if key in seen or key[0] not in participants or key[1] not in questions or key[2] not in registry:
                raise InputError("INVALID_PREPARATION", "preparation", "Duplicate or unknown normalized answer reference")
            seen.add(key)
            if not entry["source_answer_id"] or not entry["evidence"]:
                raise InputError("INVALID_PREPARATION", "preparation", "Normalized answer needs provenance")
            definition = registry[key[2]]
            if entry.get("unit") != definition["unit"]:
                raise InputError("UNIT_MISMATCH", "preparation", "Answer unit differs from its criterion")
            if "required_value" in entry and entry["confirmation_status"] == "confirmed":
                conflict_key = (entry["participant_id"], entry["attribute_id"], entry["constraint_rule"])
                if conflict_key in seen_requirements and seen_requirements[conflict_key] != entry["required_value"]:
                    raise InputError("CONFLICTING_ANSWER", "preparation.constraints", "Confirmed answers give different limits for the same criterion")
                seen_requirements[conflict_key] = entry["required_value"]
