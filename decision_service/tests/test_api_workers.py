import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from types import SimpleNamespace

from decision_service.service.http_api import DecisionServer
from decision_service.service.jobs import JobQueue, JobWorkers
from decision_service.service.store import RunStore
from decision_service.tests.test_service_integration import snapshots


class SeparateWorkerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = RunStore(str(Path(self.directory.name) / 'runs.sqlite'))
        self.queue = JobQueue(self.store)
        self.server = DecisionServer(('127.0.0.1',0),token='fixture-token',store=self.store,
                                     planning_url='',participation_url='',jobs=self.queue)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()

    def call(self,path,body=None):
        request = Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,
                          headers={'x-internal-token':'fixture-token','content-type':'application/json'})
        try:
            response = urlopen(request,timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.code,json.load(response)

    def test_api_accepts_without_executing_then_independent_worker_completes(self):
        plan, responses = snapshots()
        responses['response_revision'] = 1
        responses['participants'] = responses['participants'][:1]
        self.assertEqual(self.call('/health/ready')[0],503)
        status,run = self.call('/internal/previews',{'planning':plan,'responses':responses})
        self.assertEqual(status,202)
        self.assertEqual(self.store.get(run['run_id'])['job_state'],'queued')
        workers = JobWorkers(self.store,workers=1)
        workers.start()
        try:
            until = time.monotonic()+5
            while self.store.get(run['run_id'])['status']=='pending' and time.monotonic()<until:
                time.sleep(.01)
            self.assertEqual(self.store.get(run['run_id'])['status'],'ready')
            self.assertEqual(self.call('/health/ready')[0],200)
            metrics = self.call('/internal/metrics')[1]
            self.assertEqual(metrics['worker_processes'],1)
            self.assertNotIn('participants',json.dumps(metrics))
        finally:
            workers.close()
        self.assertEqual(self.call('/health/ready')[0],503)

    def test_readiness_returns_503_when_database_unavailable(self):
        with patch.object(self.store,'health',side_effect=RuntimeError('private connection details')):
            status,body = self.call('/health/ready')
        self.assertEqual(status,503)
        self.assertNotIn('private',json.dumps(body))

    def test_preview_pool_does_not_claim_recommendations(self):
        plan, responses = snapshots()
        queued = self.queue.enqueue(plan,responses)
        workers = JobWorkers(self.store,workers=1,kinds=['preview'])
        workers.start()
        try:
            self.assertTrue(self.store.supports([self.queue.specifications['preview']]))
            self.assertFalse(self.store.supports([self.queue.specifications['recommendation']]))
            self.assertEqual(self.store.get(queued['run_id'])['job_state'],'queued')
        finally:
            workers.close()

    def test_api_fact_identity_matches_key_owning_worker_without_api_credentials(self):
        class FixtureCollector:
            model = 'fixture-model'
            def collect(self, inputs):
                return {'claims':[{'fixture':True}],'issues':[]}
        identity = SimpleNamespace(provider_name='FixtureCollector',model='fixture-model')
        self.server.jobs = JobQueue(self.store,fact_collector=identity)
        workers = JobWorkers(self.store,workers=1,fact_collector=FixtureCollector(),kinds=['fact_collection'])
        workers.start()
        try:
            plan,_ = snapshots()
            plan['options'][0]['identity'] = {'model_id':'fixture-device'}
            status,run = self.call('/internal/facts/collections',{'planning':plan,'requests':[
                {'option_id':plan['options'][0]['option_id'],'attribute_id':'mass','value_type':'number','unit':'kg'}]})
            self.assertIn(status,(200,202))
            until = time.monotonic()+5
            while self.store.get(run['run_id'])['status']=='pending' and time.monotonic()<until:
                time.sleep(.01)
            self.assertEqual(self.store.get(run['run_id'])['status'],'needs_review')
        finally:
            workers.close()

    def test_worker_http_surface_cannot_admit_jobs(self):
        self.server.worker_health = True
        self.assertEqual(self.call('/internal/planning/validate',{})[0],404)
        self.assertEqual(self.store.health(),{})
