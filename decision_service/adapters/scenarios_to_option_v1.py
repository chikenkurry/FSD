"""Materialize confirmed preprocessing scenario requests for generic ranking."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .generic_to_option_v1 import adapt_generic_to_option_v1


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _result(status: str, issues: list[dict[str, str]], algorithm_input: dict | None = None) -> dict:
    return {"status": status, "issues": issues, "algorithm_input": algorithm_input}


def adapt_scenarios_to_option_v1(preparation: dict[str, Any]) -> dict:
    """Create executable candidates from confirmed whole-day scenario requests.

    A request denotes a feasible date *window*, not an exact selected start
    date.  The emitted candidate retains that window in ``scenario`` while its
    cost and duration become ordinary candidate facts for generic matching.
    """
    if not isinstance(preparation, dict) or preparation.get("status") != "ready":
        return _result("needs_information", [_issue("PREPARATION_NOT_READY", "Generic preparation must be ready before scenario adaptation")])
    requests = preparation.get("scenario_requests")
    if not isinstance(requests, list) or not requests:
        return _result("needs_information", [_issue("SCENARIO_CANDIDATES_REQUIRED", "No confirmed scenario requests are available")])

    criteria = {item.get("attribute_id"): item for item in preparation.get("criteria", [])}
    missing = [attribute_id for attribute_id in ("duration_days", "max_cost") if attribute_id not in criteria]
    if missing:
        return _result("unsupported", [_issue("MISSING_SCENARIO_CRITERION", f"Scenario criteria missing: {', '.join(missing)}")])
    options = {item.get("option_id"): item for item in preparation.get("candidates", [])}
    issues: list[dict[str, str]] = []
    candidates = []
    for request in requests:
        option_id = request.get("option_id")
        evidence = request.get("cost_evidence")
        if option_id not in options:
            issues.append(_issue("UNKNOWN_SCENARIO_OPTION", "Scenario request references an unknown option"))
            continue
        if request.get("cost_evidence_status") != "confirmed" or not isinstance(evidence, dict):
            issues.append(_issue("SCENARIO_COST_REQUIRED", "Every scenario needs confirmed cost evidence before ranking"))
            continue
        if any(not isinstance(request.get(field), (str, int)) for field in ("duration_days", "earliest_start_date", "latest_start_date")):
            issues.append(_issue("INVALID_SCENARIO_REQUEST", "Scenario request needs duration and ISO date window"))
            continue
        if evidence.get("status") != "confirmed" or evidence.get("amount") is None:
            issues.append(_issue("SCENARIO_COST_REQUIRED", "Scenario cost evidence must be confirmed and contain an amount"))
            continue
        option = options[option_id]
        facts = [deepcopy(fact) for fact in option.get("facts", []) if fact.get("attribute_id") not in {"duration_days", "max_cost"}]
        facts.extend([
            {**deepcopy(criteria["duration_days"]), "value": request["duration_days"], "status": "confirmed", "source": "scenario_request", "context": {}},
            {**deepcopy(criteria["max_cost"]), "value": evidence["amount"], "status": "confirmed", "source": evidence.get("source", "scenario_cost"),
             "context": deepcopy(evidence.get("context", {}))},
        ])
        scenario_id = f"{option_id}@{request['duration_days']}d:{request['earliest_start_date']}:{request['latest_start_date']}"
        candidates.append({"option_id": scenario_id, "source_option_id": option_id, "title": option.get("title"), "facts": facts,
                           "scenario": {key: request[key] for key in ("duration_days", "earliest_start_date", "latest_start_date")}})
    if issues:
        return _result("needs_information", issues)

    executable = deepcopy(preparation)
    executable["candidates"] = candidates
    # Availability has already been intersected by preprocessing to create the
    # scenario request; it is not a fact that the generic matcher evaluates.
    executable["constraints"] = [item for item in executable.get("constraints", []) if item.get("attribute_id") != "availability"]
    executable["scenario_requests"] = []
    result = adapt_generic_to_option_v1(executable)
    if result["status"] == "ready":
        result["algorithm_input"]["context"]["algorithm_version"] = "generic-option-scenario-v1"
    return result
