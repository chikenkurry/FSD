"""Bounded execution with persistent claims and source-versioned semantics."""
from copy import deepcopy
import hashlib
import logging
import os
from pathlib import Path
import threading
import time
from uuid import uuid4

from decision_service.preprocessing.sparse import VERSION as PROCESSING_VERSION
from .store import canonical
from .workflow import execute, preview
from .fact_collection import CollectionUnavailable
from .enrichment import FactEnricher, specification as enrichment_specification
from .snapshots import SnapshotError
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
    revision_key = "GEMINI_FACT_MODEL_REVISION" if kind in {"fact_collection", "research"} else "SEMANTIC_MODEL_REVISION"
    revision = (os.environ.get(revision_key) or getattr(provider,"model","rules")) if provider else "rules"
    return {"kind": kind, "processing_version": PROCESSING_VERSION,
            "implementation_hash": digest.hexdigest(),
            "semantic_provider": getattr(provider, 'provider_name', type(provider).__name__) if provider else "rules",
            "model": getattr(provider, "model", None),
            "job_timeout_seconds": int(os.environ.get("DECISION_JOB_TIMEOUT_SECONDS", "180")),
            "model_revision": revision,
            **({"fact_enrichment": enrichment_specification()} if kind in {"recommendation", "preview"} else {})}


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


class JobQueue:
    """Admission only: safe to run in independently scaled API processes."""
    def __init__(self, store, provider=None, *, fact_collector=None):
        self.store = store
        self.timeout = int(os.environ.get("DECISION_JOB_TIMEOUT_SECONDS", "180"))
        if not 30 <= self.timeout <= 900:
            raise ValueError("DECISION_JOB_TIMEOUT_SECONDS must be between 30 and 900")
        self.specifications = {kind: execution_specification(provider, kind=kind) for kind in ("recommendation", "preview")}
        self.fact_collector = fact_collector
        if fact_collector:
            self.specifications["fact_collection"] = execution_specification(fact_collector,kind="fact_collection")
            # Organiser research shares the collector's model version but runs on its own pool.
            self.specifications["research"] = execution_specification(fact_collector,kind="research")
        self.researcher = None
        self.wake = threading.Event()

    def close(self):
        pass

    def enqueue(self, planning, responses, *, kind="recommendation", retry=False):
        run = self.store.enqueue(planning, responses, self.specifications[kind])
        if retry and run["status"] == "failed":
            run = self.store.retry(run["run_id"],self.specifications[kind])
        self.wake.set()
        return run


