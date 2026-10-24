"""Test/benchmark instrumentation; never logs SQL parameters or member payloads."""
from contextlib import contextmanager
import threading

from decision_service.service.store import canonical


class SQLCounter:
    def __init__(self, store):
        self.store, self.original = store, store.connect
        self.lock = threading.Lock()
        self.statements = self.returned_bytes = 0

    def record(self, row):
        if row is not None:
            with self.lock:
                self.returned_bytes += len(canonical(dict(row)).encode())
        return row

    @contextmanager
    def connect(self):
        counter = self
        with self.original() as db:
            class Connection:
                def execute(self, query, parameters=()):
                    with counter.lock:
                        counter.statements += 1
                    cursor = db.execute(query, parameters)
                    class Cursor:
                        def fetchone(self):
                            return counter.record(cursor.fetchone())
                        def fetchall(self):
                            return [counter.record(row) for row in cursor.fetchall()]
                        def __iter__(self):
                            return (counter.record(row) for row in cursor)
                        def __getattr__(self, name):
                            return getattr(cursor, name)
                    return Cursor()
            yield Connection()

    def __enter__(self):
        self.store.connect = self.connect
        return self

    def __exit__(self, *_):
        self.store.connect = self.original

    def report(self):
        return {'statements':self.statements, 'returned_fields_json_bytes':self.returned_bytes}
