"""Build aggregate results and member-specific reviews from private run artifacts."""
from copy import deepcopy

from decision_service.ranking import primary_score_key, primary_ties
from .snapshots import SnapshotError


VIEW_SCHEMA_VERSION = "recommendation-view-v1"


def _candidate_id(row: dict) -> str | None:
    """Normalise activity and generic execution identifiers for presentation."""
    return row.get("option_id") or row.get("candidate_id")


def _candidate_catalog(run: dict) -> dict[str, dict]:
    catalog = {}
    prepared = {row["option_id"]: row for row in run.get("processing", {}).get("preparation", {}).get("candidates", [])}
    context = run.get("algorithm_input", {}).get("context", {})
    for candidate in run.get("algorithm_input", {}).get("candidates", []):
        candidate_id = _candidate_id(candidate)
        if not candidate_id:
            continue
        source_id = candidate.get("source_option_id") or candidate.get("activity_id")
        title = candidate.get("title") or prepared.get(source_id, {}).get("title") or source_id or candidate_id
        details = {key: candidate[key] for key in ("source_option_id", "start_at", "end_at", "estimated_cost_minor") if key in candidate}
        details.update({key: context[key] for key in ("currency", "currency_minor_digits") if key in context})
        if "scenario" in candidate:
            details["scenario"] = {key: candidate["scenario"][key] for key in
                                   ("duration_days", "earliest_start_date", "latest_start_date") if key in candidate["scenario"]}
        catalog[candidate_id] = {"candidate_id": candidate_id, "title": title, **details}
    return catalog


def _ranked_for_display(run: dict) -> list[dict]:
    ranked = run.get("result", {}).get("ranked_candidates", [])
    if not ranked or all("primary_rank" in row and "primary_objective_tie_size" in row for row in ranked):
        return ranked
    # Historical artifacts predate tie metadata. Derive it without changing
    # their stored scores, winner, or display order.
    model = run.get("algorithm_input", {}).get("scoring_model", {})
    mode = model.get("group_objective", {}).get("mode", "maximin_then_average")
    keys = [primary_score_key(row["min_member_score"], row["average_member_score"], row["group_score"], mode) for row in ranked]
    ties = primary_ties(keys)
    return [{**row, "primary_rank": ties[key][0], "primary_objective_tie_size": ties[key][1]}
            for row, key in zip(ranked, keys)]


def _display_candidate(row: dict, catalog: dict[str, dict], *, recommended: bool = False) -> dict:
    candidate_id = _candidate_id(row)
    known = catalog.get(candidate_id, {"candidate_id": candidate_id, "title": candidate_id})
    return {
        **known,
        "rank": row.get("rank"),
        "primary_rank": row.get("primary_rank", row.get("rank")),
        "primary_objective_tie_size": row.get("primary_objective_tie_size", 1),
        "group_score": row.get("group_score"),
        "minimum_member_score": row.get("min_member_score"),
        "average_member_score": row.get("average_member_score"),
        "fairness_penalty": row.get("fairness_penalty"),
        "is_recommended": recommended,
    }


def _tradeoffs(candidate: dict, recommendation: dict) -> list[str]:
    """Emit frontend-owned labels, never prose inferred from private answers."""
    labels = []
    for field, higher, lower in (
        ("minimum_member_score", "HIGHER_MINIMUM_SATISFACTION", "LOWER_MINIMUM_SATISFACTION"),
        ("average_member_score", "HIGHER_AVERAGE_SATISFACTION", "LOWER_AVERAGE_SATISFACTION"),
    ):
        value, baseline = candidate.get(field), recommendation.get(field)
        if value is None or baseline is None:
            continue
        if value > baseline:
            labels.append(higher)
        elif value < baseline:
            labels.append(lower)
    return labels or ["EQUIVALENT_GROUP_METRICS"]


