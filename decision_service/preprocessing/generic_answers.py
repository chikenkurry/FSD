"""Parse structured generic answers and ground model interpretations."""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from .common import InputError, require_in, require_list, require_object, require_text
from .generic_mapping import normalize_answer, token
from .generic_evidence import scoped_interpretation
from .generic_preparation import answer_provenance
from .semantics import SemanticServiceError, validate_sparse_answer_assessment, validate_sparse_dates


NO_PREFERENCE = {"anything", "fine with anything", "no preference", "none", "either", "either is fine", "anything is fine"}
DATE_RANGE_RE = re.compile(r"\s*(\d{4}-\d{2}-\d{2})(?:\s*(?:to|through|until|–|—| - )\s*(\d{4}-\d{2}-\d{2}))?\s*", re.I)


def _issue(code: str, path: str, message: str) -> dict:
    return {"code": code, "path": path, "message": message}


def _answer_text(value: object, question: dict, path: str) -> str:
    if isinstance(value, dict):
        choice_id = require_text(value.get("choice_id"), f"{path}.choice_id")
        if choice_id not in question["choices"]:
            raise InputError("UNKNOWN_CHOICE", path, "Answer references a choice outside this question")
        return question["choices"][choice_id]
    if type(value) in {int, float, bool}:
        return json.dumps(value)
    if isinstance(value, list):
        return ", ".join(_answer_text(item, question, path) for item in value)
    text = require_text(value, path)
    if question["choices"] and text not in question["choices"].values() and text not in question["choices"]:
        raise InputError("UNKNOWN_CHOICE", path, "Answer must use a declared choice")
    return question["choices"].get(text, text)



def _dates(value: object, path: str) -> list[dict] | None:
    if isinstance(value, list):
        intervals = []
        for i, raw in enumerate(value):
            item = require_object(raw, f"{path}[{i}]")
            start = require_text(item.get("start_date"), f"{path}[{i}].start_date")
            end = require_text(item.get("end_date"), f"{path}[{i}].end_date")
            try:
                if date.fromisoformat(start) > date.fromisoformat(end):
                    raise ValueError
            except ValueError as exc:
                raise InputError("INVALID_DATE", f"{path}[{i}]", "Expected ordered ISO dates") from exc
            intervals.append({"start_date": start, "end_date": end})
        return intervals or None
    text = require_text(value, path)
    match = DATE_RANGE_RE.fullmatch(text)
    if match is None:
        return None
    try:
        start = date.fromisoformat(match.group(1))
        end = date.fromisoformat(match.group(2) or match.group(1))
    except ValueError:
        return None
    if start > end:
        return None
    return [{"start_date": start.isoformat(), "end_date": end.isoformat()}]



def _budget(text: str, currency: str | None) -> dict | None:
    normalized = text.casefold().strip()
    if normalized in {"unlimited", "no limit", "no budget limit"}:
        return {"kind": "unlimited"}
    match = re.fullmatch(r"(?:(?P<prefix>[a-z]{3}|[$£€])\s*)?(?P<amount>[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?P<multiplier>k)?\s*(?P<suffix>[a-z]{3})?", normalized)
    if not match:
        return None
    explicit = match.group("suffix") or match.group("prefix")
    if explicit and explicit not in {"$", "£", "€"} and currency and explicit.upper() != currency:
        return None
    if explicit in {"£", "€"} and currency and {"£": "GBP", "€": "EUR"}[explicit] != currency:
        return None
    if explicit == "$" and currency and currency not in {"SGD", "USD", "CAD", "AUD", "NZD", "HKD"}:
        return None
    try:
        amount = Decimal(match.group("amount").replace(",", ""))
        if match.group("multiplier"):
            amount *= 1000
    except InvalidOperation:
        return None
    if amount < 0:
        return None
    return {"kind": "limited", "amount": str(amount), "currency": currency}



