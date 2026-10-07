"""Compile typed generic preferences, constraints, and missing-fact requests."""

from __future__ import annotations

import re

from .common import InputError, issue
from .generic_mapping import HARD_RULES, normalize_answer, typed_value
from .generic_values import BOUND_RULES, numeric_semantics, preference_range
from .generic_validation import validate_preparation
from .member_importance import compile_member_weights


MEMBER_ISSUES = {
    "ROSTER_MISMATCH", "INCOMPLETE_RESPONSE", "MISSING_ANSWER", "AMBIGUOUS_AVAILABILITY",
    "AMBIGUOUS_BUDGET", "AMBIGUOUS_DURATION", "AMBIGUOUS_ANSWER", "CONFIRM_REQUIREMENT",
    "UNIT_MISMATCH", "CONFLICTING_ANSWER",
    "AMBIGUOUS_IMPORTANCE", "CONFLICTING_IMPORTANCE",
    "UNRESOLVED_ANSWER_MAPPING",
    "AMBIGUOUS_CANONICAL_LABEL",
}


def compile_answers(entries: list[dict], questions: dict, hard: bool, issues: list[dict]) -> list[dict]:
    groups = {}
    for entry in entries:
        groups.setdefault((entry["participant_id"], entry["question_id"], entry["criterion"], entry.get("polarity", "prefer")), []).append(entry)
    result = []
    for (member_id, qid, aid, polarity), answers in groups.items():
        question = questions[qid]
        mapping = answers[0].get("mapping", question["mapping"])
        if mapping["status"] != "resolved":
            issues.append(issue("UNRESOLVED_ANSWER_MAPPING", f"responses.participants.{member_id}.answers.{qid}",
                                f"Criterion {aid} needs a supported comparison or a numeric scale"))
            continue
        path = f"responses.participants.{member_id}.answers.{qid}"
        original = answers[0]
        provenance = dict(original["provenance"])
        excerpts = list(dict.fromkeys(answer["provenance"]["evidence"] for answer in answers))
        if len(excerpts) > 1:
            provenance["evidence_excerpts"] = excerpts
        raw_values = [answer["value"] for answer in answers]
        intents = {answer.get("intent", "match") for answer in answers}
        intent = answers[0].get("intent", "match")
        try:
            if len(intents) != 1:
                raise InputError("CONFLICTING_ANSWER", path, "Criterion has conflicting preference directions or targets")
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
                if intent in {"maximize", "minimize"}:
                    if hard:
                        raise InputError("AMBIGUOUS_ANSWER", path, "A hard numeric requirement needs a bound, not a direction")
                    value = None
                elif intent == "range":
                    if any(raw != raw_values[0] for raw in raw_values):
                        raise InputError("CONFLICTING_ANSWER", path, "Criterion has several different preferred ranges")
                    value = numeric_semantics(raw_values[0], mapping, path, "range")[1]
                elif mapping["value_type"] == "tag_set":
                    raw = [item for value in raw_values for item in (value if isinstance(value, list) else [value])]
                    value = normalize_answer(raw, mapping, path)
                else:
                    if any(raw != raw_values[0] for raw in raw_values):
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
                rule = BOUND_RULES.get(intent, "within_range_v1" if intent == "range" else mapping["comparison_rule"])
                if question["role"] != "hard" and "mapping" not in original:
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
                    confirmations = confirmation if isinstance(confirmation, list) else [confirmation]
                    for confirmation in confirmations:
                        if not isinstance(confirmation, dict) or set(confirmation) != set(expected):
                            continue
                        try:
                            if kind == "available_dates":
                                confirmed_value = confirmation["required_value"]
                            elif intent == "range":
                                confirmed_value = numeric_semantics(confirmation["required_value"], mapping, path, "range")[1]
                            else:
                                confirmed_value = normalize_answer(confirmation["required_value"], mapping, path)
                            confirmed = confirmed or {**confirmation, "required_value": confirmed_value} == expected
                        except InputError:
                            pass
                else:
                    confirmed = True
                compiled["confirmation_status"] = "confirmed" if confirmed else "needs_confirmation"
                compiled["status"] = "confirmed" if confirmed else "needs_confirmation"
                if not confirmed:
                    issues.append(issue("CONFIRM_REQUIREMENT", path, "Confirm the interpreted criterion, rule, value, and unit"))
            else:
                compiled.update(preferred_value=preference_range(intent, value) if intent in BOUND_RULES else value,
                                utility_rule=mapping["comparison_rule"], utility_parameters=mapping.get("parameters", {}))
                if intent in {"maximize", "minimize"}:
                    compiled["direction"] = intent
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
    compile_member_weights(handoff, handoff.pop("importance_entries", []), issues)
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
                          or any(c["attribute_id"] == f["attribute_id"] for c in handoff["constraints"])
                          or any(p["attribute_id"] == f["attribute_id"] and questions[p["source_question_id"]]["weight"]
                                 for p in handoff["preferences"]))]
        for aid in sorted(set(candidate["missing_criteria"] + estimated)):
            related = [q for q in questions.values() if q["criterion"] == aid or any(
                e["question_id"] == q["question_id"] and e["criterion"] == aid for e in hard_entries + soft_entries)]
            definition = registry.get(aid, {"attribute_id": aid, "value_type": None, "unit": None})
            handoff["fact_requests"].append({
                "option_id": candidate["option_id"], **definition,
                "source_question_ids": [q["question_id"] for q in related],
                "priority": "hard_constraint" if any(q["role"] == "hard" for q in related) or any(e["criterion"] == aid for e in hard_entries) else "soft_preference",
                "required_status": "confirmed", "context": {"cost_scope": handoff["context"]["cost_scope"]} if aid == "max_cost" else {},
            })
    if any(q["criterion"] == "max_cost" for q in questions.values()) or any(e["criterion"] == "max_cost" for e in hard_entries + soft_entries):
        for scenario in handoff["scenario_requests"]:
            if scenario["cost_evidence_status"] != "confirmed":
                handoff["fact_requests"].append({
                    "option_id": scenario["option_id"], **registry["max_cost"], "scope": "scenario",
                    "source_question_ids": [q["question_id"] for q in questions.values() if q["criterion"] == "max_cost" or any(e["question_id"] == q["question_id"] and e["criterion"] == "max_cost" for e in hard_entries + soft_entries)],
                    "priority": "hard_constraint", "required_status": "confirmed",
                    "context": {key: scenario[key] for key in ("duration_days", "earliest_start_date", "latest_start_date")}
                               | {"cost_scope": handoff["context"]["cost_scope"]},
                })
    for member in handoff["participants"]:
        for question in questions.values():
            path = f"responses.participants.{member['participant_id']}.answers.{question['question_id']}"
            if question["role"] == "hard" and question["required"]:
                has_constraint = any(c["participant_id"] == member["participant_id"]
                                     and c["source_question_id"] == question["question_id"]
                                     and c["attribute_id"] == question["criterion"] for c in handoff["constraints"])
                if not has_constraint and not any(i["path"] == path for i in issues):
                    issues.append(issue("AMBIGUOUS_ANSWER", path, "Required hard question needs a normalized requirement for its criterion"))
            if question["role"] != "soft" or not question["weight"] or question["mapping"]["status"] != "resolved":
                continue
            if not any(p["participant_id"] == member["participant_id"] and p["source_question_id"] == question["question_id"] for p in handoff["preferences"]):
                if any(c["participant_id"] == member["participant_id"] and c["source_question_id"] == question["question_id"] for c in handoff["constraints"]):
                    continue
                if any(i["path"] == path for i in issues):
                    continue
                issues.append(issue("MISSING_ANSWER", path,
                                    "An active soft question needs a normalized answer or explicit indifference"))
    processing_issues = [i for i in issues if i["code"] != "EXECUTION_ADAPTER_REQUIRED"]
    handoff["status"] = "needs_clarification" if any(i["code"] in MEMBER_ISSUES for i in processing_issues) else "needs_information" if processing_issues else "ready"
    validate_preparation(handoff)
    return handoff