def recommendation_view(run: dict) -> dict:
    """Project a shared, privacy-safe decision result for product presentation.

    The view exposes aggregate outcome metrics only. Member answers, individual
    scores, and the reason a particular member cannot attend remain private.
    """
    result = run.get("result", {})
    catalog = _candidate_catalog(run)
    ranked = _ranked_for_display(run)
    recommendation = _display_candidate(ranked[0], catalog, recommended=True) if ranked else None
    pareto_ids = {_candidate_id(row) for row in result.get("pareto_frontier", [])}
    alternatives = [_display_candidate(row, catalog) for row in ranked[1:]]
    pareto = []
    if recommendation:
        for candidate in alternatives:
            if candidate["candidate_id"] in pareto_ids:
                pareto.append({**candidate, "tradeoffs": _tradeoffs(candidate, recommendation)})

    unavailable = []
    for row in result.get("candidate_results", []):
        if row.get("feasibility") == "feasible":
            continue
        candidate_id = _candidate_id(row)
        unavailable.append({**catalog.get(candidate_id, {"candidate_id": candidate_id, "title": candidate_id}),
                            "status": row.get("feasibility")})
    fact_requests = run.get("processing", {}).get("preparation", {}).get("fact_requests", [])
    status = run.get("status")
    next_action = None
    if fact_requests:
        next_action = "OPTION_FACTS_REQUIRED"
    elif status == "blocked":
        next_action = "RESPONSES_OR_CONFIRMATIONS_REQUIRED"
    elif status == "no_feasible_candidate":
        next_action = "REVISE_OPTIONS_OR_REQUIREMENTS"
    elif status == "pending":
        next_action = "RECOMMENDATION_IN_PROGRESS"
    elif status in {"needs_information", "needs_clarification", "unsupported", "invalid_input"}:
        next_action = "DECISION_SETUP_REVIEW_REQUIRED"
    elif status == "failed":
        next_action = "RECOMMENDATION_RETRY_REQUIRED"
    return {
        "schema_version": VIEW_SCHEMA_VERSION,
        "status": status,
        "recommendation": recommendation,
        "alternatives": alternatives,
        "pareto_alternatives": pareto,
        "unavailable_candidates": unavailable,
        "next_action": next_action,
    }


def _public_algorithm_result(result: dict) -> dict:
    """Allowlist the whole public result; diagnostic fields stay in storage."""
    public = {key: result[key] for key in ("status", "run_id", "algorithm_version", "policy_version") if key in result}
    fields = {
        "ranked_candidates": ("option_id", "candidate_id", "rank", "primary_rank", "primary_objective_tie_size",
                              "min_member_score", "average_member_score", "group_score", "fairness_penalty",
                              "estimated_cost_minor", "start_at"),
        "candidate_results": ("option_id", "candidate_id", "feasibility"),
        "pareto_frontier": ("option_id", "candidate_id"),
    }
    for name, allowed in fields.items():
        if name in result:
            public[name] = [{key: row[key] for key in allowed if key in row} for row in result[name]]
    if "issues" in result:
        public["issues"] = []  # Raw contract errors can include private input values.
    return deepcopy(public)


def public_result(run: dict) -> dict:
    result = _public_algorithm_result(run.get("result", {}))
    preparation = run.get("processing", {}).get("preparation", {})
    facts = [{key: row[key] for key in ("option_id", "attribute_id", "value_type", "unit", "priority") if key in row}
             for row in preparation.get("fact_requests", [])]
    scenarios = [{key: row[key] for key in ("option_id", "duration_days", "earliest_start_date", "latest_start_date", "cost_evidence_status") if key in row}
                 for row in preparation.get("scenario_requests", [])]
    supplemented = []
    for row in run.get("fact_enrichment", {}).get("applied_facts", []):
        fact = row["fact"]
        context = fact.get("context", {})
        supplemented.append({"option_id": row["option_id"], "attribute_id": fact["criterion"],
            "value": deepcopy(fact["value"]), "value_type": fact["value_type"], "unit": fact.get("unit"),
            "source_text": context.get("source_text", ""),
            "sources": [{k:s[k] for k in ("url", "title") if k in s} for s in context.get("sources", [])],
            "retrieved_at": context.get("retrieved_at")})
    return {"run_id": run["run_id"], "status": run["status"], "input_refs": run["input_refs"],
            **({"collection": deepcopy(run["collection"])} if "collection" in run else {}),
            **({"research": deepcopy(run["research"])} if "research" in run else {}),
            "job_state": run.get("job_state", "completed"),
            "execution_specification": run.get("execution_specification", {}),
            "result": result, "fact_requests": facts, "scenario_requests": scenarios,
            "supplemented_facts": supplemented,
            "recommendation_view": recommendation_view(run),
            "issues": [{"code": issue.get("code", "PROCESSING_ISSUE")} for issue in run.get("issues", [])
                       if not issue.get("path", "").startswith("responses.participants.")]}


def member_review(run: dict, member_id: str) -> dict:
    if member_id not in run.get("member_states", {}):
        raise SnapshotError("Member is not in this run")
    packet = run.get("processing", {}).get("preparation", {})
    own = {key: [deepcopy(row) for row in packet.get(key, []) if row.get("participant_id") == member_id]
           for key in ("constraints", "preferences", "importance", "unclassified_answers")}
    issues = []
    prefix = f"responses.participants.{member_id}."
    for issue in run.get("issues", []):
        path = issue.get("path", "")
        if path.startswith("responses.participants.") and not path.startswith(prefix):
            continue
        record = {"code": issue["code"]}
        if path.startswith(prefix):
            record["message"] = issue.get("message", "Review this answer")
            if ".answers." in path:
                record["question_id"] = path.split(".answers.", 1)[1]
        issues.append(record)
    own.update(status=run["status"], response_status=run["member_states"][member_id], issues=issues,
               run_id=run.get("run_id"), response_revision=run.get("response_revision"))
    return own
