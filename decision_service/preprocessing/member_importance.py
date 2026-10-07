"""Extract importance separately from preferences and derive member soft weights."""

from __future__ import annotations

import re
from collections import defaultdict

from .common import InputError, issue, require_list, require_object, require_text
from .generic_evidence import answer_provenance


def importance_question(label: str, registry: dict) -> dict | None:
    if not re.search(r"\b(important|importance|matters? most|priorities|priority)\b", label, re.I):
        return None
    names = [aid for aid in registry if aid.replace("_", " ") in label.casefold()]
    return {"role": "importance", "criterion": names[0] if len(names) == 1 else "importance",
            "relevance": 0.0, "reason": "Question asks for member importance, not an attribute target"}


def extract_importance(value: object, answer: dict, member_id: str, snapshot_id: str,
                       registry: dict, path: str, criterion: str | None = None, *, names: dict | None = None) -> list[dict]:
    """Accept explicit multipliers or ordinal comparisons; do not invent ratios."""
    text = value if isinstance(value, str) else str(value)
    provenance = answer_provenance(answer, member_id, snapshot_id, "member_response", text)
    if isinstance(value, dict):
        entries = []
        for aid, multiplier in value.items():
            require_text(aid, path)
            if type(multiplier) not in {int, float} or not 0 <= multiplier <= 1e100:
                raise InputError("AMBIGUOUS_IMPORTANCE", path, "Importance weights must be finite nonnegative numbers")
            entries.append({**provenance, "kind": "multiplier", "attribute_id": aid, "value": multiplier})
        return entries
    if type(value) in {int, float} and criterion and criterion != "importance":
        return extract_importance({criterion: value}, answer, member_id, snapshot_id, registry, path)
    if not isinstance(value, str):
        return []
    entries = []
    names = names or {aid.replace("_", " "): aid for aid in registry}
    for fragment in re.split(r"[.;\n]", value):
        match = re.fullmatch(r"\s*(.+?)\s+(?:is more important than|matters more than|over)\s+(.+?)\s*(?:to me)?\s*", fragment, re.I)
        if not match:
            continue
        left, right = (part.casefold().strip() for part in match.groups())
        if left.startswith("i prioritize "):
            left = left[len("i prioritize "):]
        if left in names and right in names:
            entries.append({**provenance, "evidence": fragment.strip(), "kind": "ordering",
                            "higher_attribute_id": names[left], "lower_attribute_id": names[right]})
    return entries


def validate_model_importance(raw: object, answer_text: str, provenance: dict, path: str) -> list[dict]:
    entries = []
    for item in require_list(raw, path):
        item = require_object(item, path)
        higher = require_text(item.get("higher_criterion"), path)
        lower = require_text(item.get("lower_criterion"), path)
        evidence = require_text(item.get("evidence"), path)
        if evidence.casefold() not in answer_text.casefold() or higher == lower:
            raise InputError("AMBIGUOUS_IMPORTANCE", path, "Importance ordering needs distinct criteria and grounded evidence")
        entries.append({**provenance, "source_type": "semantic_model", "evidence": evidence, "kind": "ordering",
                        "higher_attribute_id": higher, "lower_attribute_id": lower})
    return entries


def compile_member_weights(handoff: dict, entries: list[dict], issues: list[dict]) -> None:
    """Split question mass across criteria, then apply declared member importance.

    Ordinal levels use longest-path tiers (lowest=1). This is an explicit policy,
    not a numerical ratio claimed by the member or predicted by the model.
    """
    questions = {q["question_id"]: q for q in handoff["scoring_model"]["questions"]}
    exported, rows = [], []
    for member in handoff["participants"]:
        pid = member["participant_id"]
        preferences = [p for p in handoff["preferences"] if p["participant_id"] == pid]
        grouped = defaultdict(set)
        for preference in preferences:
            if questions[preference["source_question_id"]]["weight"]:
                grouped[preference["source_question_id"]].add(preference["attribute_id"])
        active = set().union(*grouped.values()) if grouped else set()
        multipliers, edges = {}, set()
        unresolved = False
        for entry in [entry for entry in entries if entry["participant_id"] == pid]:
            if entry.get("canonicalization_status") == "unresolved":
                unresolved = True
                exported.append({**entry, "status": "unresolved"})
                continue
            references = {entry["attribute_id"]} if entry["kind"] == "multiplier" else {entry["higher_attribute_id"], entry["lower_attribute_id"]}
            if not references <= active:
                issues.append(issue("AMBIGUOUS_IMPORTANCE", f"responses.participants.{pid}",
                                    "Importance can reference only this member's active soft criteria"))
                unresolved = True
                exported.append({**entry, "status": "unresolved"})
                continue
            if entry["kind"] == "multiplier":
                aid, value = entry["attribute_id"], entry["value"]
                if aid in multipliers and multipliers[aid] != value:
                    unresolved = True
                    issues.append(issue("CONFLICTING_IMPORTANCE", f"responses.participants.{pid}", "Different importance values target the same criterion"))
                multipliers[aid] = value
            else:
                edges.add((entry["higher_attribute_id"], entry["lower_attribute_id"]))
            exported.append({**entry, "status": "estimated" if entry["source_type"] == "semantic_model" else "confirmed"})
        levels, visiting = {}, set()

        def level(aid):
            if aid in visiting:
                raise ValueError("Importance cycle")
            if aid not in levels:
                visiting.add(aid)
                levels[aid] = 1 + max([level(lower) for higher, lower in edges if higher == aid] or [0])
                visiting.remove(aid)
            return levels[aid]

        try:
            for aid in active:
                level(aid)
        except ValueError:
            unresolved = True
            issues.append(issue("CONFLICTING_IMPORTANCE", f"responses.participants.{pid}", "Importance comparisons form a cycle"))
        if not unresolved and any(multipliers.get(higher, levels[higher]) <= multipliers.get(lower, levels[lower]) for higher, lower in edges):
            unresolved = True
            issues.append(issue("CONFLICTING_IMPORTANCE", f"responses.participants.{pid}", "Explicit importance values contradict an ordering"))
        member_rows = []
        ordered_attributes = {aid for edge in edges for aid in edge}
        for qid, attributes in grouped.items():
            base = questions[qid]["weight"] / len(attributes)
            for aid in sorted(attributes):
                multiplier = multipliers.get(aid, levels.get(aid, 1)) if not unresolved else 1
                source = "default"
                if aid in ordered_attributes:
                    source = "ordinal_tiers"
                if aid in multipliers:
                    source = "explicit"
                if unresolved:
                    source = "unresolved"
                member_rows.append({"participant_id": pid, "source_question_id": qid, "attribute_id": aid,
                                    "base_weight": base, "importance_multiplier": multiplier,
                                    "importance_source": source,
                                    "raw_weight": base * multiplier})
        total = sum(row["raw_weight"] for row in member_rows)
        if member_rows and total == 0:
            unresolved = True
            issues.append(issue("AMBIGUOUS_IMPORTANCE", f"responses.participants.{pid}", "At least one soft criterion needs positive importance"))
        if unresolved:
            for entry in exported:
                if entry["participant_id"] == pid:
                    entry["status"] = "unresolved"
        for row in member_rows:
            raw = row.pop("raw_weight")
            row.update(effective_weight=round(raw / total, 12) if total and not unresolved else None,
                       status="unresolved" if unresolved else "resolved")
        rows.extend(member_rows)
    handoff["importance"] = exported
    handoff["scoring_model"].update(member_weights=rows, member_weight_policy="question_share_times_importance_v1",
                                    ordinal_importance_policy="longest_path_tiers_v1")
