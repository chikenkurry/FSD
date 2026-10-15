"""Measure scoring, result-read payloads, readiness and idle SQL in isolation.

Set DECISION_TEST_DATABASE_URL for PostgreSQL; otherwise uses a temporary SQLite
database. PostgreSQL runs create/drop only a generated decision_eff_ schema.
Statement counts exclude driver BEGIN/COMMIT; byte counts measure JSON-encoded
materialised fields, not network protocol bytes. No external providers are used.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from uuid import uuid4

from decision_service.generic_algorithm import run_decision
from decision_service.preprocessing import preprocess
from decision_service.service.execution import adapt_preparation
from decision_service.service.jobs import JobWorkers
from decision_service.service.snapshots import map_snapshots
from decision_service.service.store import RunStore, canonical
from decision_service.tests.test_service_integration import snapshots
from decision_service.tests.sql_metrics import SQLCounter
from decision_service.service.workflow import execute
from integration.benchmark_backend import fixture


def median_ms(function, iterations=100):
    values = []
    for _ in range(iterations):
        started = time.perf_counter()
        function()
        values.append((time.perf_counter()-started)*1000)
    return round(statistics.median(values),4)


def compare_matchers(handoff, reference):
    functions = {'baseline':reference,'optimised':run_decision}
    outputs, timings = {}, {'baseline':[],'optimised':[]}
    for label, function in functions.items():
        outputs[label] = function(handoff).as_dict()
        outputs[label].pop('run_id')
    if outputs['baseline'] != outputs['optimised']:
        raise RuntimeError('Reference and optimised matcher results differ')
    for iteration in range(1000):
        order = ('baseline','optimised') if iteration % 2 else ('optimised','baseline')
        for label in order:
            started = time.perf_counter()
            functions[label](handoff)
            timings[label].append((time.perf_counter()-started)*1000)
    return {'iterations_per_variant':1000,'order':'alternating in same process',
            'baseline_ms':round(statistics.median(timings['baseline']),4),
            'optimised_ms':round(statistics.median(timings['optimised']),4),
            'identical_results':True}


def measure(store, idle_seconds, reference=None):
    scoring = []
    for members, options in ((2,2),(10,4),(30,8)):
        source, replies = fixture(members, options)
        plan, response = map_snapshots(source, replies)
        prepared = preprocess(plan, response)['preparation']
        handoff = adapt_preparation(prepared, plan, replies)['algorithm_input']
        result = run_decision(handoff).as_dict()
        if result['status'] != 'ranked':
            raise RuntimeError('Benchmark handoff did not rank')
        result.pop('run_id')
        scoring.append({'members':members,'options':options,
                        'matching_median_ms':median_ms(lambda:run_decision(handoff),200),
                        'result_sha256':hashlib.sha256(canonical(result).encode()).hexdigest()})
        if reference:
            scoring[-1]['paired_comparison'] = compare_matchers(handoff,reference)

    plan, replies = snapshots()
    artifact = execute(plan,replies)
    plan['benchmark_padding'] = 'x' * 524288
    completed = store.save(artifact,plan,replies)
    with SQLCounter(store) as counter:
        store.get(completed['run_id'])
    retrieval = {**counter.report(),'median_ms':median_ms(lambda:store.get(completed['run_id']))}

    with store.connect() as db:
        now = store._now(db)
        db.execute("""WITH RECURSIVE sequence(n) AS (
            SELECT 1 UNION ALL SELECT n+1 FROM sequence WHERE n<10000
        ) INSERT INTO jobs (id,fingerprint,inputs,specification,state,available_at,created_at,completed_at)
        SELECT 'history-' || CAST(n AS TEXT), 'history-' || CAST(n AS TEXT), '{}',
               '{}', 'failed', ?, ?, ? FROM sequence""", (now,now,now))
    probe = getattr(store,'ping',store.health)
    with SQLCounter(store) as counter:
        probe()
    readiness = {**counter.report(),'median_ms':median_ms(probe),'historical_jobs':10000}

    workers = JobWorkers(store,workers=1)
    with SQLCounter(store) as counter:
        workers.start()
        try:
            time.sleep(idle_seconds)
        finally:
            workers.close()
    return {'scoring':scoring,'completed_read_512k_input':retrieval,
            'readiness_database_probe':readiness,
            'idle_worker':{**counter.report(),'seconds':idle_seconds,'slots':1}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--idle-seconds',type=float,default=4)
    parser.add_argument('--label',default='current')
    parser.add_argument('--output')
    parser.add_argument('--reference-matcher',type=Path,help='Trusted matcher source exported from the baseline Git commit')
    args = parser.parse_args()
    if not 1 <= args.idle_seconds <= 30:
        parser.error('Use 1-30 idle seconds')
    url = os.environ.get('DECISION_TEST_DATABASE_URL')
    reference = None
    if args.reference_matcher:
        spec = importlib.util.spec_from_file_location('decision_reference_matcher',args.reference_matcher)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        reference = module.run_decision
    with tempfile.TemporaryDirectory() as directory:
        if url:
            from decision_service.service.postgres_store import PostgresRunStore
            store = PostgresRunStore(url,schema='decision_eff_'+uuid4().hex)
        else:
            store = RunStore(str(Path(directory)/'runs.sqlite'))
        try:
            report = {'label':args.label,'database':'postgresql' if url else 'sqlite',
                      'timing_iterations':100,'matching_iterations':200,
                      **measure(store,args.idle_seconds,reference)}
            if args.output:
                Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report,indent=2))
        finally:
            if url:
                from psycopg import sql
                with store.pool.connection() as db:
                    db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(store.schema)))
            store.close()


if __name__ == '__main__':
    main()
