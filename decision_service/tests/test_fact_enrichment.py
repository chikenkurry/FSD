from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from decision_service.preprocessing import preprocess
from decision_service.service.enrichment import FactEnricher, replay_facts
from decision_service.service.fact_collection import CollectionUnavailable
from decision_service.service.snapshots import map_snapshots
from decision_service.service.store import RunStore
from decision_service.service.workflow import execute, preview
from decision_service.service.views import public_result
from decision_service.tests.test_fact_semantic_flow import snapshots


class Collector:
    def __init__(self):
        self.calls = []
        self.transform = lambda rows: rows

    def collect(self, inputs):
        self.calls.append(deepcopy(inputs))
        claims = [{**r, 'claim_id': r['option_id'] + ':' + r['attribute_id'], 'value':'Italian',
                   'qualifier':'exact', 'source_text':'The menu lists Italian cuisine.', 'valid_until':None,
                   'sources':[{'url':'https://example.com/menu'}]} for r in inputs['requests']]
        return {'claims': self.transform(claims), 'issues':[], 'retrieved_at':'2026-10-22T00:00:00Z'}


class EnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.plan, self.responses = snapshots()
        self.plan['questions'] = [{'question_id':'q','label':'Private question wording', 'role':'soft',
            'criterion':'cuisine','relevance':1,'required':True,'answer_format':'choice','choices':['Italian','French'],
            'mapping':{'value_type':'category','comparison_rule':'attribute_match_v1'}}]
        self.responses['participants'][0]['answers'][0]['value'] = 'Italian'
        for option in self.plan['options']:
            option['identity'] = {'model_id':option['title'], 'region':'Singapore'}
            option['facts'] = [f for f in option['facts'] if f['criterion'] != 'cuisine']
        self.collector = Collector()

    def test_supplements_facts_before_scoring_without_mutating_published_inputs_and_replays_offline(self):
        original = deepcopy(self.plan)
        run = execute(self.plan,self.responses,fact_enricher=FactEnricher(self.collector))
        self.assertEqual(run['status'],'ranked',run.get('issues'))
        self.assertEqual(self.plan,original)
        self.assertEqual(len(run['fact_enrichment']['applied_facts']),4)
        inputs = self.collector.calls[0]
        self.assertEqual(set(inputs),{'options','requests','currency','cost_scope'})
        self.assertNotIn('Private question wording',json.dumps(inputs))
        self.assertNotIn('French',json.dumps(inputs))
        self.assertNotIn('participant',json.dumps(inputs))
        enriched = replay_facts(self.plan,run['fact_enrichment'])
        self.assertTrue(all(f['fact']['context']['reviewed'] is False for f in run['fact_enrichment']['applied_facts']))
        mapped,replies = map_snapshots(enriched,self.responses)
        self.assertEqual(preprocess(mapped,replies),run['processing'])
        replayed=execute(enriched,self.responses)['result']
        self.assertEqual({k:v for k,v in replayed.items() if k!='run_id'},
                         {k:v for k,v in run['result'].items() if k!='run_id'})
        run['run_id']='synthetic-run'
        run['fact_enrichment']['collections'][0]['private_internal_marker']='INTERNAL-ONLY'
        public=public_result(run)
        self.assertEqual(len(public['supplemented_facts']),4)
        self.assertNotIn('INTERNAL-ONLY',json.dumps(public))
        self.assertEqual(public['supplemented_facts'][0]['sources'],[{'url':'https://example.com/menu'}])

    def test_ambiguous_conditional_and_expired_claims_never_become_usable_facts(self):
        def conflicting(rows):
            other=deepcopy(rows[0]);other['value']='French'
            return rows + [other]
        for transform in (conflicting, lambda rows:[{**r,'qualifier':'conditions'} for r in rows],
                          lambda rows:[{**r,'valid_until':'2000-01-01T00:00:00Z'} for r in rows]):
            self.collector.transform=transform
            run=execute(self.plan,self.responses,fact_enricher=FactEnricher(self.collector))
            self.assertEqual(run['status'],'needs_information')
            self.assertTrue(run['processing']['preparation']['fact_requests'])

    def test_organiser_corrections_are_preserved_and_complete_snapshots_do_not_search(self):
        for option in self.plan['options']:
            option['facts'].append({'criterion':'cuisine','value':'French','value_type':'category',
                                    'source':'Organiser checked menu','status':'confirmed','context':{'reviewed':True}})
        run=execute(self.plan,self.responses,fact_enricher=FactEnricher(self.collector))
        self.assertEqual(run['status'],'ranked')
        self.assertEqual(self.collector.calls,[])
        self.assertEqual(run['fact_enrichment']['applied_facts'],[])

    def test_expired_and_stale_old_values_stay_unknown_when_refresh_fails(self):
        for context in ({'valid_until':'2000-01-01T00:00:00Z'}, {'stale':True}):
            plan=deepcopy(self.plan)
            plan['options'][0]['facts'].append({'criterion':'cuisine','value':'Italian','value_type':'category',
                                               'source':'old menu','status':'confirmed','context':context})
            with patch.object(self.collector,'collect',side_effect=CollectionUnavailable('GEMINI_SEARCH_HTTP_429')):
                run=execute(plan,self.responses,fact_enricher=FactEnricher(self.collector))
            self.assertEqual(run['status'],'needs_information')
            self.assertEqual(run['fact_enrichment']['issues'],[{'code':'GEMINI_SEARCH_HTTP_429'}])
            fact=next(f for f in run['processing']['preparation']['candidates'][0]['facts'] if f['attribute_id']=='cuisine')
            self.assertEqual((fact['status'],fact['value']),('unknown',None))
            replayed=execute(replay_facts(plan,run['fact_enrichment']),self.responses)
            self.assertEqual(replayed['processing'],run['processing'])

    def test_missing_identity_does_not_prevent_other_options_being_researched(self):
        del self.plan['options'][0]['identity']
        run=execute(self.plan,self.responses,fact_enricher=FactEnricher(self.collector))
        self.assertEqual(run['status'],'needs_information')
        self.assertEqual(len(run['fact_enrichment']['applied_facts']),3)
        self.assertEqual(run['fact_enrichment']['issues'][0]['code'],'FACT_IDENTITY_OR_TYPE_REQUIRED')

    def test_expired_cost_is_not_used_even_when_only_needed_for_tie_breaking(self):
        for option in self.plan['options']:
            option['facts'].append({'criterion':'cuisine','value':'Italian','value_type':'category',
                                    'source':'menu','status':'confirmed'})
        cost=next(f for f in self.plan['options'][0]['facts'] if f['criterion']=='max_cost')
        cost['context']['valid_until']='2000-01-01T00:00:00Z'
        run=execute(self.plan,self.responses,fact_enricher=FactEnricher(self.collector))
        self.assertEqual(run['status'],'ranked')
        candidate=next(c for c in run['algorithm_input']['candidates'] if c['candidate_id']=='a')
        self.assertIsNone(candidate['estimated_cost_minor'])
        self.assertEqual(self.collector.calls,[])
        self.assertEqual(len(run['fact_enrichment']['invalidated_facts']),1)

    def test_previews_and_final_runs_share_versioned_public_research_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            store=RunStore(str(Path(directory)/'runs.sqlite'))
            enricher=FactEnricher(self.collector,store)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda _:enricher.enrich(self.plan,self.responses),range(4)))
            draft={**deepcopy(self.responses),'response_revision':3}
            self.assertEqual(preview(self.plan,draft,fact_enricher=enricher)['status'],'ready')
            self.assertEqual(execute(self.plan,self.responses,fact_enricher=enricher)['status'],'ranked')
            self.assertEqual(len(self.collector.calls),1)
            with patch.dict('os.environ',{'GEMINI_FACT_MODEL_REVISION':'changed'}):
                enricher.enrich(self.plan,self.responses)
            self.assertEqual(len(self.collector.calls),2)
            plan=deepcopy(self.plan);plan['options'][0]['identity']['region']='Elsewhere'
            enricher.enrich(plan,self.responses)
            self.assertEqual(len(self.collector.calls),3)

    def test_legacy_rounds_keep_their_original_policy_and_missing_provider_is_explicit(self):
        plan=deepcopy(self.plan);plan.pop('interpretation_policy')
        run=execute(plan,self.responses,fact_enricher=FactEnricher(self.collector))
        self.assertEqual(run['status'],'needs_information')
        self.assertEqual(self.collector.calls,[])
        run=execute(self.plan,self.responses,fact_enricher=FactEnricher())
        self.assertEqual(run['status'],'needs_information')
        self.assertEqual(run['fact_enrichment']['issues'],[{'code':'FACT_COLLECTOR_NOT_CONFIGURED'}])


if __name__ == '__main__': unittest.main()
