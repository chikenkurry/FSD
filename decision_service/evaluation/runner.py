"""Run labelled snapshots through preprocessing and report assertion failures."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from decision_service.preprocessing import preprocess
from decision_service.preprocessing.sparse import VERSION as SPARSE_PROCESSING_VERSION


DIMENSIONS = {
    "classification", "mapping", "weights", "extraction", "constraints",
    "facts", "clarification", "status",
}
OPERATORS = {"equals", "approx", "rows", "contains_rows", "absent_rows", "normalized_weights"}


class _RecordingProvider:
    """Record accepted and rejected model replies without API transport secrets."""

    METHODS = {"classify_question", "extract_sparse_answer", "extract_sparse_dates", "suggest_option_tags", "canonicalize_sparse_label"}

    def __init__(self, provider):
        self.provider = provider
        self.calls = []

    def __getattr__(self, name):
        method = getattr(self.provider, name)
        if name not in self.METHODS:
            return method

        def record(*args, **kwargs):
            call = {"method": name, "subject": {
                key: args[0][key] for key in ("question_id", "label", "option_id", "kind", "criterion") if key in args[0]
            }}
            started = perf_counter()
            self.calls.append(call)
            try:
                result = method(*args, **kwargs)
                call["response"] = copy.deepcopy(result)
                return result
            except Exception as exc:
                call["error_type"] = type(exc).__name__
                raise
            finally:
                call["duration_seconds"] = round(perf_counter() - started, 3)

        return record


def _reject_constant(value: str) -> None:
    raise ValueError(f"Nonfinite JSON number is not supported: {value}")


def load_dataset(path: Path) -> dict:
    dataset = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    validate_dataset(dataset)
    return dataset


def validate_dataset(dataset: dict) -> None:
    """Reject empty, duplicate, or malformed labels before running any provider."""
    if not isinstance(dataset, dict) or dataset.get("schema_version") != "preprocessing-eval-v1":
        raise ValueError("Dataset must use preprocessing-eval-v1")
    if not isinstance(dataset.get("dataset_version"), str) or not dataset["dataset_version"].strip():
        raise ValueError("Dataset version must be a nonempty string")
    provenance = dataset.get("label_provenance")
    if provenance is not None:
        if (not isinstance(provenance, dict) or set(provenance) != {"author", "method", "independent_review", "reviewer"}
                or not isinstance(provenance["author"], str) or not provenance["author"].strip()
                or not isinstance(provenance["method"], str) or not provenance["method"].strip()
                or not isinstance(provenance["independent_review"], str) or provenance["independent_review"] not in {"pending", "complete"}
                or provenance["reviewer"] is not None and not isinstance(provenance["reviewer"], str)
                or provenance["independent_review"] == "complete" and not (provenance["reviewer"] or "").strip()):
            raise ValueError("Label provenance must identify authorship and independent review status/reviewer")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Dataset needs at least one case")
    seen = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Each case must be an object")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", case_id) or case_id in seen:
            raise ValueError("Case IDs must be unique lowercase slugs")
        seen.add(case_id)
        if not isinstance(case.get("domain"), str) or not case["domain"].strip():
            raise ValueError(f"{case_id}: domain is required")
        tags = case.get("tags")
        if not isinstance(tags, list) or not tags or any(not isinstance(tag, str) or not tag for tag in tags):
            raise ValueError(f"{case_id}: tags must be nonempty strings")
        for field in ("planning", "responses"):
            if not isinstance(case.get(field), dict):
                raise ValueError(f"{case_id}: {field} must be a snapshot object")
        assertions = case.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            raise ValueError(f"{case_id}: assertions cannot be empty")
        for assertion in assertions:
            if not isinstance(assertion, dict) or set(assertion) != {"dimension", "path", "op", "value"}:
                raise ValueError(f"{case_id}: assertions need dimension, path, op, and value")
            if (not isinstance(assertion["dimension"], str) or assertion["dimension"] not in DIMENSIONS
                    or not isinstance(assertion["op"], str) or assertion["op"] not in OPERATORS):
                raise ValueError(f"{case_id}: unsupported assertion dimension or operator")
            pointer = assertion["path"]
            if not isinstance(pointer, str) or not pointer.startswith("/") or re.search(r"~(?![01])", pointer):
                raise ValueError(f"{case_id}: path must be a JSON pointer")
            value = assertion["value"]
            if assertion["op"] == "approx":
                if type(value) not in {int, float} or not math.isfinite(value):
                    raise ValueError(f"{case_id}: approximate values must be finite numbers")
            elif assertion["op"] == "normalized_weights":
                if (not isinstance(value, list) or not value or any(not isinstance(v, str) or not v for v in value)
                        or len(set(value)) != len(value)):
                    raise ValueError(f"{case_id}: normalized_weights needs unique active question IDs")
            elif assertion["op"] in {"rows", "contains_rows", "absent_rows"}:
                if not isinstance(value, list) or any(not isinstance(row, dict) or not row for row in value):
                    raise ValueError(f"{case_id}: row labels must be nonempty objects")
                if assertion["op"] != "rows" and not value:
                    raise ValueError(f"{case_id}: inclusion/exclusion checks need at least one row")


def _pointer(result: dict, pointer: str) -> object:
    current = result
    for part in pointer[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list) and re.fullmatch(r"0|[1-9][0-9]*", part):
            current = current[int(part)]
        else:
            raise KeyError(pointer)
    return current


def _matches(actual: object, expected: object, subset: bool = False) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and (subset or set(actual) == set(expected)) and all(
            key in actual and _matches(actual[key], value, subset) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            _matches(a, e, subset) for a, e in zip(actual, expected)
        )
    if type(expected) is bool or type(actual) is bool:
        return type(actual) is type(expected) and actual == expected
    return actual == expected


def _row_matches(actual: list, expected: list) -> tuple[list[int], list[int]]:
    """Find a one-to-one assignment; overlapping labels cannot reuse a row."""
    assigned = {}

    def assign(label: int, visited: set) -> bool:
        for index, row in enumerate(actual):
            if index in visited or not _matches(row, expected[label], subset=True):
                continue
            visited.add(index)
            if index not in assigned or assign(assigned[index], visited):
                assigned[index] = label
                return True
        return False

    missing = [index for index in range(len(expected)) if not assign(index, set())]
    unexpected = [index for index in range(len(actual)) if index not in assigned]
    return missing, unexpected


def check_assertion(result: dict, assertion: dict) -> dict:
    check = {"dimension": assertion["dimension"], "path": assertion["path"], "op": assertion["op"]}
    expected = assertion["value"]
    try:
        actual = _pointer(result, assertion["path"])
    except (KeyError, IndexError):
        return {**check, "passed": False, "expected": expected, "missing_path": True}
    op = assertion["op"]
    if op == "equals":
        passed = _matches(actual, expected)
    elif op == "approx":
        passed = type(actual) in {int, float} and math.isfinite(actual) and math.isclose(
            actual, expected, rel_tol=0, abs_tol=1e-9,
        )
    elif not isinstance(actual, list):
        passed = False
    elif op == "normalized_weights":
        passed = _normalized_weights(actual, expected)
    elif op == "absent_rows":
        passed = not any(_matches(row, label, subset=True) for row in actual for label in expected)
    else:
        missing, unexpected = _row_matches(actual, expected)
        passed = not missing and (op == "contains_rows" or not unexpected)
        if not passed:
            check.update(missing_rows=[expected[i] for i in missing])
            if op == "rows":
                check.update(unexpected_rows=[actual[i] for i in unexpected])
    return {**check, "passed": passed} if passed else {
        **check, "passed": False, "expected": expected, "actual": actual,
    }


def _normalized_weights(questions: list, expected: list[str]) -> bool:
    weights, active, seen = [], set(), set()
    for question in questions:
        if not isinstance(question, dict) or not isinstance(question.get("question_id"), str):
            return False
        qid, weight, role = question["question_id"], question.get("weight"), question.get("role")
        if qid in seen:
            return False
        seen.add(qid)
        if role == "soft":
            if type(weight) not in {int, float} or not 0 <= weight <= 1:
                return False
            weights.append(weight)
            if weight > 0:
                active.add(qid)
        elif role not in {"hard", "informational", "importance", "unclassified"} or weight is not None:
            return False
    return active == set(expected) and math.isclose(sum(weights), 1, rel_tol=0, abs_tol=1e-9)


def _metrics(checks: list[dict]) -> dict:
    passed = sum(check["passed"] for check in checks)
    return {"passed": passed, "total": len(checks), "accuracy": passed / len(checks) if checks else None,
            "missing_paths": sum(check.get("missing_path", False) for check in checks),
            "value_mismatches": sum(not check["passed"] and not check.get("missing_path", False) for check in checks)}


def evaluate(dataset: dict, *, semantic_provider=None, evidence_dir: Path | None = None,
             save_evidence_dir: Path | None = None, tags: tuple[str, ...] = (),
             progress=None) -> dict:
    """Labels are used only after processing; never supplied to the provider.

    A replay directory must contain an evidence file for every selected case.
    Provider failures and unexpected exceptions remain failed cases in the report.
    """
    validate_dataset(dataset)
    dataset_hash = hashlib.sha256(json.dumps(dataset, sort_keys=True, allow_nan=False).encode()).hexdigest()
    if evidence_dir is not None and semantic_provider is not None:
        raise ValueError("Replay and a live semantic provider cannot be combined")
    cases = [case for case in dataset["cases"] if not tags or set(tags) <= set(case["tags"])]
    if not cases:
        raise ValueError("No cases match the requested tags")
    if save_evidence_dir is not None:
        save_evidence_dir.mkdir(parents=True, exist_ok=True)
    by_dimension, by_domain = defaultdict(list), defaultdict(list)
    reports = []
    evaluated_at = datetime.now(timezone.utc).isoformat()
    started = perf_counter()
    for number, case in enumerate(cases, 1):
        if progress:
            progress(number, len(cases), case["case_id"])
        case_started = perf_counter()
        error = None
        recorder = _RecordingProvider(semantic_provider) if semantic_provider is not None else None
        try:
            evidence = json.loads((evidence_dir / f"{case['case_id']}.json").read_text(encoding="utf-8")) if evidence_dir else None
            if evidence_dir and not isinstance(evidence, dict):
                raise ValueError("Replay requires an evidence object, not null")
            result = preprocess(copy.deepcopy(case["planning"]), copy.deepcopy(case["responses"]),
                                semantic_provider=recorder, semantic_evidence=evidence)
            if result.get("status") == "upstream_unavailable":
                error = {"type": "provider_unavailable", "message": "Semantic provider failed"}
            artifact = result.get("semantic_evidence")
            if (artifact is None and recorder is not None and not recorder.calls and error is None
                    and "options" in case["planning"]):
                # Freeze an empty assessment set for cases completed entirely
                # by rules, so a hybrid run can replay its full selected corpus.
                artifact = {"option_snapshot_id": case["planning"].get("option_snapshot_id"),
                            "response_snapshot_id": case["responses"].get("response_snapshot_id"),
                            "processing_version": SPARSE_PROCESSING_VERSION, "model": None,
                            "question_assessments": {}, "answer_assessments": {},
                            "option_suggestions": {}, "date_assessments": {},
                            "canonical_assessments": {}, "canonicalization_enabled": False,
                            "canonicalization_declarations": copy.deepcopy(case["planning"].get("canonicalization", {}))}
            if save_evidence_dir is not None and artifact is not None:
                destination = save_evidence_dir / f"{case['case_id']}.json"
                destination.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            # Keep a failed case visible and continue the rest of a potentially
            # expensive model run. Do not put provider payloads/secrets in reports.
            result = {}
            error = {"type": type(exc).__name__, "message": "Case execution or evidence I/O failed"}
        checks = [check_assertion(result, assertion) for assertion in case["assertions"]]
        for check in checks:
            by_dimension[check["dimension"]].append(check)
            by_domain[case["domain"]].append(check)
        reports.append({
            "case_id": case["case_id"], "domain": case["domain"], "tags": case["tags"],
            "passed": error is None and all(check["passed"] for check in checks),
            "duration_seconds": round(perf_counter() - case_started, 3),
            "result_status": result.get("status"), "error": error,
            "issues": copy.deepcopy(result.get("issues", [])),
            "model_calls": recorder.calls if recorder else [],
            "processing_version": result.get("preparation", {}).get("context", {}).get("processing_version"),
            "evidence_model": (result.get("semantic_evidence") or {}).get("model"),
            "metrics": _metrics(checks), "failures": [check for check in checks if not check["passed"]],
        })
    passed_cases = sum(case["passed"] for case in reports)
    all_checks = [check for checks in by_dimension.values() for check in checks]
    return {
        "schema_version": "preprocessing-eval-report-v1", "dataset_version": dataset.get("dataset_version"),
        "dataset_sha256": dataset_hash, "evaluated_at": evaluated_at,
        "label_provenance": copy.deepcopy(dataset.get("label_provenance")),
        "mode": "replay" if evidence_dir else "live" if semantic_provider else "rules",
        "model": getattr(semantic_provider, "model", None), "selected_tags": list(tags),
        "duration_seconds": round(perf_counter() - started, 3),
        "cases": {"passed": passed_cases, "total": len(reports), "accuracy": passed_cases / len(reports)},
        "assertions": _metrics(all_checks),
        "operational_errors": sum(case["error"] is not None for case in reports),
        "by_dimension": {key: _metrics(value) for key, value in sorted(by_dimension.items())},
        "by_domain": {key: _metrics(value) for key, value in sorted(by_domain.items())},
        "results": reports,
    }
