"""HTTP/process scaling and SIGKILL recovery against isolated PostgreSQL schemas.

No real users, existing run data or model APIs are used. Optional delay simulates
blocking provider I/O; reported timings are never presented as Gemini latency.
Run from FSD: python -m integration.benchmark_decision_service --jobs 48
Set DECISION_TEST_DATABASE_URL to a disposable/test-capable PostgreSQL database.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from decision_service.service.postgres_store import PostgresRunStore
from decision_service.service.jobs import JobWorkers
from decision_service.tests.test_service_integration import snapshots

MODULE = 'integration.benchmark_decision_service'
TOKEN = 'isolated-benchmark-internal-token'


def wait_for(function, timeout=30):
    until = time.monotonic() + timeout
    while True:
        value = function()
        if value:
            return value
        if time.monotonic() > until:
            raise RuntimeError('Benchmark condition timed out')
        time.sleep(.02)


def worker(delay_ms):
    from decision_service.service import jobs
    from decision_service.service.store import open_store
    # This delay exists only in the harness. Production has no artificial delay.
    original = jobs.preview
    def delayed(*args, **kwargs):
        time.sleep(delay_ms / 1000)
        return original(*args, **kwargs)
    jobs.preview = delayed
    original_execute = jobs.execute
    def delayed_execute(*args, **kwargs):
        time.sleep(delay_ms / 1000)
        return original_execute(*args, **kwargs)
    jobs.execute = delayed_execute
    store = open_store(migrate=False)
    workers = JobWorkers(store, workers=1, lease_seconds=5)
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    workers.start()
    try:
        stopped.wait()
    finally:
        workers.close()
        store.close()


class Scenario:
    def __init__(self, url, count, delay_ms):
        self.schema = 'decision_bench_' + uuid4().hex
        self.store = PostgresRunStore(url, schema=self.schema)
        self.processes = []
        self.snapshots = {}
        self.rounds = {}
        outer = self
        class SnapshotHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                body = outer.snapshots.get(self.path)
                if self.headers.get('x-internal-token') != TOKEN or body is None:
                    self.send_error(404)
                    return
                encoded = json.dumps(body).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
        self.snapshot_server = ThreadingHTTPServer(('127.0.0.1', 0), SnapshotHandler)
        self.snapshot_thread = threading.Thread(target=self.snapshot_server.serve_forever, daemon=True)
        self.snapshot_thread.start()
        fixture_url = f'http://127.0.0.1:{self.snapshot_server.server_port}'
        with socket.socket() as available:
            available.bind(('127.0.0.1', 0))
            port = available.getsockname()[1]
        self.base = f'http://127.0.0.1:{port}'
        self.env = {**os.environ, 'DECISION_DATABASE_URL': url, 'DECISION_DB_SCHEMA': self.schema,
                    'INTERNAL_API_TOKEN': TOKEN, 'SEMANTIC_PROVIDER': 'rules', 'GEMINI_API_KEY': '',
                    'PLANNING_BASE_URL': fixture_url, 'PARTICIPATION_BASE_URL': fixture_url,
                    'PORT': str(port), 'DECISION_LEASE_SECONDS': '5', 'DECISION_JOB_TIMEOUT_SECONDS': '180'}
        def healthy():
            try:
                return self.call('GET', '/health/ready')
            except (URLError, HTTPError):
                return None
        try:
            self.launch([sys.executable, '-m', 'decision_service.service', '--role', 'api'])
            for _ in range(count):
                self.launch_worker(delay_ms)
            wait_for(healthy)
            wait_for(lambda: len(self.store.active_workers()) == count)
        except BaseException:
            self.close()
            raise

    def launch(self, command):
        process = subprocess.Popen(command, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.processes.append(process)
        return process

    def launch_worker(self, delay_ms):
        return self.launch([sys.executable, '-m', MODULE, '--worker', '--delay-ms', str(delay_ms)])

    def call(self, method, path, body=None):
        request = Request(self.base+path, method=method,
                          data=json.dumps(body).encode() if body is not None else None,
                          headers={'content-type': 'application/json', 'x-internal-token': TOKEN})
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    def body(self, revision):
        plan, response = snapshots()
        member = response['participants'][0]
        plan['roster'] = [member['participant_id']]
        response['participants'] = [member]
        response['constraints'] = [row for row in response.get('constraints', []) if row['participant_id'] == member['participant_id']]
        response.update(response_revision=revision, snapshot_id=f'benchmark-{revision}')
        return {'planning': plan, 'responses': response}

    def recommend(self, revision):
        round_id = self.rounds.setdefault(revision, str(uuid4()))
        plan, response = snapshots()
        plan['round_id'] = response['round_id'] = round_id
        response['snapshot_id'] = f'benchmark-{revision}'
        self.snapshots[f'/internal/rounds/{round_id}/option-snapshot'] = plan
        self.snapshots[f'/internal/rounds/{round_id}/response-snapshot'] = response
        return self.call('POST', f'/internal/rounds/{round_id}/recommendations', {})

    def complete(self, run_id, expected='ranked'):
        def result():
            run = self.call('GET', '/internal/runs/' + run_id)
            return run if run['status'] != 'pending' else None
        run = wait_for(result)
        if run['status'] != expected:
            raise RuntimeError('Synthetic job did not produce its expected domain result')
        return run

    def close(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
        for process in self.processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self.snapshot_server.shutdown()
        self.snapshot_server.server_close()
        self.snapshot_thread.join(timeout=2)
        from psycopg import sql
        with self.store.pool.connection() as db:
            db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.store.close()


def percentile(values, fraction):
    values = sorted(values)
    return round(values[min(len(values)-1, int((len(values)-1)*fraction))], 3)


def load(url, processes, jobs, delay_ms):
    scenario = Scenario(url, processes, delay_ms)
    try:
        def journey(revision):
            started = time.monotonic()
            admitted = scenario.recommend(revision)
            admission = time.monotonic()-started
            scenario.complete(admitted['run_id'])
            return admission, time.monotonic()-started
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=16) as clients:
            timings = list(clients.map(journey, range(jobs)))
        elapsed = time.monotonic()-started
        # A simultaneous duplicate burst must resolve to exactly one artifact.
        with ThreadPoolExecutor(max_workers=16) as clients:
            runs = list(clients.map(lambda _: scenario.recommend(1000), range(32)))
        ids = {run['run_id'] for run in runs}
        if len(ids) != 1:
            raise RuntimeError('Duplicate input generated multiple jobs')
        scenario.complete(next(iter(ids)))
        metrics = scenario.call('GET', '/internal/metrics')
        return {'worker_processes': processes, 'slots_per_process': 1, 'jobs': jobs,
                'concurrent_clients': 16, 'simulated_io_ms': delay_ms,
                'elapsed_seconds': round(elapsed,3), 'jobs_per_second': round(jobs/elapsed,3),
                'admission_seconds_p95': percentile([row[0] for row in timings],.95),
                'end_to_end_seconds_p95': percentile([row[1] for row in timings],.95),
                'duplicate_requests': 32, 'duplicate_run_ids': len(ids), 'errors': 0,
                'metrics': metrics}
    finally:
        scenario.close()


def recovery(url):
    scenario = Scenario(url, 1, 2000)
    try:
        run = scenario.call('POST', '/internal/previews', scenario.body(2000))
        def claimed():
            with scenario.store.connect() as db:
                row = db.execute('SELECT * FROM jobs WHERE id=?', (run['run_id'],)).fetchone()
            return dict(row) if row['state'] == 'running' else None
        original = wait_for(claimed)
        started = time.monotonic()
        victim = scenario.processes[1]
        victim.kill()  # Deliberately bypass graceful release and test lease recovery.
        victim.wait(timeout=5)
        scenario.launch_worker(0)
        scenario.complete(run['run_id'], expected='ready')
        with scenario.store.connect() as db:
            row = db.execute('SELECT attempts FROM jobs WHERE id=?', (run['run_id'],)).fetchone()
        fenced = not scenario.store.complete(original, {'status':'ready'})
        if row['attempts'] != 2 or not fenced:
            raise RuntimeError('Crash recovery or stale completion fencing failed')
        return {'signal':'SIGKILL', 'lease_seconds':5, 'recovery_seconds':round(time.monotonic()-started,3),
                'attempts': row['attempts'], 'same_run_id': True, 'stale_completion_rejected': fenced}
    finally:
        scenario.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=int, default=48)
    parser.add_argument('--delay-ms', type=int, default=100)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--output', help='Optional JSON evidence file')
    args = parser.parse_args()
    if args.worker:
        return worker(args.delay_ms)
    if not 1 <= args.jobs <= 96 or not 0 <= args.delay_ms <= 2000:
        parser.error('Use 1-96 jobs and 0-2000 ms simulated I/O')
    url = os.environ.get('DECISION_TEST_DATABASE_URL')
    if not url:
        parser.error('Set DECISION_TEST_DATABASE_URL to a test-capable PostgreSQL database')
    report = {'workload':'Synthetic fixture recommendations over HTTP with stub snapshot services and real preprocessing/ranking; optional simulated provider wait; preview crash recovery; no external model calls',
              'load': [load(url, count, args.jobs, args.delay_ms) for count in (1,2)],
              'recovery': recovery(url)}
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