def _duration(text: str) -> dict | None:
    normalized = text.casefold().strip()
    if normalized in NO_PREFERENCE:
        return {"kind": "indifferent"}
    match = re.fullmatch(r"(\d+)\s*(?:days?)?", normalized)
    if not match or not 1 <= int(match.group(1)) <= 365:
        return None
    return {"kind": "preferred", "days": int(match.group(1))}


def process_answers(responses: dict, roster: list[str], questions: list[dict], candidates: list[dict],
                    context: dict, semantic_provider, extracted: dict, date_assessments: dict,
                    response_snapshot_id: str, issues: list[dict]) -> tuple[list, list, list, list, dict]:
    ids = {q["question_id"] for q in questions}
    currency = context["currency"]
    members = {}
    for i, raw in enumerate(require_list(responses.get("participants"), "responses.participants")):
        member = require_object(raw, f"responses.participants[{i}]")
        member_id = require_text(member.get("participant_id"), f"responses.participants[{i}].participant_id")
        if member_id in members:
            raise InputError("DUPLICATE_ID", "responses.participants", "Duplicate participant ID")
        require_in(member.get("response_status"), {"complete", "incomplete", "stale", "needs_clarification"},
                   f"responses.participants.{member_id}.response_status")
        members[member_id] = member
    if set(members) != set(roster):
        issues.append(_issue("ROSTER_MISMATCH", "responses.participants", "Response roster differs from approved roster"))
    constraints, preferences, informational, unclassified_answers = [], [], [], []
    answer_ids = set()
    for member_id in roster:
        member = members.get(member_id)
        if member is None:
            continue
        if member.get("response_status") != "complete":
            issues.append(_issue("INCOMPLETE_RESPONSE", f"responses.participants.{member_id}", "Response is not complete"))
        answers = {}
        for ai, raw in enumerate(require_list(member.get("answers"), f"responses.participants.{member_id}.answers")):
            answer = require_object(raw, f"responses.participants.{member_id}.answers[{ai}]")
            qid = require_text(answer.get("question_id"), "responses.answers.question_id")
            if qid not in ids or qid in answers:
                raise InputError("INVALID_ANSWER", f"responses.participants.{member_id}.answers[{ai}]", "Unknown or repeated question ID")
            answer_id = answer.get("answer_id", f"{response_snapshot_id}:{member_id}:{qid}")
            answer_id = require_text(answer_id, "responses.answers.answer_id")
            if answer_id in answer_ids:
                raise InputError("DUPLICATE_ID", "responses.answers.answer_id", "Duplicate answer ID")
            answer_ids.add(answer_id)
            answers[qid] = {**answer, "answer_id": answer_id}
        for q in questions:
            qid = q["question_id"]
            path = f"responses.participants.{member_id}.answers.{qid}"
            if qid not in answers:
                if q["required"]:
                    issues.append(_issue("MISSING_ANSWER", path, "Required question was not answered"))
                continue
            answer = answers[qid]
            value = answer.get("value")
            evidence_text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
            def entry(parsed: object, source_type: str = "member_response", evidence: str | None = None) -> dict:
                return {"participant_id": member_id, "question_id": qid, "criterion": q["criterion"],
                        "value": parsed, "provenance": answer_provenance(answer, member_id, response_snapshot_id, source_type,
                                                                       evidence_text if evidence is None else evidence),
                        "confirmation": answer.get("confirmed_requirement")}
            criterion = q["criterion"]
            if criterion == "availability" and q["role"] == "hard":
                parsed = _dates(value, path)
                model_dates = False
                if parsed is None and isinstance(value, str) and re.search(r"\b\d{4}\b", value):
                    saved_dates = date_assessments.get(member_id, {}).get(qid) if isinstance(date_assessments.get(member_id, {}), dict) else None
                    if saved_dates is None and semantic_provider is not None and hasattr(semantic_provider, "extract_sparse_dates"):
                        saved_dates = semantic_provider.extract_sparse_dates(q, value, context)
                        date_assessments.setdefault(member_id, {})[qid] = saved_dates
                    if saved_dates is not None:
                        date_result = validate_sparse_dates(saved_dates, value, f"semantic.dates.{member_id}.{qid}")
                        if date_result["status"] == "resolved":
                            parsed = date_result["intervals"]
                            model_dates = True
                if parsed is None:
                    issues.append(_issue("AMBIGUOUS_AVAILABILITY", path, "Provide exact dates or date intervals"))
                else:
                    constraints.append(entry(parsed, "semantic_model" if model_dates else "member_response"))
                continue
            answer_text = _answer_text(value, q, path)
            if criterion == "max_cost" and q["role"] == "hard":
                parsed = _budget(answer_text, currency)
                if parsed is None:
                    issues.append(_issue("AMBIGUOUS_BUDGET", path, "Provide a numeric budget or unlimited"))
                else:
                    constraints.append(entry(parsed))
                continue
            if criterion == "duration_days" and q["role"] == "soft":
                parsed = _duration(answer_text)
                if parsed is None:
                    issues.append(_issue("AMBIGUOUS_DURATION", path, "Provide a number of days or no preference"))
                else:
                    preferences.append(entry(parsed))
                continue
            if q["role"] == "informational":
                informational.append({"participant_id": member_id, "question_id": qid, "value": answer_text})
                continue
            if q["role"] == "unclassified":
                unclassified_answers.append({"participant_id": member_id, "question_id": qid, "value": answer_text})
                continue
            if answer_text.casefold().strip() in NO_PREFERENCE and q["role"] == "soft":
                preferences.append(entry({"kind": "indifferent"}))
                continue
            mapping = q["mapping"]
            if mapping["status"] == "resolved":
                known_values = {token(str(v)) for c in candidates for f in c["facts"] if f["criterion"] == criterion
                                for v in (f["value"] if isinstance(f["value"], list) else [f["value"]])}
                direct = mapping["value_type"] in {"number", "decimal", "boolean"} or isinstance(value, list) or bool(q["choices"]) or token(answer_text) in known_values
                if direct:
                    raw_value = [_answer_text(v, q, path) for v in value] if isinstance(value, list) else answer_text
                    try:
                        parsed = normalize_answer(raw_value, mapping, path)
                    except InputError as exc:
                        if exc.code == "UNIT_MISMATCH":
                            issues.append(exc.as_issue())
                            continue
                        parsed = None
                    if parsed is not None:
                        source_type = "semantic_model" if q["role"] == "hard" and q["inference_source"] == "model" else "member_response"
                        (constraints if q["role"] == "hard" else preferences).append(entry(parsed, source_type))
                        continue
            saved = extracted.get(member_id, {}).get(qid) if isinstance(extracted.get(member_id, {}), dict) else None
            if saved is None and semantic_provider is not None:
                if not hasattr(semantic_provider, "extract_sparse_answer"):
                    raise SemanticServiceError("Sparse answers require extract_sparse_answer on the semantic provider")
                saved = semantic_provider.extract_sparse_answer(q, answer_text, context)
                extracted.setdefault(member_id, {})[qid] = saved
            if saved is None:
                issues.append(_issue("SEMANTIC_PROVIDER_REQUIRED", path, "Open answer needs semantic extraction"))
                continue
            result = validate_sparse_answer_assessment(saved, answer_text, f"semantic.answers.{member_id}.{qid}", criterion)
            if result["status"] == "unresolved" or not result["interpretations"]:
                issues.append(_issue("AMBIGUOUS_ANSWER", path, "Open answer needs clarification"))
                continue
            for interpretation in result["interpretations"]:
                try:
                    interpretation = scoped_interpretation(interpretation, answer_text, q["role"], path)
                except InputError as exc:
                    issues.append(exc.as_issue())
                    continue
                interpreted = {**entry(interpretation["value"], "semantic_model", interpretation["evidence"]),
                               "must_have": interpretation["must_have"], "polarity": interpretation["polarity"]}
                if interpretation["must_have"] or q["role"] == "hard":
                    constraints.append(interpreted)
                if q["role"] == "soft":
                    preferences.append(interpreted)

    return constraints, preferences, informational, unclassified_answers, members
