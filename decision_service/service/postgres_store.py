"""Pooled PostgreSQL storage with checksummed migrations and fenced queue claims."""
from contextlib import closing, contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import shutil
import tempfile

from .store import RunStore, canonical


@contextmanager
def legacy_snapshot(source):
    """SQLite may need writable WAL sidecars even for a read-only connection.

    Copy the quiesced DB/WAL into a private temporary directory and reconstruct
    shared-memory metadata there. Never checkpoint or write the legacy volume.
    """
    def signature():
        return {suffix: (path.stat().st_size, path.stat().st_mtime_ns)
                for suffix in ('', '-wal') if (path := Path(str(source)+suffix)).is_file()}
    before = signature()
    with tempfile.TemporaryDirectory(prefix='decision-import-') as directory:
        target = Path(directory) / 'runs.sqlite'
        for suffix in before:
            shutil.copyfile(str(source)+suffix, str(target)+suffix)
        if signature() != before:
            raise ValueError('Legacy database changed during import; stop its writers')
        yield target


class _Connection:
    # Queries are static application SQL; values always use driver parameters.
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, parameters=()):
        return self.connection.execute(query.replace('?', '%s'), parameters)


class PostgresRunStore(RunStore):
    postgres = True

    def __init__(self, url, *, schema='public', pool_size=8, migrate=True):
        from psycopg.conninfo import make_conninfo
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema):
            raise ValueError('Invalid Decision database schema')
        if not 1 <= pool_size <= 32:
            raise ValueError('Decision connection pool must have 1-32 connections')
        self.schema = schema
        self.pool = ConnectionPool(
            make_conninfo(url, options=f'-csearch_path={schema}'), min_size=1, max_size=pool_size,
            timeout=5, max_waiting=64, open=False, name='decision-db',
            kwargs={'row_factory': dict_row, 'connect_timeout': 5,
                    'application_name': 'decision-service', 'prepare_threshold': None},
        )
        try:
            self.pool.open(wait=True, timeout=10)
            if migrate:
                self.migrate()
            else:
                self.verify_schema()
        except Exception:
            self.pool.close()
            raise

    @contextmanager
    def connect(self):
        with self.pool.connection() as connection:
            yield _Connection(connection)

    def close(self):
        self.pool.close()

    def _write(self, db, *, admission=False):
        if admission:
            # Serialize admission/count checks, never model execution or claims.
            db.execute('SELECT pg_advisory_xact_lock(74623091)')

    def _now(self, db):
        # Shared database clock keeps leases consistent across machines.
        return db.execute('SELECT EXTRACT(EPOCH FROM clock_timestamp())::double precision AS now').fetchone()['now']

    def migrate(self):
        from psycopg import sql
        with self.pool.connection() as connection:
            connection.execute('SELECT pg_advisory_xact_lock(74623090)')
            connection.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(self.schema)))
            connection.execute('CREATE TABLE IF NOT EXISTS decision_schema_migrations (version TEXT PRIMARY KEY, checksum TEXT NOT NULL)')
            for path in sorted((Path(__file__).parent / 'migrations').glob('*.sql')):
                source = path.read_text()
                checksum = hashlib.sha256(source.encode()).hexdigest()
                previous = connection.execute('SELECT checksum FROM decision_schema_migrations WHERE version=%s', (path.name,)).fetchone()
                if previous:
                    if previous['checksum'] != checksum:
                        raise ValueError('Decision migration checksum changed')
                    continue
                connection.execute(source)
                connection.execute('INSERT INTO decision_schema_migrations VALUES (%s,%s)', (path.name, checksum))

    def verify_schema(self):
        with self.connect() as db:
            installed = {row['version']: row['checksum'] for row in db.execute('SELECT * FROM decision_schema_migrations')}
        for path in sorted((Path(__file__).parent / 'migrations').glob('*.sql')):
            if installed.get(path.name) != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError('Decision schema requires migration or has a changed checksum')

    def import_sqlite(self, path):
        """Copy a stopped legacy deployment atomically; never alter the source.

        Completed artifacts and cache entries keep their IDs/keys. Pending work
        is explicitly failed: this release uses a different implementation hash.
        Resubmit its original API request to create a job for the new workers.
        """
        source = Path(path).resolve()
        with self.connect() as db:
            self._write(db, admission=True)
            prior = db.execute("SELECT summary FROM import_markers WHERE source='legacy-sqlite-v1'").fetchone()
            if prior:
                return {'already_imported': True, **json.loads(prior['summary'])}
            if not source.is_file():
                return {'source_missing': True}
            with legacy_snapshot(source) as snapshot, closing(sqlite3.connect(snapshot.as_uri() + '?mode=ro', uri=True)) as legacy:
                legacy.row_factory = sqlite3.Row
                legacy.execute('BEGIN')
                tables = {row['name'] for row in legacy.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'runs' not in tables:
                    raise ValueError('Legacy database has no artifact table')
                summary = {}
                for table, key in (('runs', 'id'), ('jobs', 'id'), ('semantic_cache', 'key')):
                    if table not in tables:
                        continue
                    count = 0
                    for raw in legacy.execute('SELECT * FROM ' + table):
                        row = dict(raw)
                        if table == 'jobs':
                            row.setdefault('started_at', None)
                            if row['state'] in {'queued', 'running'}:
                                row.update(state='failed', error_code='EXECUTION_VERSION_CHANGED', lease_token=None,
                                           lease_until=None, completed_at=self._now(db))
                        columns = list(row)
                        placeholders = ','.join('?' for _ in columns)
                        # Identifiers are fixed by the known legacy schema below.
                        allowed = {
                            'runs': {'id','fingerprint','payload'},
                            'semantic_cache': {'key','payload'},
                            'jobs': {'id','fingerprint','inputs','specification','state','attempts','available_at',
                                     'lease_until','lease_token','error_code','created_at','completed_at','started_at'},
                        }
                        if not set(columns) <= allowed[table]:
                            raise ValueError('Unknown legacy columns')
                        inserted = db.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders}) ON CONFLICT DO NOTHING", tuple(row.values())).rowcount
                        if not inserted:
                            existing = db.execute(f'SELECT * FROM {table} WHERE {key}=?', (row[key],)).fetchone()
                            if existing is None or any(existing[name] != value for name, value in row.items()):
                                raise ValueError('Legacy import conflicts with existing Decision data')
                        count += 1
                    summary[table] = count
                db.execute("INSERT INTO import_markers VALUES ('legacy-sqlite-v1', ?)", (canonical(summary),))
                return summary
