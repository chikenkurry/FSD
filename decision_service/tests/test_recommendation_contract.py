"""Regressions for the public boundary and end-to-end ranking metadata."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from decision_service.adapters import adapt_generic_to_option_v1
from decision_service.algorithm import run_decision as run_scheduled
from decision_service.contract import ranking_order
from decision_service.generic_algorithm import run_decision
from decision_service.service.views import public_result, recommendation_view
from decision_service.service.workflow import execute
from decision_service.service.execution import execute_preparation
from decision_service.tests.test_algorithm import algorithm_input
from decision_service.tests.test_generic_option_v1 import preparation
from decision_service.tests.test_service_integration import snapshots


def tied_snapshots():
    plan, responses = snapshots()
    plan['options'][0]['facts'][0]['value'] = '1400'
    plan['options'][1]['facts'][0]['value'] = '1200'
    responses['participants'][0]['answers'][1]['value'] = '13.5 hours'
    responses['participants'][0]['answers'][2]['value'] = ['Coding']
    return plan, responses


class RecommendationContractTests(unittest.TestCase):
    def test_connected_cost_tie_uses_facts_and_declared_precision(self):
        for digits in (0, 2, 3):
            with self.subTest(digits=digits):
                plan, responses = tied_snapshots()
                plan['currency_minor_digits'] = responses['minor_digits'] = digits
                run = execute(plan, responses)
                self.assertEqual(run['status'], 'ranked')
                self.assertEqual(run['result']['ranked_candidates'][0]['option_id'], 'device-b')
                self.assertEqual([c['estimated_cost_minor'] for c in run['algorithm_input']['candidates']],
                                 [1400 * 10 ** digits, 1200 * 10 ** digits])
                view = recommendation_view(run)
                self.assertEqual(view['recommendation']['estimated_cost_minor'], 1200 * 10 ** digits)
                self.assertEqual(view['recommendation']['currency_minor_digits'], digits)
                self.assertEqual(view['recommendation']['primary_objective_tie_size'], 2)

    def test_cost_conversion_never_rounds(self):
        plan, responses = tied_snapshots()
        plan['options'][0]['facts'][0]['value'] = '1400.001'
        run = execute(plan, responses)
        self.assertEqual(run['status'], 'invalid_input')
        self.assertEqual(run['issues'][0]['code'], 'INVALID_OPTION_COST')

    def test_unconfirmed_or_missing_cost_is_not_treated_as_free(self):
        for state in ('estimated', 'unknown', 'missing'):
            with self.subTest(state=state):
                plan, responses = tied_snapshots()
                plan['questions'] = plan['questions'][1:]
                responses['participants'][0]['answers'] = responses['participants'][0]['answers'][1:]
                if state == 'missing':
                    plan['options'][0]['facts'].pop(0)
                else:
                    plan['options'][0]['facts'][0]['status'] = state
                    if state == 'unknown':
                        plan['options'][0]['facts'][0]['value'] = None
                        plan['options'][0]['facts'][0]['value_type'] = 'decimal'
                run = execute(plan, responses)
                self.assertEqual(run['status'], 'ranked', run.get('issues'))
                self.assertIsNone(run['algorithm_input']['candidates'][0]['estimated_cost_minor'])
                self.assertEqual(run['result']['ranked_candidates'][0]['option_id'], 'device-b')

    def test_scenarios_use_confirmed_costs_and_expose_date_windows(self):
        packet = preparation()
        packet['context'].update(currency='SGD', cost_scope='per_person_total')
        packet['criteria'] += [
            {'attribute_id': 'duration_days', 'value_type': 'number', 'unit': 'days'},
            {'attribute_id': 'max_cost', 'value_type': 'decimal', 'unit': 'SGD'},
        ]
        packet['scenario_requests'] = [
            {'option_id': option, 'duration_days': 3, 'earliest_start_date': '2027-06-01', 'latest_start_date': '2027-06-03',
             'cost_evidence_status': 'confirmed', 'cost_evidence': {'amount': cost, 'status': 'confirmed'}}
            for option, cost in (('a', '100'), ('b', '90'))
        ]
        run = execute_preparation(packet, {'execution_mode': 'scenarios', 'currency': 'SGD',
                                         'currency_minor_digits': 2, 'cost_scope': 'per_person_total'},
                                  {'constraints': [], 'snapshot_id': 'review'})
        self.assertEqual(run['status'], 'ranked', run.get('issues'))
        candidate = recommendation_view(run)['recommendation']
        self.assertEqual(candidate['source_option_id'], 'b')
        self.assertEqual(candidate['estimated_cost_minor'], 9000)
        self.assertEqual(candidate['scenario'], {'duration_days': 3, 'earliest_start_date': '2027-06-01', 'latest_start_date': '2027-06-03'})

    def test_mixed_offsets_and_equivalent_instants_use_actual_time(self):
        for first, second, winner in (
            ('2027-01-02T09:00:00+08:00', '2027-01-02T02:00:00Z', 'a'),
            ('2027-01-02T09:00:00+08:00', '2027-01-02T01:00:00Z', 'a'),
            (None, '2027-01-02T01:00:00Z', 'b'),
        ):
            with self.subTest(first=first, second=second):
                source = preparation()
                source['candidates'][0]['start_at'] = first
                source['candidates'][1]['start_at'] = second
                handoff = adapt_generic_to_option_v1(source)['algorithm_input']
                result = run_decision(handoff)
                self.assertEqual(result.ranked_candidates[0]['option_id'], winner)
                self.assertEqual(result.ranked_candidates[0]['primary_objective_tie_size'], 2)

    def test_scheduled_matcher_and_historical_view_share_tie_semantics(self):
        for mode in ('maximin_then_average', 'weighted_fairness'):
            with self.subTest(mode=mode):
                data = algorithm_input()
                data['preferences'][1]['rating'] = 4
                objective = data['scoring_model']['group_objective']
                objective['mode'] = mode
                data['scoring_model']['ranking_policy']['sort_order'] = ranking_order(objective)
                result = run_scheduled(data).as_dict()
                self.assertEqual(result['ranked_candidates'][0]['candidate_id'], 'b')
                self.assertEqual([(r['primary_rank'], r['primary_objective_tie_size'])
                                  for r in result['ranked_candidates']], [(1, 2), (1, 2)])
                for historical in (False, True):
                    artifact = deepcopy(result)
                    if historical:
                        for row in artifact['ranked_candidates']:
                            row.pop('primary_rank')
                            row.pop('primary_objective_tie_size')
                    run = {'status': 'ranked', 'result': artifact, 'algorithm_input': data}
                    before = deepcopy(run)
                    view = recommendation_view(run)
                    self.assertEqual(view['recommendation']['primary_objective_tie_size'], 2)
                    self.assertEqual(view['alternatives'][0]['primary_rank'], 1)
                    self.assertEqual(run, before)

    def test_entire_public_response_excludes_diagnostics_and_keeps_private_artifact(self):
        plan, responses = tied_snapshots()
        responses['constraints'][0]['activity_flags'] = [{'activity_id': 'device-a', 'flag': 'cannot_join'}]
        run = dict(execute(plan, responses), run_id='review')
        run['result']['member_scores'] = {'p1': 'PRIVATE-SCORE'}
        run['result']['issues'] = ['PRIVATE-CONTRACT-ERROR']
        run['issues'].append({'code': 'PRIVATE-ANSWER-CODE', 'path': 'responses.participants.p1.answers.q'})
        before = deepcopy(run)
        public = public_result(run)
        wire = json.dumps(public)
        for private in ('CANNOT_JOIN', 'explanation_codes', 'PRIVATE-SCORE', 'PRIVATE-CONTRACT-ERROR', 'PRIVATE-ANSWER-CODE'):
            self.assertNotIn(private, wire)
        self.assertEqual(public['result']['candidate_results'][0]['feasibility'], 'infeasible')
        self.assertEqual(run, before)
        self.assertIn('CANNOT_JOIN', run['result']['candidate_results'][0]['explanation_codes'])

    def test_view_schema_validates_real_and_fixture_states_and_rejects_drift(self):
        root = Path(__file__).parents[2]
        schema = json.loads((root / 'contracts/api.schema.json').read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator({**schema, '$ref': '#/$defs/recommendation_view'})
        fixtures = json.loads((root / 'decision_service/fixtures/presentation/recommendation_view_cases.json').read_text())
        views = [recommendation_view(case['run']) for case in fixtures.values()]
        plan, responses = tied_snapshots()
        views.append(recommendation_view(execute(plan, responses)))
        data = algorithm_input()
        scheduled = run_scheduled(data).as_dict()
        views.append(recommendation_view({'status': 'ranked', 'result': scheduled, 'algorithm_input': data}))
        for view in views:
            validator.validate(view)
        run = dict(execute(plan, responses), run_id='review')
        Draft202012Validator({**schema, '$ref': '#/$defs/run'}).validate(public_result(run))
        bad = deepcopy(views[-1])
        bad['recommendation']['primary_objective_tie_size'] = 0
        self.assertFalse(validator.is_valid(bad))
        bad = deepcopy(views[-1])
        bad['recommendation']['member_scores'] = {'p1': .5}
        self.assertFalse(validator.is_valid(bad))
        bad = deepcopy(views[-1])
        bad['next_action'] = 'UNRECOGNIZED_ACTION'
        self.assertFalse(validator.is_valid(bad))
        self.assertFalse(validator.is_valid({k: v for k, v in views[-1].items() if k != 'alternatives'}))


if __name__ == '__main__':
    unittest.main()
