"""Bounded execution with persistent claims and source-versioned semantics."""
from copy import deepcopy
import hashlib
import logging
import os
from pathlib import Path
import threading
import time

from decision_service.preprocessing.sparse import VERSION as PROCESSING_VERSION
from .store import canonical
from .workflow import execute, preview
from .fact_collection import CollectionUnavailable
from decision_service.deadlines import deadline, remaining_timeout
from decision_service.preprocessing.semantics import SemanticServiceError


def execution_specification(provider=None, *, kind="recommendation") -> dict:
    root = Path(__file__).parents[1]
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if any(part in {"tests", "fixtures", "evaluation", "app"} for part in path.relative_to(root).parts):
            continue
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    revision_key = "GEMINI_FACT_MODEL_REVISION" if kind == "fact_collection" else "SEMANTIC_MODEL_REVISION"
    revision = (os.environ.get(revision_key) or getattr(provider,"model","rules")) if provider else "rules"
    return {"kind": kind, "processing_version": PROCESSING_VERSION,
            "implementation_hash": digest.hexdigest(),
            "semantic_provider": type(provider).__name__ if provider else "rules",
            "model": getattr(provider, "model", None),
            "job_timeout_seconds": int(os.environ.get("DECISION_JOB_TIMEOUT_SECONDS", "180")),
            "model_revision": revision}


class CachedSemanticProvider:
    """Reuse exact calls across previews and runs; keep cached values private."""
    def __init__(self, provider, store, specification):
        self.provider, self.store, self.specification = provider, store, specification
        self.model = provider.model
        self.locks = [threading.Lock() for _ in range(64)]

    def __getattr__(self, method):
        function = getattr(self.provider, method)
        if not callable(function):
            return function
        def cached(*args, **kwargs):
            try:
                remaining_timeout(180)
            except TimeoutError:
                raise SemanticServiceError("Execution deadline exceeded") from None
            started = time.monotonic()
            key = hashlib.sha256(canonical({"specification": self.specification, "method": method,
                                            "args": args, "kwargs": kwargs}).encode()).hexdigest()
            with self.locks[int(key[:8], 16) % len(self.locks)]:
                payload = self.store.cache_get(key)
                hit = payload is not None
                if payload is None:
                    payload = self.store.cache_put(key, function(*args, **kwargs))
                logging.info("semantic_call method=%s cache_hit=%s elapsed_ms=%d",method,hit,(time.monotonic()-started)*1000)
                return deepcopy(payload)
        return cached


class JobWorkers:
    def __init__(self, store, provider=None, *, workers=2, fact_collector=None):
        if not 1 <= workers <= 8:
            raise ValueError("DECISION_WORKERS must be between 1 and 8")
        self.store = store
        self.timeout = int(os.environ.get("DECISION_JOB_TIMEOUT_SECONDS", "180"))
        if not 30 <= self.timeout <= 900:
            raise ValueError("DECISION_JOB_TIMEOUT_SECONDS must be between 30 and 900")
        self.specifications = {kind: execution_specification(provider, kind=kind) for kind in ("recommendation", "preview")}
        self.fact_collector = fact_collector
        if fact_collector:
            self.specifications["fact_collection"] = execution_specification(fact_collector,kind="fact_collection")
        self.provider = CachedSemanticProvider(provider, store, self.specifications["recommendation"]) if provider else None
        self.stop = threading.Event()
        self.active = {}
        self.active_lock = threading.Lock()
        self.wake = threading.Event()
        self.threads = [threading.Thread(target=self.work, daemon=True, name=f"decision-worker-{i}") for i in range(workers)]

    def start(self):
        for thread in self.threads:
            thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        until = time.monotonic()+2
        for thread in self.threads:
            thread.join(timeout=max(0,until-time.monotonic()))
        with self.active_lock:
            active = list(self.active.values())
        for job in active:
            self.store.release(job)

    def enqueue(self, planning, responses, *, kind="recommendation", retry=False):
        run = self.store.enqueue(planning, responses, self.specifications[kind])
        if retry and run["status"] == "failed":
            run = self.store.retry(run["run_id"],self.specifications[kind])
        self.wake.set()
        return run

    def work(self):
        checked = 0
        while not self.stop.is_set():
            try:
                if time.monotonic() - checked > 30:
                    self.store.fail_obsolete(list(self.specifications.values()))
                    checked = time.monotonic()
                job = self.store.claim(list(self.specifications.values()))
            except Exception as error:
                logging.error("queue_unavailable type=%s", type(error).__name__)
                self.stop.wait(1)
                continue
            if job is None:
                self.wake.wait(timeout=0.25)
                self.wake.clear()
                continue
            with self.active_lock:
                if self.stop.is_set():
                    self.store.release(job)
                    return
                self.active[job["id"]] = job
            done = threading.Event()
            def heartbeat(claim=job, finished=done):
                while not finished.wait(30):
                    try:
                        if not self.store.renew(claim):
                            return
                    except Exception:
                        return
            pulse = threading.Thread(target=heartbeat, daemon=True)
            pulse.start()
            started = time.monotonic()
            budget = deadline.set(started + self.timeout)
            try:
                inputs = job["inputs"]
                kind = job["specification"]["kind"]
                if kind == "fact_collection":
                    collection = self.fact_collector.collect(inputs["planning"]["collection_input"])
                    refs = {key: inputs["planning"][key] for key in ("plan_id", "round_id", "option_revision", "option_snapshot_id")}
                    refs["response_snapshot_id"] = inputs["responses"]["snapshot_id"]
                    run = {"status": "needs_review" if collection["claims"] else "needs_information",
                           "input_refs": refs, "collection": collection, "issues": collection["issues"]}
                else:
                    function = preview if kind == "preview" else execute
                    run = function(inputs["planning"], inputs["responses"], semantic_provider=self.provider)
                if time.monotonic() > started + self.timeout:
                    self.store.fail(job, "EXECUTION_DEADLINE_EXCEEDED")
                elif run["status"] == "upstream_unavailable":
                    self.store.fail(job, "SEMANTIC_SERVICE_UNAVAILABLE")
                else:
                    self.store.complete(job, run)
                logging.info("job_finished run_id=%s kind=%s status=%s elapsed_ms=%d", job["id"], job["specification"]["kind"], run["status"], (time.monotonic()-started)*1000)
            except CollectionUnavailable as error:
                self.store.fail(job, error.code, max_attempts=3 if error.retryable else job["attempts"])
            except Exception as error:
                logging.error("job_failed run_id=%s type=%s", job["id"], type(error).__name__)
                self.store.fail(job, "EXECUTION_FAILED")
            finally:
                with self.active_lock:
                    self.active.pop(job["id"],None)
                deadline.reset(budget)
                done.set()
                pulse.join(timeout=1)
