"""Resolve labels within a typed criterion without inferring option facts."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from copy import deepcopy

from .common import InputError, require_in, require_list, require_object, require_text


POLICY_VERSION = "scoped-labels-v1"
TEXT_TYPES = {"category", "tag_set"}


def label_key(value: str) -> str:
    """Ignore case, spacing, and separators between words, retaining C++/C#."""
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"(?<=\w)[_-](?=\w)", " ", value)
    return " ".join(value.split())


def _add_alias(index: dict, alias: str, target: str, path: str) -> None:
    key = label_key(require_text(alias, path))
    if key in index and index[key] != target:
        raise InputError("AMBIGUOUS_ALIAS", path, "One label cannot identify different canonical meanings in the same scope")
    index[key] = target


class Canonicalizer:
    """Apply declared aliases first and optionally ask the semantic provider.

    Model decisions are equivalence assessments, never facts. Only supplied
    criterion IDs and observed/declared text values can be model targets.
    Option facts use declared aliases and formatting rules only.
    """

    def __init__(self, declarations: object, registry: dict, provider=None,
                 assessments: dict | None = None, *, replay: bool = False, model_enabled: bool | None = None,
                 decision_question: str | None = None):
        declarations = require_object(declarations, "planning.canonicalization")
        if set(declarations) - {"criteria", "values"}:
            raise InputError("INVALID_ALIAS", "planning.canonicalization", "Unknown canonicalization field")
        self.declarations = deepcopy(declarations)
        self.registry = registry
        self.provider = provider
        self.assessments = assessments if assessments is not None else {}
        self.replay = replay
        self.decision_question = decision_question
        if model_enabled is None:
            model_enabled = bool(self.assessments) if replay else provider is not None and hasattr(provider, "canonicalize_sparse_label")
        self.model_enabled = model_enabled
        if type(self.model_enabled) is not bool:
            raise InputError("INVALID_SEMANTIC_RESULT", "semantic_evidence.canonicalization_enabled", "Expected a boolean")
        self.records = []
        self.criterion_aliases, self.value_aliases, self.vocabulary = {}, {}, {}
        raw_criteria = require_object(declarations.get("criteria", {}), "planning.canonicalization.criteria")
        explicit = {}
        for target, aliases in raw_criteria.items():
            if target not in registry:
                raise InputError("UNKNOWN_CRITERION", "planning.canonicalization.criteria", "Declare the canonical criterion in facts or planning.criteria")
            for alias in require_list(aliases, "planning.canonicalization.criteria"):
                _add_alias(explicit, alias, target, "planning.canonicalization.criteria")
                if alias in registry and (registry[alias]["value_type"] != registry[target]["value_type"]
                                          or registry[alias]["unit"] != registry[target]["unit"]):
                    raise InputError("CONFLICTING_FACT_TYPE", "planning.canonicalization.criteria", "Aliased criteria must have the same type and unit")
        for aid in registry:
            target = explicit.get(label_key(aid), aid)
            _add_alias(self.criterion_aliases, aid, target, "planning.canonicalization.criteria")
        for alias, target in explicit.items():
            _add_alias(self.criterion_aliases, alias, target, "planning.canonicalization.criteria")
        # Reject chains/cycles: declarations must point directly to a stable ID.
        for target in raw_criteria:
            if self.criterion_aliases[label_key(target)] != target:
                raise InputError("INVALID_ALIAS", "planning.canonicalization.criteria", "Alias targets cannot themselves be aliases")
        self.target_ids = {self.criterion_aliases[label_key(aid)] for aid in registry}
        raw_values = require_object(declarations.get("values", {}), "planning.canonicalization.values")
        for aid, values in raw_values.items():
            if aid not in self.target_ids or registry[aid]["value_type"] not in TEXT_TYPES:
                raise InputError("INVALID_ALIAS", "planning.canonicalization.values", "Value aliases require a canonical category or tag_set criterion")
            index = self.value_aliases.setdefault(aid, {})
            for target, aliases in require_object(values, "planning.canonicalization.values").items():
                target = label_key(require_text(target, "planning.canonicalization.values"))
                _add_alias(index, target, target, "planning.canonicalization.values")
                for alias in require_list(aliases, "planning.canonicalization.values"):
                    _add_alias(index, alias, target, "planning.canonicalization.values")
                self.vocabulary.setdefault(aid, set()).add(target)

    def names(self) -> dict:
        return {label: aid for label, aid in self.criterion_aliases.items()}

    def question_label(self, label: str) -> str:
        """Expand declared criterion aliases in local question matching only."""
        text = label_key(label)
        names = self.names()
        if not names:
            return text
        pattern = r"(?<!\w)(?:" + "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True)) + r")(?!\w)"
        return re.sub(pattern, lambda match: names[match.group()].replace("_", " "), text)

    def has_value_alias(self, value: str, aid: str) -> bool:
        key = label_key(value)
        return key in self.value_aliases.get(aid, {}) or key in self.vocabulary.get(aid, set())

    def register_choices(self, question: dict) -> None:
        """Leader-written form choices are established labels, not synonyms to infer."""
        aid = question["criterion"]
        definition = self.registry.get(aid)
        if definition is None or definition["value_type"] not in TEXT_TYPES:
            return
        for label in question["choices"].values():
            key = label_key(label)
            target = self.value_aliases.get(aid, {}).get(key, key)
            self.vocabulary.setdefault(aid, set()).add(target)

    def _record(self, kind: str, original: object, canonical: object, path: str,
                source: str, status: str = "mapped", attribute_id: str | None = None,
                reason: str | None = None) -> None:
        record = {"kind": kind, "path": path, "attribute_id": attribute_id,
                  "original": original, "canonical": canonical,
                  "source_type": source, "status": status}
        if reason is not None:
            record["reason"] = reason
        self.records.append(record)

    def _assess(self, label: str, kind: str, targets: list[str], path: str,
                definition: dict | None = None, original: str | None = None) -> tuple[str, bool]:
        if not targets:
            return label, False
        payload = {"policy_version": POLICY_VERSION, "kind": kind, "label": label,
                   "decision_question": self.decision_question,
                   "criterion": definition,
                   "targets": ([self.registry[aid] for aid in targets] if kind == "criterion" else targets)}
        key = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        saved = self.assessments.get(key)
        if saved is None:
            if not self.model_enabled:
                return label, False
            if self.replay:
                raise InputError("MISSING_CANONICAL_EVIDENCE", path, "Frozen evidence lacks this label assessment")
            saved = self.provider.canonicalize_sparse_label(payload)
            self.assessments[key] = saved
        saved = require_object(saved, f"semantic.canonicalization.{key}")
        status = require_in(saved.get("status"), {"equivalent", "distinct", "unresolved"}, path)
        target = saved.get("target")
        reason = require_text(saved.get("reason"), path)
        if status == "equivalent":
            if not isinstance(target, str) or target not in targets:
                raise InputError("INVALID_SEMANTIC_RESULT", path, "Canonical target must be one of the supplied labels")
            self._record(kind, original or label, target, path, "semantic_model", reason=reason,
                         attribute_id=(definition or {}).get("attribute_id"))
            return target, True
        if target is not None:
            raise InputError("INVALID_SEMANTIC_RESULT", path, "Distinct or unresolved labels must have a null target")
        self._record(kind, original or label, None, path, "semantic_model", status, (definition or {}).get("attribute_id"), reason)
        if status == "unresolved":
            raise InputError("AMBIGUOUS_CANONICAL_LABEL", path, reason)
        return label, False

    def criterion(self, label: str, path: str, *, allow_model: bool = True) -> tuple[str, bool]:
        label = require_text(label, path)
        target = self.criterion_aliases.get(label_key(label))
        if target is not None:
            if label != target:
                self._record("criterion", label, target, path, "declared_alias" if label_key(label) != label_key(target) else "format")
            return target, False
        if label in {"availability", "max_cost", "duration_days", "preferences", "importance", "unclassified"}:
            return label, False
        if not allow_model:
            return label, False
        return self._assess(label, "criterion", sorted(self.target_ids), path)

    def value(self, value: object, aid: str, path: str, *, allow_model: bool = True) -> tuple[object, bool]:
        definition = self.registry.get(aid)
        if definition is None or definition["value_type"] not in TEXT_TYPES:
            return value, False
        values = value if isinstance(value, list) else [value]
        normalized, used_model = [], False
        for raw in values:
            raw = require_text(raw, path)
            key = label_key(raw)
            target = self.value_aliases.get(aid, {}).get(key)
            if target is not None:
                if raw != target:
                    self._record("value", raw, target, path, "declared_alias", attribute_id=aid)
            elif key in self.vocabulary.get(aid, set()):
                target = key
                if raw != target:
                    self._record("value", raw, target, path, "format", attribute_id=aid)
            elif allow_model:
                record_count = len(self.records)
                target, model = self._assess(key, "value", sorted(self.vocabulary.get(aid, set())), path, definition, raw)
                used_model = used_model or model
                if len(self.records) == record_count and raw != target:
                    self._record("value", raw, target, path, "format", attribute_id=aid)
            else:
                target = key
                if raw != target:
                    self._record("value", raw, target, path, "format", attribute_id=aid)
            normalized.append(target)
        if definition["value_type"] == "tag_set":
            return sorted(set(normalized)), used_model
        if len(normalized) != 1:
            raise InputError("INVALID_VALUE", path, "Category requires one value")
        return normalized[0], used_model

    def prepare_facts(self, candidates: list[dict]) -> None:
        for ci, candidate in enumerate(candidates):
            for fi, fact in enumerate(candidate["facts"]):
                path = f"planning.options[{ci}].facts[{fi}]"
                aid, _ = self.criterion(fact["criterion"], path, allow_model=False)
                fact["criterion"] = aid
                if fact["status"] != "unknown" and self.registry[aid]["value_type"] in TEXT_TYPES:
                    fact["value"], _ = self.value(fact["value"], aid, path, allow_model=False)
                    values = fact["value"] if isinstance(fact["value"], list) else [fact["value"]]
                    self.vocabulary.setdefault(aid, set()).update(values)
            if len({f["criterion"] for f in candidate["facts"]}) != len(candidate["facts"]):
                raise InputError("DUPLICATE_ID", "planning.options.facts", "Aliased facts duplicate a criterion; reconcile their values and sources")

    def confirmation(self, raw: object, path: str) -> object:
        """Normalize reviewed labels with declared aliases only."""
        if isinstance(raw, list):
            return [self.confirmation(item, path) for item in raw]
        if not isinstance(raw, dict) or "attribute_id" not in raw or "required_value" not in raw:
            return raw
        aid, _ = self.criterion(raw["attribute_id"], path, allow_model=False)
        value, _ = self.value(raw["required_value"], aid, path, allow_model=False)
        return {**raw, "attribute_id": aid, "required_value": value}

    def meaning(self, item: dict, path: str) -> tuple[dict, bool]:
        aid, used_model = self.criterion(item["criterion"], path)
        value, model_value = self.value(item["value"], aid, path)
        return {**item, "criterion": aid, "value": value}, used_model or model_value

    def importance(self, entries: list[dict]) -> list[dict]:
        result = []
        for entry in entries:
            entry = dict(entry)
            fields = ("attribute_id",) if entry["kind"] == "multiplier" else ("higher_attribute_id", "lower_attribute_id")
            for field in fields:
                entry[field], model = self.criterion(entry[field], f"responses.participants.{entry['participant_id']}.importance")
                if model:
                    entry["source_type"] = "semantic_model"
            result.append(entry)
        return result

    def packet(self) -> dict:
        return {"policy_version": POLICY_VERSION, "declarations": self.declarations, "records": self.records}
