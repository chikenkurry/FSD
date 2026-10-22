"""Sourced attributes -> interpreted member meanings -> deterministic decisions."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from decision_service.preprocessing import preprocess
from decision_service.service.snapshots import map_snapshots
from decision_service.service.workflow import execute
from decision_service.preprocessing.semantics import OllamaSemanticProvider, OpenAISemanticProvider, SemanticServiceError


def snapshots():
    options = []
    for key, cost, atmosphere, cuisine in [('a','85','calm','Italian'),('b','105','lively','Italian'),('c','100','calm','Italian'),('d','90','lively','French')]:
        options.append({'option_id':key,'title':'Venue '+key,'facts':[
            {'criterion':'max_cost','value':cost,'value_type':'decimal','unit':'SGD','status':'confirmed','source':'menu','context':{'scope':'per_person_total'}},
            {'criterion':'atmosphere','value':atmosphere,'value_type':'category','status':'confirmed','source':'venue description'},
            {'criterion':'cuisine','value':cuisine,'value_type':'category','status':'confirmed','source':'menu'}]})
    plan={'schema_version':'planning-snapshot-v1','plan_id':'plan','round_id':'round','option_snapshot_id':'options','option_revision':1,
          'interpretation_policy':'facts-v1','decision_question':'Where should we eat?','currency':'SGD','currency_minor_digits':2,
          'cost_scope':'per_person_total','execution_mode':'options','roster':['member'],'options':options,
          'questions':[{'question_id':'q','label':'What matters to you?','answer_format':'text','required':True,
                        'role':'soft','criterion':'preferences','relevance':1}]}
    replies={'schema_version':'response-snapshot-v2','plan_id':'plan','round_id':'round','option_snapshot_id':'options','option_revision':1,
             'snapshot_id':'responses','currency':'SGD','minor_digits':2,'constraints':[{'participant_id':'member'}],'preferences':[],
             'participants':[{'participant_id':'member','response_status':'complete','answers':[{'question_id':'q',
                'value':'I must stay below SGD 100; I prefer somewhere peaceful and Italian.'}]}]}
    return plan,replies


class Provider:
    model='recorded-meaning-test'

    def __init__(self): self.extractions=0;self.assessments=[]

    def suggest_option_tags(self, *args):
        raise AssertionError('New-policy semantics must never invent missing option facts')

    def extract_sparse_answer(self, question, answer, context):
        self.extractions+=1
        return {'status':'resolved','interpretations':[
            {'criterion':'max_cost','value':'100 SGD','intent':'less_than','must_have':True,'polarity':'prefer','evidence':'I must stay below SGD 100'},
            {'criterion':'atmosphere','value':'peaceful','intent':'match','must_have':False,'polarity':'prefer','evidence':'I prefer somewhere peaceful'},
            {'criterion':'cuisine','value':'Italian','intent':'match','must_have':False,'polarity':'prefer','evidence':'Italian'}]}

    def canonicalize_sparse_label(self, payload):
        self.assessments.append(deepcopy(payload))
        if payload['label']=='peaceful': return {'status':'equivalent','target':'calm','reason':'Same atmosphere meaning'}
        raise AssertionError('Unexpected semantic call: '+payload['label'])


class FactSemanticFlowTests(unittest.TestCase):
    def test_provider_repairs_paraphrased_evidence_once_without_accepting_unsupported_spans(self):
        good={'status':'resolved','interpretations':[{'criterion':'cuisine','value':'Italian','intent':'match','must_have':False,
              'polarity':'prefer','evidence':'Italian'}],'importance_relations':[]}
        bad=deepcopy(good);bad['interpretations'][0]['evidence']='I prefer Italian'
        for provider in (OllamaSemanticProvider(),OpenAISemanticProvider(api_key='synthetic-test-key')):
            with self.subTest(provider=type(provider).__name__),patch.object(provider,'_request',side_effect=[bad,good]) as request:
                self.assertEqual(provider.extract_sparse_answer({},'I prefer quiet and Italian',{}),good)
                self.assertEqual(request.call_count,2)
                repair_args=request.call_args.args
                schema=repair_args[0] if isinstance(provider,OllamaSemanticProvider) else repair_args[1]
                spans=schema['properties']['interpretations']['items']['properties']['evidence']['enum']
                self.assertIn('Italian',spans)
                self.assertNotIn('I prefer Italian',spans)
                self.assertTrue(all(s in 'I prefer quiet and Italian' for s in spans))
            with self.subTest(provider=type(provider).__name__),patch.object(provider,'_request',return_value=bad) as request:
                with self.assertRaises(SemanticServiceError): provider.extract_sparse_answer({},'I prefer quiet and Italian',{})
                self.assertEqual(request.call_count,2)

    def test_compound_answer_requires_confirmation_then_algorithm_enforces_strict_budget(self):
        plan,replies=snapshots();original=deepcopy(plan['options']);provider=Provider()
        first=execute(plan,replies,semantic_provider=provider)
        self.assertEqual(first['status'],'needs_clarification',first.get('issues'))
        constraint=first['processing']['preparation']['constraints'][0]
        self.assertEqual((constraint['attribute_id'],constraint['constraint_rule'],constraint['required_value']),('max_cost','less_than_v1','100'))
        self.assertEqual(constraint['confirmation_status'],'needs_confirmation')
        replies['participants'][0]['answers'][0]['confirmed_requirements']=[{
            'attribute_id':'max_cost','constraint_rule':'less_than_v1','required_value':'100','unit':'SGD'}]
        replies['snapshot_id']='confirmed-responses'
        run=execute(plan,replies,semantic_provider=provider)
        self.assertEqual(run['status'],'ranked',run.get('issues'))
        self.assertEqual([c['option_id'] for c in run['result']['ranked_candidates']],['a','d'])
        self.assertEqual(plan['options'],original) # Interpreting members never writes option facts.
        packet=run['processing']['preparation']
        self.assertEqual({p['attribute_id'] for p in packet['preferences']},{'atmosphere','cuisine'})
        self.assertEqual([p['preferred_value'] for p in packet['preferences'] if p['attribute_id']=='atmosphere'],['calm'])
        # Frozen semantic evidence is sufficient to reproduce preparation offline.
        mapped,responses=map_snapshots(plan,replies)
        self.assertEqual(preprocess(mapped,responses,semantic_evidence=run['processing']['semantic_evidence']),run['processing'])

    def test_choices_are_interpreted_against_facts_instead_of_becoming_fact_labels(self):
        plan,replies=snapshots();provider=Provider()
        plan['questions']=[{'question_id':'q','label':'Preferred atmosphere?','role':'soft','criterion':'atmosphere',
                            'relevance':1,'required':True,'answer_format':'choice','choices':['Peaceful','Lively']}]
        replies['participants'][0]['answers'][0]['value']='Peaceful'
        run=execute(plan,replies,semantic_provider=provider)
        self.assertEqual(run['status'],'ranked',run.get('issues'))
        self.assertEqual(provider.extractions,0)
        self.assertEqual(provider.assessments[0]['targets'],['calm','lively'])
        self.assertEqual(run['processing']['preparation']['preferences'][0]['preferred_value'],'calm')
        self.assertEqual([c['option_id'] for c in run['result']['ranked_candidates']][:2],['a','c'])

    def test_known_typed_answers_need_no_model_and_missing_facts_block_ranking(self):
        plan,replies=snapshots()
        plan['questions']=[{'question_id':'q','label':'Cuisine preference?','role':'soft','criterion':'cuisine','relevance':1,
                            'required':True,'answer_format':'choice','choices':['Italian','French']}]
        replies['participants'][0]['answers'][0]['value']='Italian'
        provider=Provider()
        self.assertEqual(execute(plan,replies,semantic_provider=provider)['status'],'ranked')
        self.assertEqual((provider.extractions,provider.assessments),(0,[]))
        plan['options'][0]['facts']=[f for f in plan['options'][0]['facts'] if f['criterion']!='cuisine']
        run=execute(plan,replies,semantic_provider=provider)
        self.assertEqual(run['status'],'needs_information')
        self.assertEqual(run['processing']['preparation']['fact_requests'][0]['attribute_id'],'cuisine')

    def test_free_text_fails_explicitly_without_semantics_instead_of_becoming_context(self):
        plan,replies=snapshots()
        run=execute(plan,replies)
        self.assertNotEqual(run['status'],'ranked')
        self.assertIn('SEMANTIC_PROVIDER_REQUIRED',[i['code'] for i in run['issues']])


if __name__=='__main__': unittest.main()
