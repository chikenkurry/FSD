"""Run against compose.integration.yaml; creates isolated, randomly named test plans."""
import json
import os
import unittest
import time
from urllib.error import URLError
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

PLANNING = os.environ.get('PLANNING_URL', 'http://127.0.0.1:18080')
PARTICIPATION = os.environ.get('PARTICIPATION_URL', 'http://127.0.0.1:13002')


def call(base, method, path, body=None, token=None, status=200):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer '+token
    request = Request(base+path, data=json.dumps(body).encode() if body is not None else None,
                      headers=headers, method=method)
    try:
        response = urlopen(request, timeout=180)
    except HTTPError as error:
        response = error
    with response:
        data = json.loads(response.read() or b'{}')
        if response.code != status:
            raise AssertionError(f'{method} {path}: expected {status}, got {response.code}: {data}')
        return data


class ServiceJourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        deadline = time.monotonic() + 30
        while True:
            try:
                call(PLANNING, 'GET', '/health')
                call(PARTICIPATION, 'GET', '/health/ready')
                return
            except (URLError, AssertionError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)

    def create_plan(self, *, unknown=False, scheduled=False):
        owner = call(PLANNING, 'POST', '/v1/users', {'username': 'integration-'+str(uuid4())}, status=201)
        member = call(PLANNING, 'POST', '/v1/users', {'username': 'integration-'+str(uuid4())}, status=201)
        plan = call(PLANNING, 'POST', '/v1/plans', {
            'title':'Choose a device', 'plan_category':'GENERAL', 'plan_state':'DRAFT',
            'organiser_id':owner['id'], 'organiser_name':'Organiser'}, owner['session_token'], 201)
        invite = call(PLANNING, 'POST', f"/v1/plans/{plan['id']}/invites", {'created_by':owner['id']}, owner['session_token'], 201)
        call(PLANNING, 'POST', f"/v1/invites/{invite['token']}/join", {'user_id':member['id'],'display_name':'Member'}, member['session_token'])
        options = []
        for index, (price, mass) in enumerate([('20.00',1.2), ('40.00',0.8)]):
            facts = [{'criterion':'max_cost','value':price,'unit':'SGD','status':'confirmed','source':'synthetic test quote', 'context':{'scope':'per_person_total'}}]
            if scheduled:
                facts.append({'criterion':'environment','value':'indoor','status':'confirmed','source':'synthetic venue fixture'})
            else:
                facts.append({'criterion':'mass','value':None if unknown and index==1 else mass,
                              'value_type':'number','unit':'kg','status':'unknown' if unknown and index==1 else 'confirmed','source':'synthetic specification'})
            metadata = {'facts':facts}
            if scheduled:
                metadata['candidates'] = [{'candidate_id':'candidate-'+str(uuid4()),'start_at':'2027-01-01T10:00:00Z','end_at':'2027-01-01T11:00:00Z'}]
            options.append(call(PLANNING, 'POST', f"/v1/proposed_activity/plans/{plan['id']}",
                                {'title':f'Option {index+1}','metadata':metadata}, owner['session_token'], 201))
        if scheduled:
            definition = {'role':'soft','criterion':'environment','relevance':1,'answer_format':'choice'}
            question_type = 'CUSTOM_SINGLE_CHOICE'
            choices = ['indoor','outdoor']
            label = 'Environment preference?'
        else:
            definition = {'role':'soft','criterion':'mass','relevance':1,'answer_format':'number','numeric_intent':'target',
                          'mapping':{'value_type':'number','unit':'kg','comparison_rule':'numeric_target_v1','scale':0.4}}
            question_type = 'CUSTOM_TEXT'
            choices = []
            label = 'Preferred mass?'
        question = call(PLANNING,'POST','/v1/question',{'plan_id':plan['id'],'title':label,
            'question_type':question_type,'is_required':True,'options':{'options':choices,'decision':definition}},owner['session_token'],201)
        round_record = call(PLANNING,'POST',f"/v1/rounds/plans/{plan['id']}",{},owner['session_token'],201)
        settings = {'currency':'SGD','currency_minor_digits':2,'cost_scope':'per_person_total','timezone':'UTC',
                    'execution_mode':'scheduled' if scheduled else 'options'}
        published = call(PLANNING,'POST',f"/v1/rounds/{round_record['id']}/publish",settings,owner['session_token'])
        repeat = call(PLANNING,'POST',f"/v1/rounds/{round_record['id']}/publish",settings,owner['session_token'])
        self.assertEqual(published['option_snapshot_id'],repeat['option_snapshot_id'])
        form = call(PLANNING,'GET',f"/v1/rounds/{round_record['id']}/form",token=member['session_token'])
        return owner,member,plan,options,question,round_record,published,form

    def submit(self, user, round_record, question, revision, *, scheduled=False, flag=None, budget=False):
        data = {'expectedRevision':0,'acknowledgedOptionRevision':revision,
                'availability':[{'startAt':'2027-01-01T09:00:00Z','endAt':'2027-01-01T12:00:00Z'}] if scheduled else [],
                'budget':{'kind':'CAP','capMinor':budget if type(budget) is int else 3000} if budget else {'kind':'UNANSWERED'},
                'activityAnswers':[flag] if flag else [],
                'answers':[{'question_id':question['id'],'value':'indoor' if scheduled else 1.2}],
                'privateNote':'PRIVATE-INTEGRATION-NOTE'}
        path=f"/rounds/{round_record['id']}/my-response"
        call(PARTICIPATION,'PUT',path,{k:v for k,v in data.items() if k!='budget'},user['session_token'],400)
        saved=call(PARTICIPATION,'PUT',path,data,user['session_token'])
        submitted=call(PARTICIPATION,'POST',path+'/submit',{'expectedRevision':saved['revision']},user['session_token'])
        self.assertEqual(submitted['revision'],saved['revision']+1)
        replay=call(PARTICIPATION,'POST',path+'/submit',{'expectedRevision':saved['revision']},user['session_token'])
        self.assertEqual(replay['revision'],submitted['revision'])
        call(PARTICIPATION,'PUT',path,data|{'expectedRevision':saved['revision']},user['session_token'],409)
        return data,submitted

    def test_publish_submit_freeze_rank_confirm_and_reopen(self):
        owner,member,plan,options,question,round_record,published,form=self.create_plan()
        self.assertEqual({q['question_id'] for q in form['questions']},{question['id']})
        self.submit(owner,round_record,question,published['option_revision'],budget=True)
        body,submitted=self.submit(member,round_record,question,published['option_revision'])
        call(PLANNING,'PATCH',f"/v1/question/{question['id']}",{'title':'Changed'},owner['session_token'],409)
        root=f"/v1/rounds/{round_record['id']}"
        closed=call(PLANNING,'POST',root+'/close',{},owner['session_token'])
        again=call(PLANNING,'POST',root+'/close',{},owner['session_token'])
        self.assertEqual(closed['response_snapshot_id'],again['response_snapshot_id'])
        call(PARTICIPATION,'PUT',f"/rounds/{round_record['id']}/my-response",body|{'expectedRevision':submitted['revision']},member['session_token'],409)
        run=call(PLANNING,'POST',root+'/recommendations',{},owner['session_token'])
        self.assertEqual(run['status'],'ranked')
        self.assertEqual(run['result']['ranked_candidates'][0]['option_id'],options[0]['id'])
        self.assertEqual(call(PLANNING,'POST',root+'/recommendations',{},owner['session_token'])['run_id'],run['run_id'])
        self.assertNotIn('PRIVATE-INTEGRATION-NOTE',json.dumps(run))
        self.assertNotIn('participants',json.dumps(run))
        own_review=call(PLANNING,'GET',root+'/clarifications',token=member['session_token'])
        self.assertEqual(own_review['response_status'],'complete')
        self.assertTrue(own_review['preferences'])
        self.assertTrue(all(row['participant_id']==member['id'] for row in own_review['preferences']))
        self.assertNotIn(owner['id'],json.dumps(own_review))
        confirmation={'operation_id':str(uuid4()),'run_id':run['run_id'],'candidate_id':options[0]['id']}
        call(PLANNING,'POST',root+'/confirm',confirmation|{'candidate_id':options[1]['id']},owner['session_token'],409)
        call(PLANNING,'POST',root+'/confirm',confirmation,member['session_token'],403)
        selected=call(PLANNING,'POST',root+'/confirm',confirmation,owner['session_token'])
        self.assertEqual(selected,call(PLANNING,'POST',root+'/confirm',confirmation,owner['session_token']))
        self.assertEqual(call(PLANNING,'POST',root+'/close',{},owner['session_token'])['state'],'CONFIRMED')
        self.assertEqual(call(PLANNING,'GET',f"/v1/plans/{plan['id']}",token=owner['session_token'])['state'],'CONFIRMED')
        operation={'operation_id':str(uuid4())}
        reopened=call(PLANNING,'POST',root+'/reopen',operation,owner['session_token'])
        self.assertNotEqual(reopened['id'],round_record['id'])
        self.assertEqual(reopened['id'],call(PLANNING,'POST',root+'/reopen',operation,owner['session_token'])['id'])
        self.assertEqual(call(PLANNING,'GET',root+'/form',token=owner['session_token']),form)
        call(PLANNING,'POST',root+'/recommendations',{},owner['session_token'],409)
        next_root=f"/v1/rounds/{reopened['id']}"
        next_publication=call(PLANNING,'POST',next_root+'/publish',{'currency':'SGD','currency_minor_digits':2,
            'cost_scope':'per_person_total','timezone':'UTC','execution_mode':'options'},owner['session_token'])
        own=f"/rounds/{reopened['id']}/my-response"
        copied=call(PARTICIPATION,'POST',own+'/copy',{'sourceRoundId':round_record['id']},member['session_token'])
        self.assertEqual(copied['status'],'DRAFT')
        self.assertEqual(copied['acknowledgedOptionRevision'],published['option_revision'])
        call(PARTICIPATION,'POST',own+'/submit',{'expectedRevision':copied['revision']},member['session_token'],409)
        reviewed=call(PARTICIPATION,'PUT',own,body|{'expectedRevision':copied['revision'],
            'acknowledgedOptionRevision':next_publication['option_revision']},member['session_token'])
        call(PARTICIPATION,'POST',own+'/submit',{'expectedRevision':reviewed['revision']},member['session_token'])

    def test_missing_member_blocks_the_decision(self):
        owner,member,plan,options,question,round_record,published,form=self.create_plan()
        self.submit(owner,round_record,question,published['option_revision'])
        root=f"/v1/rounds/{round_record['id']}"
        call(PLANNING,'POST',root+'/close',{},owner['session_token'])
        result=call(PLANNING,'POST',root+'/recommendations',{},owner['session_token'])
        self.assertEqual(result['status'],'blocked')
        self.assertIn('INCOMPLETE_RESPONSE',[issue['code'] for issue in result['issues']])

    def test_missing_fact_requests_review_instead_of_ranking_a_subset(self):
        owner,member,plan,options,question,round_record,published,form=self.create_plan(unknown=True)
        for user in (owner,member):
            self.submit(user,round_record,question,published['option_revision'])
        root=f"/v1/rounds/{round_record['id']}"
        call(PLANNING,'POST',root+'/close',{},owner['session_token'])
        result=call(PLANNING,'POST',root+'/recommendations',{},owner['session_token'])
        self.assertEqual(result['status'],'needs_information')
        call(PLANNING,'POST',root+'/confirm',{'operation_id':str(uuid4()),'run_id':result['run_id'],'candidate_id':options[0]['id']},owner['session_token'],409)

    def test_scheduled_candidates_preserve_member_flags(self):
        owner,member,plan,options,question,round_record,published,form=self.create_plan(scheduled=True)
        self.submit(owner,round_record,question,published['option_revision'],scheduled=True, budget=5000,
                    flag={'activityId':options[0]['id'],'kind':'CANNOT_JOIN'})
        self.submit(member,round_record,question,published['option_revision'],scheduled=True)
        root=f"/v1/rounds/{round_record['id']}"
        call(PLANNING,'POST',root+'/close',{},owner['session_token'])
        result=call(PLANNING,'POST',root+'/recommendations',{},owner['session_token'])
        self.assertEqual(result['status'],'ranked',result)
        self.assertEqual(len(result['result']['ranked_candidates']),1)
        failures=[c for c in result['result']['candidate_results'] if c['feasibility']=='infeasible']
        self.assertIn('CANNOT_JOIN',failures[0]['explanation_codes'])


if __name__=='__main__':
    unittest.main(verbosity=2)
