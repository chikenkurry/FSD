"""Persist private run artifacts with immutable snapshot references."""
import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import uuid4
from contextlib import contextmanager
from copy import deepcopy


class RunStore:
    def __init__(self, path: str):
        if not path:
            raise ValueError("A persistent database path is required")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, run: dict, planning: dict, responses: dict) -> dict:
        run = {**deepcopy(run), "run_id": str(uuid4())}
        material = {"planning": planning, "responses": responses, "output": deepcopy({k: v for k, v in run.items() if k != "run_id"})}
        # A retry reuses identical artifacts. Changed semantic output gets a new run.
        result = material["output"].get("result", {})
        result.pop("run_id", None)
        fingerprint = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
        if "result" in run:
            run["result"]["run_id"] = run["run_id"]
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO runs VALUES (?, ?, ?)", (run["run_id"], fingerprint, json.dumps(run)))
            return json.loads(db.execute("SELECT payload FROM runs WHERE fingerprint = ?", (fingerprint,)).fetchone()[0])

    def get(self, run_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
            return json.loads(row[0]) if row else None
