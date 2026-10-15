from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import threading
import unittest
from unittest.mock import patch

from decision_service.service.jobs import CachedSemanticProvider, JobWorkers
from decision_service.service.store import QueueFull, RunStore
from decision_service.service.workflow import execute, preview
from decision_service.deadlines import deadline, remaining_timeout
from decision_service.tests.test_service_integration import snapshots


class DurableJobTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = RunStore(str(Path(self.directory.name) / "runs.sqlite"))
        self.plan, self.responses = snapshots()
        self.spec = {"kind": "recommendation", "implementation_hash": "test-v1"}

    def tearDown(self):
        self.directory.cleanup()

    def test_concurrent_requests_claim_one_input_before_computation(self):
        def enqueue(_):
            return self.store.enqueue(self.plan, self.responses, self.spec)["run_id"]
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(enqueue, range(16)))
        self.assertEqual(len(set(ids)), 1)
        first = self.store.claim(self.spec)
        self.assertIsNotNone(first)
        self.assertIsNone(self.store.claim(self.spec))
        self.store.complete(first, execute(self.plan, self.responses))
        self.assertEqual(self.store.enqueue(self.plan, self.responses, self.spec)["status"], "ranked")

    def test_first_authoritative_artifact_is_reused_even_if_model_output_changes(self):
        first = execute(self.plan, self.responses)
        a = self.store.save(first, self.plan, self.responses)
        second = deepcopy(first)
        second["result"]["ranked_candidates"].reverse()
        b = self.store.save(second, self.plan, self.responses)
        self.assertEqual(a, b)

    def test_expired_worker_is_fenced_after_restart(self):
        self.store.enqueue(self.plan, self.responses, self.spec)
        now = time.time()
        with patch("decision_service.service.store.time.time", return_value=now):
            original = self.store.claim(self.spec, lease_seconds=1)
        restarted = RunStore(self.store.path)
        with patch("decision_service.service.store.time.time", return_value=now + 2):
            replacement = restarted.claim(self.spec)
        artifact = execute(self.plan, self.responses)
        self.assertFalse(self.store.complete(original, artifact))
        self.assertFalse(self.store.renew(original))
        self.assertTrue(restarted.complete(replacement, artifact))
        self.assertEqual(restarted.get(replacement["id"])["status"], "ranked")

    def test_graceful_release_requeues_without_consuming_failure_attempts(self):
        self.store.enqueue(self.plan,self.responses,self.spec)
        original=self.store.claim(self.spec)
        self.store.release(original)
        replacement=self.store.claim(self.spec)
        self.assertEqual(replacement["id"],original["id"])
        self.assertEqual(replacement["attempts"],1)
        self.assertFalse(self.store.complete(original,execute(self.plan,self.responses)))

    def test_implementation_and_model_versions_create_distinct_jobs(self):
        original = self.store.enqueue(self.plan, self.responses, self.spec)
        changed = self.store.enqueue(self.plan, self.responses, {**self.spec, "model": "different"})
        self.assertNotEqual(original["run_id"], changed["run_id"])

    def test_failed_jobs_have_bounded_retries_and_safe_diagnostics(self):
        run = self.store.enqueue(self.plan, self.responses, self.spec)
        now = time.time()
        for attempt in range(3):
            with patch("decision_service.service.store.time.time", return_value=now + attempt * 100):
                job = self.store.claim(self.spec)
                self.store.fail(job, "SEMANTIC_SERVICE_UNAVAILABLE")
        failed = self.store.get(run["run_id"])
        self.assertEqual(failed["status"], "failed")
        self.assertNotIn("participants", json.dumps(failed["issues"]))
        self.assertIsNone(self.store.claim(self.spec))

    def test_rolling_versions_only_claim_their_own_work(self):
        run = self.store.enqueue(self.plan, self.responses, self.spec)
        replacement = {**self.spec, 'implementation_hash': 'test-v2'}
        self.assertIsNone(self.store.claim(replacement))
        self.assertEqual(self.store.get(run['run_id'])['status'], 'pending')
        self.assertEqual(self.store.claim(self.spec)['id'], run['run_id'])

    def test_pending_admission_is_bounded_but_duplicates_remain_readable(self):
        original = self.store.enqueue(self.plan, self.responses, self.spec)
        for n in range(127):
            self.store.enqueue(self.plan, {**self.responses, "snapshot_id": str(n)}, self.spec)
        self.assertEqual(self.store.enqueue(self.plan, self.responses, self.spec)["run_id"], original["run_id"])
        with self.assertRaises(QueueFull):
            self.store.enqueue(self.plan, {**self.responses, "snapshot_id": "over-capacity"}, self.spec)

    def test_existing_artifact_ids_survive_queue_schema_migration(self):
        old_path = str(Path(self.directory.name) / "legacy.sqlite")
        artifact = {"run_id": "historical", "status": "ranked"}
        with sqlite3.connect(old_path) as db:
            db.execute("CREATE TABLE runs(id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)")
            db.execute("INSERT INTO runs VALUES(?,?,?)", ("historical", "old-hash", json.dumps(artifact)))
        self.assertEqual(RunStore(old_path).get("historical"), artifact)

    def test_workers_execute_once_and_restart_reads_completed_artifact(self):
        workers = JobWorkers(self.store, workers=2)
        with patch("decision_service.service.jobs.execute", wraps=execute) as function:
            workers.start()
            try:
                run = workers.enqueue(self.plan, self.responses)
                workers.enqueue(self.plan, self.responses)
                for _ in range(100):
                    if self.store.get(run["run_id"])["status"] != "pending":
                        break
                    threading.Event().wait(0.01)
                self.assertEqual(self.store.get(run["run_id"])["status"], "ranked")
                self.assertEqual(function.call_count, 1)
            finally:
                workers.close()
        self.assertEqual(RunStore(self.store.path).get(run["run_id"])["status"], "ranked")

    def test_semantic_calls_are_coalesced_and_private_cache_returns_copies(self):
        class Provider:
            model = "fixture-model"
            calls = 0
            def extract_sparse_answer(self, *args):
                self.calls += 1
                return {"items": [{"value": "private fixture"}]}
        provider = Provider()
        cached = CachedSemanticProvider(provider, self.store, self.spec)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: cached.extract_sparse_answer({}, "answer", {}), range(16)))
        self.assertEqual(provider.calls, 1)
        results[0]["items"].clear()
        self.assertTrue(cached.extract_sparse_answer({}, "answer", {})["items"])

    def test_draft_preview_has_exact_revision_and_cannot_rank(self):
        response = {**deepcopy(self.responses), "response_revision": 7}
        response["participants"][0]["response_status"] = "incomplete"
        run = preview(self.plan, response)
        self.assertEqual(run["response_revision"], 7)
        self.assertNotIn("result", run)
        self.assertTrue(run["processing"]["preparation"]["preferences"])

    def test_queue_is_fifo_across_job_kinds(self):
        preview_spec = {**self.spec, "kind": "preview"}
        first = self.store.enqueue(self.plan,self.responses,preview_spec)
        self.store.enqueue(self.plan,self.responses,self.spec)
        claimed = self.store.claim([self.spec,preview_spec])
        self.assertEqual(claimed["id"],first["run_id"])

    def test_explicit_retry_preserves_identity_and_does_not_replace_success(self):
        queued = self.store.enqueue(self.plan,self.responses,self.spec)
        job = self.store.claim(self.spec)
        self.store.fail(job,"FIXTURE_FAILURE",max_attempts=1)
        retried = self.store.retry(queued["run_id"],self.spec)
        self.assertEqual(retried["run_id"],queued["run_id"])
        self.assertEqual(retried["status"],"pending")
        job = self.store.claim(self.spec)
        self.store.complete(job,execute(self.plan,self.responses))
        self.assertEqual(self.store.retry(queued["run_id"],self.spec)["status"],"ranked")
        with self.assertRaises(ValueError):
            self.store.retry(queued["run_id"],{**self.spec,"implementation_hash":"other"})

    def test_provider_timeout_respects_remaining_job_budget(self):
        token = deadline.set(time.monotonic()+0.5)
        try:
            self.assertLessEqual(remaining_timeout(120),0.5)
        finally:
            deadline.reset(token)
        token = deadline.set(time.monotonic()-1)
        try:
            with self.assertRaises(TimeoutError):
                remaining_timeout(120)
        finally:
            deadline.reset(token)
