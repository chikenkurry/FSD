from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from decision_service.service.snapshots import SnapshotError, map_snapshots, validate_planning_snapshot
from decision_service.service.store import RunStore
from decision_service.service.workflow import execute, public_result, member_review


def snapshots():
    root = Path(__file__).parents[1] / 'fixtures/preprocessing'
    planning = json.loads((root / 'planning_generic.json').read_text())
    replies = json.loads((root / 'response_generic.json').read_text())
    planning.update(schema_version='planning-snapshot-v1', plan_id='plan-1', option_revision=1, currency_minor_digits=2)
    responses = {"schema_version": "response-snapshot-v2", "plan_id": "plan-1", "round_id": planning['round_id'],
                 "option_revision": 1, "option_snapshot_id": planning['option_snapshot_id'],
                 "snapshot_id": replies['response_snapshot_id'], "currency": 'USD', 'minor_digits': 2,
                 "participants": replies['participants'], "constraints": [{'participant_id':'p1'}]}
    return planning, responses


class ServiceIntegrationTests(unittest.TestCase):
    def test_real_preprocessing_and_matcher_execute_frozen_question_answers(self):
        plan, replies = snapshots()
        validate_planning_snapshot(plan)
        run = execute(plan, replies)
        self.assertEqual(run['status'], 'ranked', run.get('issues'))
        self.assertEqual(run['result']['ranked_candidates'][0]['option_id'], 'device-a')

    def test_finite_float_facts_are_validated_without_crashing(self):
        plan, replies = snapshots()
        plan['options'][0]['facts'][1]['value'] = 12.5
        self.assertEqual(execute(plan, replies)['status'], 'ranked')
        plan['options'][0]['facts'][1]['value'] = float('nan')
        self.assertEqual(execute(plan, replies)['status'], 'invalid_input')

    def test_refuse_cross_round_revision_and_roster_mismatches(self):
        for key, value in [('round_id', 'other'), ('option_revision', 2), ('option_snapshot_id', 'other')]:
            plan, replies = snapshots()
            replies[key] = value
            with self.assertRaises(SnapshotError):
                map_snapshots(plan, replies)
        plan, replies = snapshots()
        replies['participants'].append(deepcopy(replies['participants'][0]))
        with self.assertRaises(SnapshotError):
            map_snapshots(plan, replies)

    def test_snapshot_boundary_rejects_invalid_metadata_and_flags(self):
        for field, value in [('currency', ''), ('currency_minor_digits', True),
                             ('option_revision', True), ('roster', ['p1', 'p1']), ('questions', [])]:
            plan, replies = snapshots()
            plan[field] = value
            with self.subTest(field=field), self.assertRaises(SnapshotError):
                validate_planning_snapshot(plan)
        plan, replies = snapshots()
        replies['constraints'][0]['activity_flags'] = [{'activity_id':'unknown','flag':'cannot_join'}]
        with self.assertRaises(SnapshotError):
            map_snapshots(plan, replies)

    def test_member_flags_and_incomplete_responses_are_enforced(self):
        plan, replies = snapshots()
        replies['constraints'] = [{'participant_id':'p1', 'activity_flags':[{'activity_id':'device-a','flag':'cannot_join'}]}]
        run = execute(plan, replies)
        self.assertEqual(run['result']['ranked_candidates'][0]['option_id'], 'device-b')
        replies['constraints'][0]['activity_flags'][0]['flag'] = 'needs_information'
        self.assertEqual(execute(plan, replies)['status'], 'blocked')
        replies['participants'][0]['response_status'] = 'incomplete'
        self.assertEqual(execute(plan, replies)['status'], 'blocked')

    def test_legacy_activity_ratings_are_not_silently_discarded(self):
        plan, replies = snapshots()
        replies['preferences'] = [{'participant_id':'p1','activity_id':'device-a','rating':4}]
        run = execute(plan, replies)
        self.assertEqual(run['status'], 'unsupported')
        self.assertEqual(run['issues'][0]['code'], 'ACTIVITY_RATINGS_NOT_SUPPORTED')

    def test_run_persistence_reuses_identical_artifacts_and_public_output_excludes_answers(self):
        plan, replies = snapshots()
        with tempfile.TemporaryDirectory() as root:
            store = RunStore(root+'/runs.sqlite')
            a = store.save(execute(plan,replies),plan,replies)
            b = store.save(execute(plan,replies),plan,replies)
            self.assertEqual(a['run_id'], b['run_id'])
            self.assertEqual(store.get(a['run_id'])['input_refs'], a['input_refs'])
            public = public_result(a)
            self.assertNotIn('processing', public)
            self.assertNotIn('participants', json.dumps(public))
            view = public['recommendation_view']
            self.assertEqual(view['schema_version'], 'recommendation-view-v1')
            self.assertEqual(view['status'], 'ranked')
            self.assertEqual(view['recommendation']['candidate_id'], 'device-a')
            self.assertTrue(view['recommendation']['is_recommended'])
            self.assertNotIn('explanation_codes', json.dumps(view))

    def test_shared_recommendation_view_hides_member_specific_failure_reasons(self):
        run = {
            'run_id': 'run-1', 'input_refs': {}, 'status': 'ranked',
            'result': {'ranked_candidates': [{'option_id': 'a', 'rank': 1, 'group_score': .8,
                                                'min_member_score': .6, 'average_member_score': .8,
                                                'fairness_penalty': .01}],
                       'candidate_results': [{'option_id': 'b', 'feasibility': 'infeasible',
                                              'explanation_codes': ['CANNOT_JOIN']}],
                       'pareto_frontier': []},
            'algorithm_input': {'candidates': [{'option_id': 'a', 'title': 'Option A'},
                                                {'option_id': 'b', 'title': 'Option B'}]},
        }
        view = public_result(run)['recommendation_view']
        self.assertEqual(view['recommendation']['title'], 'Option A')
        self.assertEqual(view['unavailable_candidates'], [{'candidate_id': 'b', 'title': 'Option B', 'status': 'infeasible'}])
        self.assertNotIn('CANNOT_JOIN', json.dumps(view))

    def test_structured_budget_conversion_is_exact_and_checks_scope(self):
        plan, replies = snapshots()
        replies['constraints'] = [{'participant_id':'p1','budget':{'kind':'limited','max_cost_minor':120050}}]
        plan['cost_scope'] = 'per_person_total'
        mapped, answers = map_snapshots(plan, replies)
        self.assertEqual(answers['participants'][0]['answers'][-1]['value'], '1200.50')
        self.assertEqual(mapped['questions'][-1]['criterion'], 'max_cost')
        plan['cost_scope'] = 'per_device_total'
        with self.assertRaises(SnapshotError):
            map_snapshots(plan, replies)

    def test_member_review_keeps_other_members_answers_and_issues_private(self):
        run = {'status':'needs_clarification', 'member_states':{'p1':'complete','p2':'complete'},
               'processing':{'preparation':{'constraints':[{'participant_id':'p1','evidence':'own'},
                                                         {'participant_id':'p2','evidence':'PRIVATE'}]}},
               'issues':[{'code':'AMBIGUOUS_ANSWER','path':'responses.participants.p1.answers.q','message':'Review own answer'},
                         {'code':'AMBIGUOUS_ANSWER','path':'responses.participants.p2.answers.q','message':'PRIVATE'}]}
        review = member_review(run,'p1')
        self.assertNotIn('PRIVATE',json.dumps(review))
        self.assertEqual(review['issues'][0]['question_id'],'q')
        with self.assertRaises(SnapshotError):
            member_review(run,'outsider')
