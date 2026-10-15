"""Real PostgreSQL contract checks; enabled by DECISION_TEST_DATABASE_URL.

Every test owns a disposable schema. The configured database must be dedicated
to tests; no production tables are truncated or reused.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from decision_service.service.postgres_store import PostgresRunStore
from decision_service.service.store import QueueFull
from decision_service.service.workflow import execute
from decision_service.tests.test_service_integration import snapshots


@unittest.skipUnless(os.environ.get('DECISION_TEST_DATABASE_URL'), 'PostgreSQL test database not configured')
class PostgresStoreTests(unittest.TestCase):
    def setUp(self):
        self.url = os.environ['DECISION_TEST_DATABASE_URL']
        self.schema = 'decision_test_' + uuid4().hex
        self.store = PostgresRunStore(self.url, schema=self.schema)
        self.plan, self.responses = snapshots()
        self.spec = {'kind': 'recommendation', 'implementation_hash': 'fixture-v1'}

    def tearDown(self):
        from psycopg import sql
        try:
            with self.store.pool.connection() as db:
                db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        finally:
            self.store.close()

    def another(self):
        return PostgresRunStore(self.url, schema=self.schema, pool_size=2)

    def test_concurrent_admission_has_one_stable_identity(self):
        with ThreadPoolExecutor(max_workers=16) as pool:
            runs = list(pool.map(lambda _: self.store.enqueue(self.plan, self.responses, self.spec), range(48)))
        self.assertEqual(len({row['run_id'] for row in runs}), 1)

    def test_independent_consumers_claim_distinct_jobs_and_reuse_artifacts(self):
        other = self.another()
        try:
            ids = {self.store.enqueue(self.plan, {**self.responses, 'snapshot_id': str(n)}, self.spec)['run_id'] for n in range(32)}
            with ThreadPoolExecutor(max_workers=8) as pool:
                claims = list(pool.map(lambda n: (self.store if n % 2 else other).claim(self.spec), range(40)))
            claimed = [row for row in claims if row]
            self.assertEqual({row['id'] for row in claimed}, ids)
            self.assertEqual(len(claimed), 32)
            artifact = execute(self.plan, self.responses)
            for claim in claimed:
                self.assertTrue(other.complete(claim, artifact))
                self.assertEqual(self.store.get(claim['id'])['status'], 'ranked')
            self.assertEqual(self.store.metrics()['sample_size'], 32)
        finally:
            other.close()

    def test_skip_locked_does_not_wait_for_an_unrelated_claim(self):
        first = self.store.enqueue(self.plan, self.responses, self.spec)
        second = self.store.enqueue(self.plan, {**self.responses, 'snapshot_id': 'second'}, self.spec)
        with self.store.connect() as db:
            db.execute('SELECT id FROM jobs WHERE id=? FOR UPDATE', (first['run_id'],))
            claim = self.store.claim(self.spec)
            self.assertEqual(claim['id'], second['run_id'])

    def test_dead_worker_recovers_and_stale_token_cannot_change_replacement(self):
        queued = self.store.enqueue(self.plan, self.responses, self.spec)
        original = self.store.claim(self.spec)
        with self.store.connect() as db:
            db.execute('UPDATE jobs SET lease_until=0 WHERE id=?', (queued['run_id'],))
        other = self.another()
        try:
            replacement = other.claim(self.spec)
            self.assertEqual(replacement['attempts'], 2)
            self.assertFalse(self.store.renew(original))
            self.store.fail(original, 'STALE_FAILURE')
            self.store.release(original)
            self.assertFalse(self.store.complete(original, execute(self.plan, self.responses)))
            self.assertTrue(other.complete(replacement, execute(self.plan, self.responses)))
        finally:
            other.close()

    def test_claims_are_scoped_to_version_and_kind_during_rollouts(self):
        old = self.store.enqueue(self.plan, self.responses, self.spec)
        preview = self.store.enqueue(self.plan, self.responses, {**self.spec, 'kind': 'preview'})
        newer = {**self.spec, 'implementation_hash': 'fixture-v2'}
        self.assertIsNone(self.store.claim(newer))
        self.assertEqual(self.store.get(old['run_id'])['status'], 'pending')
        self.assertEqual(self.store.claim({**self.spec, 'kind': 'preview'})['id'], preview['run_id'])
        self.assertEqual(self.store.claim(self.spec)['id'], old['run_id'])

    def test_global_capacity_survives_concurrent_admission_and_allows_duplicates(self):
        def admit(n):
            try:
                return self.store.enqueue(self.plan, {**self.responses, 'snapshot_id': str(n)}, self.spec)
            except QueueFull:
                return None
        with ThreadPoolExecutor(max_workers=16) as pool:
            runs = list(pool.map(admit, range(144)))
        self.assertEqual(sum(row is not None for row in runs), 128)
        admitted = next(row for row in runs if row is not None)
        snapshot_id = admitted['input_refs']['response_snapshot_id']
        self.assertIsNotNone(self.store.enqueue(self.plan, {**self.responses, 'snapshot_id': snapshot_id}, self.spec))

    def test_explicit_failure_retry_and_success_immutability(self):
        queued = self.store.enqueue(self.plan, self.responses, self.spec)
        original = self.store.claim(self.spec)
        self.store.fail(original, 'FIXTURE_FAILURE', max_attempts=1)
        self.assertEqual(self.store.get(queued['run_id'])['status'], 'failed')
        self.store.retry(queued['run_id'], self.spec)
        replacement = self.store.claim(self.spec)
        self.assertEqual(replacement['attempts'], 1)
        self.store.complete(replacement, execute(self.plan, self.responses))
        self.assertEqual(self.store.retry(queued['run_id'], self.spec)['status'], 'ranked')

    def test_cached_values_are_shared_and_first_accepted_value_is_preserved(self):
        other = self.another()
        try:
            self.store.cache_put('fixture-key', {'value': 1})
            self.assertEqual(other.cache_get('fixture-key'), {'value': 1})
            self.assertEqual(other.cache_put('fixture-key', {'value': 2}), {'value': 1})
        finally:
            other.close()

    def test_worker_presence_tracks_exact_capabilities(self):
        self.store.register_worker('fixture-worker', [self.spec], 2)
        self.assertTrue(self.store.supports([self.spec]))
        self.assertFalse(self.store.supports([{**self.spec, 'kind': 'preview'}]))
        with self.store.connect() as db:
            db.execute('UPDATE worker_presence SET last_seen=0')
        self.assertFalse(self.store.supports([self.spec]))

    def test_schema_migration_replay_and_checksum_detection(self):
        other = self.another()
        other.close()
        with self.store.connect() as db:
            db.execute("UPDATE decision_schema_migrations SET checksum='changed'")
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.another()

    def test_sqlite_import_preserves_historical_ids_cache_and_reports_old_pending_work(self):
        from decision_service.service.store import RunStore
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'legacy.sqlite')
            legacy = RunStore(path)
            artifact = legacy.save(execute(self.plan, self.responses), self.plan, self.responses)
            pending = legacy.enqueue(self.plan, {**self.responses, 'snapshot_id': 'pending'}, self.spec)
            legacy.cache_put('old-key', {'value': 'cached'})
            summary = self.store.import_sqlite(path)
            self.assertEqual(summary['runs'], 1)
            self.assertEqual(self.store.get(artifact['run_id']), artifact)
            failed = self.store.get(pending['run_id'])
            self.assertEqual(failed['issues'][0]['code'], 'EXECUTION_VERSION_CHANGED')
            self.assertEqual(self.store.cache_get('old-key'), {'value': 'cached'})
            self.assertTrue(self.store.import_sqlite(path)['already_imported'])
            self.assertEqual(legacy.get(pending['run_id'])['status'], 'pending')

    def test_import_conflict_rolls_back_entire_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'legacy.sqlite')
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE runs (id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)')
                db.executemany('INSERT INTO runs VALUES (?,?,?)', [('new', 'new', '{}'), ('same', 'conflict', '{}')])
            with self.store.connect() as db:
                db.execute('INSERT INTO runs VALUES (?,?,?)', ('same', 'existing', '{}'))
            with self.assertRaisesRegex(ValueError, 'conflicts'):
                self.store.import_sqlite(path)
            self.assertIsNone(self.store.get('new'))

    def test_missing_source_does_not_mark_import_finished(self):
        self.assertEqual(self.store.import_sqlite('/nonexistent/legacy.sqlite'), {'source_missing': True})
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) AS total FROM import_markers').fetchone()['total'], 0)

    def test_readonly_wal_import_preserves_uncheckpointed_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'runs.sqlite'
            legacy = sqlite3.connect(path)
            try:
                legacy.execute('PRAGMA journal_mode=WAL')
                legacy.execute('CREATE TABLE runs (id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)')
                legacy.execute('INSERT INTO runs VALUES (?,?,?)', ('wal-id', 'wal-hash', json.dumps({'run_id':'wal-id','status':'ranked'})))
                legacy.commit()
                before = {p.name:p.read_bytes() for p in Path(directory).iterdir()}
                Path(directory).chmod(0o500)
                self.assertEqual(self.store.import_sqlite(path)['runs'], 1)
                self.assertEqual(self.store.get('wal-id')['status'], 'ranked')
                self.assertEqual({p.name:p.read_bytes() for p in Path(directory).iterdir()}, before)
            finally:
                Path(directory).chmod(0o700)
                legacy.close()

    def test_explicit_retirement_refuses_active_workers_and_live_leases(self):
        queued = self.store.enqueue(self.plan, self.responses, self.spec)
        self.store.register_worker('old-release', [self.spec], 1)
        with self.assertRaisesRegex(ValueError, 'active'):
            self.store.retire_implementation('fixture-v1')
        self.store.unregister_worker('old-release')
        self.store.claim(self.spec)
        with self.assertRaisesRegex(ValueError, 'live leases'):
            self.store.retire_implementation('fixture-v1')
        with self.store.connect() as db:
            db.execute('UPDATE jobs SET lease_until=0')
        self.assertEqual(self.store.retire_implementation('fixture-v1'), 1)
        self.assertEqual(self.store.get(queued['run_id'])['issues'][0]['code'], 'EXECUTION_VERSION_RETIRED')

    def test_readonly_runtime_verifies_schema_without_running_ddl(self):
        other = PostgresRunStore(self.url, schema=self.schema, migrate=False)
        try:
            self.assertEqual(other.health(), {})
        finally:
            other.close()
