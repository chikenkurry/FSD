"""Private artifacts and a durable, input-keyed queue for a single SQLite deployment."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


class QueueFull(Exception):
    pass


class RunStore:
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
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT id FROM jobs WHERE fingerprint=?", (fingerprint,)).fetchone()
            if existing:
                return self.get(existing["id"])
            if db.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0] >= 128:
                raise QueueFull("Job capacity reached")
            db.execute("INSERT OR IGNORE INTO jobs (id, fingerprint, inputs, specification, available_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                       (str(uuid4()), fingerprint, canonical(inputs), canonical(specification), now, now))
            row = db.execute("SELECT id FROM jobs WHERE fingerprint = ?", (fingerprint,)).fetchone()
        return self.get(row["id"])

    def claim(self, specification: dict | list, *, lease_seconds: float = 300, max_attempts: int = 3, job_id: str | None = None) -> dict | None:
        """Fence workers by lease token; expired work can be claimed after a restart."""
        now = time.time()
        specifications = specification if isinstance(specification, list) else [specification]
        placeholders = ",".join("?" for _ in specifications)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE jobs SET state='failed', error_code='EXECUTION_RETRY_EXHAUSTED', lease_token=NULL WHERE state='running' AND lease_until < ? AND attempts >= ?",
                       (now, max_attempts))
            query = f"""SELECT * FROM jobs WHERE specification IN ({placeholders}) AND attempts < ? AND
                ((state='queued' AND available_at <= ?) OR (state='running' AND lease_until < ?))
                {"AND id=?" if job_id else ""} ORDER BY created_at LIMIT 1"""
            parameters = (*(canonical(spec) for spec in specifications), max_attempts, now, now)
            if job_id:
                parameters = (*parameters, job_id)
            row = db.execute(query, parameters).fetchone()
            if row is None:
                return None
            token = str(uuid4())
            db.execute("UPDATE jobs SET state='running', attempts=attempts+1, lease_until=?, lease_token=? WHERE id=?",
                       (now + lease_seconds, token, row["id"]))
            return {**dict(row), "lease_token": token, "attempts": row["attempts"] + 1,
                    "inputs": json.loads(row["inputs"]), "specification": json.loads(row["specification"])}

    def renew(self, job: dict, lease_seconds: float = 300) -> bool:
        with self.connect() as db:
            return db.execute("UPDATE jobs SET lease_until=? WHERE id=? AND state='running' AND lease_token=?",
                              (time.time() + lease_seconds, job["id"], job["lease_token"])).rowcount == 1

    def release(self, job: dict) -> None:
        """Graceful shutdown surrenders only this worker's fenced claim."""
        with self.connect() as db:
            db.execute("UPDATE jobs SET state='queued',attempts=max(0,attempts-1),available_at=?,lease_token=NULL,lease_until=NULL WHERE id=? AND state='running' AND lease_token=?",
                       (time.time(),job["id"],job["lease_token"]))

    def complete(self, job: dict, run: dict) -> bool:
        run = {**deepcopy(run), "run_id": job["id"], "job_state": "completed", "execution_specification": job["specification"]}
        if "result" in run:
            run["result"]["run_id"] = job["id"]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("UPDATE jobs SET state='completed', completed_at=?, lease_token=NULL, error_code=NULL WHERE id=? AND state='running' AND lease_token=?",
                                 (time.time(), job["id"], job["lease_token"])).rowcount
            if not changed:
                return False
            db.execute("INSERT INTO runs VALUES (?, ?, ?)", (job["id"], job["fingerprint"], canonical(run)))
            return True

    def fail(self, job: dict, code: str, *, max_attempts: int = 3) -> None:
        with self.connect() as db:
            db.execute("UPDATE jobs SET state=?, available_at=?, error_code=?, lease_token=NULL WHERE id=? AND state='running' AND lease_token=?",
                       ("queued" if job["attempts"] < max_attempts else "failed",
                        time.time() + min(30, 2 ** job["attempts"]), code, job["id"], job["lease_token"]))

    def get(self, run_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row:
                return json.loads(row["payload"])
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
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
            db.execute("INSERT OR IGNORE INTO semantic_cache VALUES (?, ?)", (key, canonical(payload)))
            return json.loads(db.execute("SELECT payload FROM semantic_cache WHERE key=?", (key,)).fetchone()["payload"])

    def health(self) -> dict:
        with self.connect() as db:
            db.execute("SELECT 1")
            return dict(db.execute("SELECT state, count(*) FROM jobs GROUP BY state").fetchall())

    def fail_obsolete(self, specifications: list) -> None:
        placeholders = ",".join("?" for _ in specifications)
        with self.connect() as db:
            db.execute(f"UPDATE jobs SET state='failed', error_code='EXECUTION_VERSION_CHANGED', lease_token=NULL WHERE (state='queued' OR (state='running' AND lease_until < ?)) AND specification NOT IN ({placeholders})",
                       (time.time(), *(canonical(spec) for spec in specifications)))

    def retry(self, run_id: str, specification: dict) -> dict:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state,specification FROM jobs WHERE id=?", (run_id,)).fetchone()
            if row is None or row["specification"] != canonical(specification):
                raise ValueError("Execution version changed; start a new run")
            if row["state"] == "failed":
                if db.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0] >= 128:
                    raise QueueFull("Job capacity reached")
                db.execute("UPDATE jobs SET state='queued',attempts=0,error_code=NULL,available_at=?,lease_token=NULL WHERE id=?", (time.time(),run_id))
        return self.get(run_id)
