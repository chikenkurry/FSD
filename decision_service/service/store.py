"""Private artifacts and a durable queue, with SQLite and PostgreSQL adapters.

The SQL contract is shared; PostgreSQL claims use row locks and SKIP LOCKED.
SQLite remains available for small local processes and historical import.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


class QueueFull(Exception):
    pass


class RunStore:
    postgres = False

    def __init__(self, path: str):
        if not path:
            raise ValueError("A persistent database path is required")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            # Preserve the original table and IDs for historical selections.
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)")
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, inputs TEXT NOT NULL,
                specification TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
                attempts INTEGER NOT NULL DEFAULT 0, available_at REAL NOT NULL,
                lease_until REAL, lease_token TEXT, error_code TEXT,
                created_at REAL NOT NULL, completed_at REAL)""")
            db.execute("CREATE INDEX IF NOT EXISTS jobs_ready ON jobs(state, available_at, lease_until)")
            db.execute("CREATE TABLE IF NOT EXISTS semantic_cache (key TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            columns = {row['name'] for row in db.execute('PRAGMA table_info(jobs)')}
            if 'started_at' not in columns:
                db.execute('ALTER TABLE jobs ADD COLUMN started_at REAL')
            db.execute('CREATE TABLE IF NOT EXISTS worker_presence (id TEXT PRIMARY KEY, specifications TEXT NOT NULL, slots INTEGER NOT NULL, last_seen REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS import_markers (source TEXT PRIMARY KEY, summary TEXT NOT NULL)')
            db.execute("CREATE INDEX IF NOT EXISTS jobs_expired_leases ON jobs(lease_until) WHERE state='running'")

    def close(self):
        pass

    def _write(self, db, *, admission=False):
        db.execute('BEGIN IMMEDIATE')

    def _now(self, db):
        return time.time()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, planning: dict, responses: dict, specification: dict) -> dict:
        inputs = {"planning": planning, "responses": responses}
        fingerprint = hashlib.sha256(canonical({"inputs": inputs, "specification": specification}).encode()).hexdigest()
        with self.connect() as db:
            self._write(db, admission=True)
            now = self._now(db)
            existing = db.execute("SELECT id FROM jobs WHERE fingerprint=?", (fingerprint,)).fetchone()
            if existing:
                return self._get(db, existing["id"])
            if db.execute("SELECT count(*) AS total FROM jobs WHERE state IN ('queued','running')").fetchone()['total'] >= 128:
                raise QueueFull("Job capacity reached")
            db.execute("INSERT INTO jobs (id, fingerprint, inputs, specification, available_at, created_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                       (str(uuid4()), fingerprint, canonical(inputs), canonical(specification), now, now))
            row = db.execute("SELECT id FROM jobs WHERE fingerprint = ?", (fingerprint,)).fetchone()
        return self.get(row["id"])

    def claim(self, specification: dict | list, *, lease_seconds: float = 300, max_attempts: int = 3, job_id: str | None = None) -> dict | None:
        """Fence workers by lease token; expired work can be claimed after a restart."""
        specifications = specification if isinstance(specification, list) else [specification]
        if not specifications:
            return None
        placeholders = ",".join("?" for _ in specifications)
        with self.connect() as db:
            self._write(db)
            now = self._now(db)
            query = f"""SELECT * FROM jobs WHERE specification IN ({placeholders}) AND attempts < ? AND
                ((state='queued' AND available_at <= ?) OR (state='running' AND lease_until < ?))
                {"AND id=?" if job_id else ""} ORDER BY created_at, id LIMIT 1
                {"FOR UPDATE SKIP LOCKED" if self.postgres else ""}"""
            parameters = (*(canonical(spec) for spec in specifications), max_attempts, now, now)
            if job_id:
                parameters = (*parameters, job_id)
            row = db.execute(query, parameters).fetchone()
            if row is None:
                return None
            token = str(uuid4())
            db.execute("UPDATE jobs SET state='running', attempts=attempts+1, lease_until=?, lease_token=?, started_at=? WHERE id=?",
                       (now + lease_seconds, token, now, row["id"]))
            return {**dict(row), "lease_token": token, "attempts": row["attempts"] + 1,
                    "inputs": json.loads(row["inputs"]), "specification": json.loads(row["specification"])}

    def reap_exhausted(self, *, max_attempts: int = 3) -> int:
        """Periodic maintenance; reclaimable leases stay on the normal claim path."""
        with self.connect() as db:
            self._write(db)
            now = self._now(db)
            exhausted = "SELECT id FROM jobs WHERE state='running' AND lease_until < ? AND attempts >= ?"
            if self.postgres:
                exhausted += ' FOR UPDATE SKIP LOCKED'
            return db.execute(
                "UPDATE jobs SET state='failed', error_code='EXECUTION_RETRY_EXHAUSTED', "
                "lease_token=NULL, completed_at=? WHERE id IN (" + exhausted + ")",
                (now, now, max_attempts),
            ).rowcount

    def renew(self, job: dict, lease_seconds: float = 300) -> bool:
        with self.connect() as db:
            return db.execute("UPDATE jobs SET lease_until=? WHERE id=? AND state='running' AND lease_token=?",
                              (self._now(db) + lease_seconds, job["id"], job["lease_token"])).rowcount == 1

    def release(self, job: dict) -> None:
        """Graceful shutdown surrenders only this worker's fenced claim."""
        with self.connect() as db:
            db.execute("UPDATE jobs SET state='queued',attempts=CASE WHEN attempts>0 THEN attempts-1 ELSE 0 END,available_at=?,lease_token=NULL,lease_until=NULL WHERE id=? AND state='running' AND lease_token=?",
                       (self._now(db),job["id"],job["lease_token"]))

    def complete(self, job: dict, run: dict) -> bool:
        run = {**deepcopy(run), "run_id": job["id"], "job_state": "completed", "execution_specification": job["specification"]}
        if "result" in run:
            run["result"]["run_id"] = job["id"]
        with self.connect() as db:
            self._write(db)
            changed = db.execute("UPDATE jobs SET state='completed', completed_at=?, lease_token=NULL, error_code=NULL WHERE id=? AND state='running' AND lease_token=?",
                                 (self._now(db), job["id"], job["lease_token"])).rowcount
            if not changed:
                return False
            db.execute("INSERT INTO runs VALUES (?, ?, ?)", (job["id"], job["fingerprint"], canonical(run)))
            return True

    def fail(self, job: dict, code: str, *, max_attempts: int = 3) -> None:
        with self.connect() as db:
            terminal = job['attempts'] >= max_attempts
            now = self._now(db)
            db.execute("UPDATE jobs SET state=?, available_at=?, error_code=?, lease_token=NULL, completed_at=? WHERE id=? AND state='running' AND lease_token=?",
                       ("failed" if terminal else "queued",
                        now + min(30, 2 ** job["attempts"]), code, now if terminal else None, job["id"], job["lease_token"]))

    def get(self, run_id: str) -> dict | None:
        with self.connect() as db:
            return self._get(db, run_id)

    def _get(self, db, run_id):
        # One statement sees a consistent completion snapshot. CASE avoids
        # transferring frozen inputs when an artifact already exists. Starting
        # from the requested ID also supports historical runs without job rows.
        row = db.execute("""
            SELECT runs.payload AS artifact, jobs.state, jobs.specification,
                   jobs.error_code,
                   CASE WHEN runs.id IS NULL THEN jobs.inputs END AS inputs
            FROM (SELECT ? AS id) AS requested
            LEFT JOIN runs ON runs.id = requested.id
            LEFT JOIN jobs ON jobs.id = requested.id
        """, (run_id,)).fetchone()
        if row['artifact'] is not None:
            return json.loads(row['artifact'])
        if row['state'] is None:
            return None
        inputs = json.loads(row["inputs"])
        plan, response = inputs["planning"], inputs["responses"]
        refs = {key: plan[key] for key in ("plan_id", "round_id", "option_revision", "option_snapshot_id")}
        refs["response_snapshot_id"] = response["snapshot_id"]
        return {"run_id": run_id, "status": "failed" if row["state"] == "failed" else "pending",
                "job_state": row["state"], "input_refs": refs,
                "execution_specification": json.loads(row["specification"]),
                "member_states": {p["participant_id"]: "draft" for p in response.get("participants", [])},
                "response_revision": response.get("response_revision"),
                "issues": [{"code": row["error_code"]}] if row["error_code"] else []}

    def save(self, run: dict, planning: dict, responses: dict) -> dict:
        """Compatibility helper for callers that already computed an artifact."""
        specification = {"kind": "compatibility", "version": "input-key-v1"}
        saved = self.enqueue(planning, responses, specification)
        if saved["status"] == "pending":
            job = self.claim(specification,job_id=saved["run_id"])
            if job:
                self.complete(job, run)
        return self.get(saved["run_id"])

    def cache_get(self, key: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM semantic_cache WHERE key=?", (key,)).fetchone()
            return json.loads(row["payload"]) if row else None

    def cache_put(self, key: str, payload: dict) -> dict:
        with self.connect() as db:
            db.execute("INSERT INTO semantic_cache VALUES (?, ?) ON CONFLICT DO NOTHING", (key, canonical(payload)))
            return json.loads(db.execute("SELECT payload FROM semantic_cache WHERE key=?", (key,)).fetchone()["payload"])

    def ping(self) -> None:
        """Constant-size readiness probe, independent of historical job count."""
        with self.connect() as db:
            db.execute("SELECT 1")

    def health(self) -> dict:
        """Diagnostic counts, kept off the readiness path."""
        with self.connect() as db:
            return {row['state']: row['total'] for row in db.execute("SELECT state, count(*) AS total FROM jobs GROUP BY state")}

    def retry(self, run_id: str, specification: dict) -> dict:
        with self.connect() as db:
            self._write(db, admission=True)
            row = db.execute("SELECT state,specification FROM jobs WHERE id=?" + (' FOR UPDATE' if self.postgres else ''), (run_id,)).fetchone()
            if row is None or row["specification"] != canonical(specification):
                raise ValueError("Execution version changed; start a new run")
            if row["state"] == "failed":
                if db.execute("SELECT count(*) AS total FROM jobs WHERE state IN ('queued','running')").fetchone()['total'] >= 128:
                    raise QueueFull("Job capacity reached")
                db.execute("UPDATE jobs SET state='queued',attempts=0,error_code=NULL,available_at=?,lease_token=NULL,lease_until=NULL,completed_at=NULL WHERE id=?", (self._now(db),run_id))
        return self.get(run_id)

    def register_worker(self, worker_id, specifications, slots):
        with self.connect() as db:
            now = self._now(db)
            db.execute('INSERT INTO worker_presence VALUES (?,?,?,?) ON CONFLICT (id) DO UPDATE SET specifications=excluded.specifications, slots=excluded.slots, last_seen=excluded.last_seen',
                       (worker_id, canonical(specifications), slots, now))
            db.execute('DELETE FROM worker_presence WHERE last_seen < ?', (now - 3600,))

    def unregister_worker(self, worker_id):
        with self.connect() as db:
            db.execute('DELETE FROM worker_presence WHERE id=?', (worker_id,))

    def active_workers(self):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM worker_presence WHERE last_seen >= ?', (self._now(db) - 30,)).fetchall()
        return [{**dict(row), 'specifications': json.loads(row['specifications'])} for row in rows]

    def supports(self, specifications):
        active = {canonical(spec) for worker in self.active_workers() for spec in worker['specifications']}
        return all(canonical(spec) in active for spec in specifications)

    def retire_implementation(self, implementation_hash):
        """Explicit operator action after draining/removing an old worker release."""
        with self.connect() as db:
            self._write(db, admission=True)
            now = self._now(db)
            workers = db.execute('SELECT specifications FROM worker_presence WHERE last_seen >= ?', (now-30,)).fetchall()
            if any(spec.get('implementation_hash') == implementation_hash for worker in workers for spec in json.loads(worker['specifications'])):
                raise ValueError('Matching workers are still active')
            rows = db.execute("SELECT id,specification,state,lease_until FROM jobs WHERE state IN ('queued','running')" + (' FOR UPDATE' if self.postgres else '')).fetchall()
            matching = [row for row in rows if json.loads(row['specification']).get('implementation_hash') == implementation_hash]
            if any(row['state'] == 'running' and (row['lease_until'] or 0) > now for row in matching):
                raise ValueError('Matching jobs still have live leases')
            for row in matching:
                db.execute("UPDATE jobs SET state='failed',error_code='EXECUTION_VERSION_RETIRED',completed_at=?,lease_token=NULL WHERE id=?", (now,row['id']))
            return len(matching)

    def metrics(self):
        """Bounded sample, no member inputs or model evidence in operational metrics."""
        with self.connect() as db:
            now = self._now(db)
            pending = db.execute("SELECT specification, state, created_at FROM jobs WHERE state IN ('queued','running')").fetchall()
            recent = db.execute('SELECT created_at, started_at, completed_at, attempts, state FROM jobs WHERE completed_at IS NOT NULL ORDER BY completed_at DESC LIMIT 500').fetchall()
            cache = db.execute('SELECT count(*) AS total FROM semantic_cache').fetchone()['total']
        def percentile(values, fraction):
            values = sorted(values)
            return round(values[min(len(values)-1, int((len(values)-1)*fraction))], 3) if values else None
        waiting = [max(0, row['started_at']-row['created_at']) for row in recent if row['started_at'] is not None]
        processing = [max(0, row['completed_at']-row['started_at']) for row in recent if row['started_at'] is not None]
        workers = self.active_workers()
        active_specs = {canonical(spec) for worker in workers for spec in worker['specifications']}
        return {'jobs': self.health(), 'pending_by_kind': {
                    kind: sum(json.loads(row['specification']).get('kind') == kind for row in pending)
                    for kind in ('preview', 'recommendation', 'fact_collection')},
                'oldest_pending_seconds': round(max((now-row['created_at'] for row in pending), default=0), 3),
                'sample_size': len(recent), 'queue_wait_seconds_p95': percentile(waiting, .95),
                'last_attempt_seconds_p95': percentile(processing, .95),
                'sample_retry_attempts': sum(max(0,row['attempts']-1) for row in recent),
                'cache_entries': cache, 'worker_processes': len(workers),
                'pending_without_worker': sum(row['specification'] not in active_specs for row in pending),
                'pending_implementations': sorted({json.loads(row['specification']).get('implementation_hash', 'unknown') for row in pending}),
                'worker_slots': sum(row['slots'] for row in workers)}


def open_store(database_url=None, path=None, *, migrate=True):
    url = database_url if database_url is not None else os.environ.get('DECISION_DATABASE_URL')
    if url:
        from .postgres_store import PostgresRunStore
        return PostgresRunStore(url, schema=os.environ.get('DECISION_DB_SCHEMA', 'public'),
                                pool_size=int(os.environ.get('DECISION_DB_POOL_SIZE', '8')), migrate=migrate)
    return RunStore(path or os.environ.get('DECISION_DB_PATH', '/data/runs.sqlite'))