class JobWorkers(JobQueue):
    def __init__(self, store, provider=None, *, workers=2, fact_collector=None, kinds=None, lease_seconds=300):
        super().__init__(store, provider, fact_collector=fact_collector)
        if not 1 <= workers <= 8:
            raise ValueError("DECISION_WORKERS must be between 1 and 8")
        if not 5 <= lease_seconds <= 1800:
            raise ValueError('Decision lease must be between 5 and 1800 seconds')
        kinds = kinds or list(self.specifications)
        if len(set(kinds)) != len(kinds) or any(kind not in {'recommendation', 'preview', 'fact_collection', 'research'} for kind in kinds):
            raise ValueError('Unknown or duplicate worker job kinds')
        self.specifications = {kind: spec for kind, spec in self.specifications.items() if kind in kinds}
        if not self.specifications:
            raise ValueError('No configured job kinds for this worker')
        self.provider = CachedSemanticProvider(provider, store, execution_specification(provider)) if provider else None
        self.fact_enricher = FactEnricher(fact_collector, store)
        self.worker_id = str(uuid4())
        self.lease_seconds = lease_seconds
        self.last_presence = 0
        self.stop = threading.Event()
        self.active = {}
        self.active_lock = threading.Lock()
        self.threads = [threading.Thread(target=self.work, daemon=True, name=f"decision-worker-{i}") for i in range(workers)]
        self.presence_thread = threading.Thread(target=self.presence, daemon=True, name='decision-presence')

    def start(self):
        self.register()
        self.store.reap_exhausted()
        for thread in self.threads:
            thread.start()
        self.presence_thread.start()

    def register(self):
        self.store.register_worker(self.worker_id, list(self.specifications.values()), len(self.threads))
        self.last_presence = time.monotonic()

    def presence(self):
        while not self.stop.wait(5):
            try:
                if all(thread.is_alive() for thread in self.threads):
                    self.register()
                    self.store.reap_exhausted()
            except Exception as error:
                logging.error('worker_presence_failed type=%s', type(error).__name__)

    def ready(self):
        return (not self.stop.is_set() and all(thread.is_alive() for thread in self.threads)
                and time.monotonic() - self.last_presence < 15)

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
        if self.presence_thread.is_alive():
            self.presence_thread.join(timeout=1)
        self.store.unregister_worker(self.worker_id)

    def work(self):
        idle_delay = 0.25
        while not self.stop.is_set():
            try:
                job = self.store.claim(list(self.specifications.values()), lease_seconds=self.lease_seconds)
            except Exception as error:
                logging.error("queue_unavailable type=%s", type(error).__name__)
                self.stop.wait(1)
                continue
            if job is None:
                notified = self.wake.wait(timeout=idle_delay)
                self.wake.clear()
                # Local admission wakes this process; remote API processes are
                # detected by a bounded poll, at most one second after enqueue.
                idle_delay = 0.25 if notified else min(1.0, idle_delay * 2)
                continue
            idle_delay = 0.25
            with self.active_lock:
                if self.stop.is_set():
                    self.store.release(job)
                    return
                self.active[job["id"]] = job
            done = threading.Event()
            def heartbeat(claim=job, finished=done):
                while not finished.wait(min(30, self.lease_seconds / 3)):
                    try:
                        if not self.store.renew(claim, self.lease_seconds):
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
                if kind == "research":
                    if not self.researcher or not self.researcher.gemini:
                        raise CollectionUnavailable("FACT_COLLECTOR_NOT_CONFIGURED", retryable=False)
                    planning = inputs["planning"]
                    task = planning["research_task"]
                    output = getattr(self.researcher, {"overviews": "overviews", "questions": "draft_questions", "facts": "facts"}[task])(planning["research_input"])
                    refs = {key: planning[key] for key in ("plan_id", "round_id", "option_revision", "option_snapshot_id")}
                    refs["response_snapshot_id"] = inputs["responses"]["snapshot_id"]
                    run = {"status": "completed", "input_refs": refs, "research": output, "issues": []}
                elif kind == "fact_collection":
                    collection = self.fact_collector.collect(inputs["planning"]["collection_input"])
                    refs = {key: inputs["planning"][key] for key in ("plan_id", "round_id", "option_revision", "option_snapshot_id")}
                    refs["response_snapshot_id"] = inputs["responses"]["snapshot_id"]
                    run = {"status": "needs_review" if collection["claims"] else "needs_information",
                           "input_refs": refs, "collection": collection, "issues": collection["issues"]}
                else:
                    function = preview if kind == "preview" else execute
                    run = function(inputs["planning"], inputs["responses"], semantic_provider=self.provider,
                                   fact_enricher=self.fact_enricher)
                if time.monotonic() > started + self.timeout:
                    self.store.fail(job, "EXECUTION_DEADLINE_EXCEEDED")
                elif run["status"] == "upstream_unavailable":
                    self.store.fail(job, "SEMANTIC_SERVICE_UNAVAILABLE")
                else:
                    self.store.complete(job, run)
                logging.info("job_finished run_id=%s kind=%s status=%s elapsed_ms=%d", job["id"], job["specification"]["kind"], run["status"], (time.monotonic()-started)*1000)
            except SnapshotError:
                self.store.fail(job, "INVALID_RESEARCH_INPUT", max_attempts=job["attempts"])
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
