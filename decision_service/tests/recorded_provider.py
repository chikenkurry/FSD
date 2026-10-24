"""Supply saved model replies to regression tests without calling a service."""

import copy
import hashlib
import json
from collections import defaultdict, deque


class RecordedSparseProvider:
    def __init__(self, evidence: dict, responses: dict):
        self.model = "recorded:" + (evidence.get("model") or "rules")
        self.evidence = evidence
        self.answers = defaultdict(deque)
        self.dates = defaultdict(deque)
        for participant in responses["participants"]:
            pid = participant["participant_id"]
            for answer in participant["answers"]:
                qid, value = answer["question_id"], answer["value"]
                if not isinstance(value, str):
                    continue
                for collection, field in ((self.answers, "answer_assessments"), (self.dates, "date_assessments")):
                    reply = evidence.get(field, {}).get(pid, {}).get(qid)
                    if reply is not None:
                        collection[qid, value].append(reply)

    def classify_question(self, question, context):
        return copy.deepcopy(self.evidence["question_assessments"][question["question_id"]])

    def extract_sparse_answer(self, question, answer_text, context):
        return copy.deepcopy(self.answers[question["question_id"], answer_text].popleft())

    def extract_sparse_dates(self, question, answer_text, context):
        return copy.deepcopy(self.dates[question["question_id"], answer_text].popleft())

    def suggest_option_tags(self, option, criteria, context):
        return copy.deepcopy(self.evidence.get("option_suggestions", {})[option["option_id"]])

    def __getattr__(self, name):
        if name != "canonicalize_sparse_label" or not self.evidence.get("canonicalization_enabled", False):
            raise AttributeError(name)
        return self._canonical_reply

    def _canonical_reply(self, payload):
        key = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return copy.deepcopy(self.evidence["canonical_assessments"][key])
