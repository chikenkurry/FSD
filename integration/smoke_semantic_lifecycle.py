"""Optional live Ollama journey with synthetic facts/answers; no Gemini calls.

Run from FSD with the integration stack and its configured Ollama server running.
Creates an isolated synthetic plan. Prints outcomes, never guest session tokens.
"""
import time
from uuid import uuid4

from test_http_lifecycle import PLANNING, PARTICIPATION, call


def wait(path, token, ready):
    until=time.monotonic()+180
    while time.monotonic()<until:
        result=call(PLANNING,'GET',path,token=token,status=(200,202))
        if ready(result):return result
        time.sleep(1)
    raise AssertionError('The live semantic job did not finish within 180 seconds')


def main():
    users=[call(PLANNING,'POST','/v1/users',{'username':'semantic-smoke-'+str(uuid4())},status=201) for _ in range(2)]
    owner,member=users
    plan=call(PLANNING,'POST','/v1/plans',{'title':'Synthetic semantic lifecycle','plan_category':'GENERAL','plan_state':'DRAFT',
        'organiser_id':owner['id'],'organiser_name':'Synthetic organiser'},owner['session_token'],201)
    invite=call(PLANNING,'POST',f"/v1/plans/{plan['id']}/invites",{'created_by':owner['id']},owner['session_token'],201)
    call(PLANNING,'POST',f"/v1/invites/{invite['token']}/join",{'user_id':member['id'],'display_name':'Synthetic member'},member['session_token'])
    options={}
    for title,cost,atmosphere,cuisine in [('Synthetic A','85','calm','Italian'),('Synthetic B','100','calm','Italian'),('Synthetic C','80','lively','French')]:
        facts=[{'criterion':'max_cost','value_type':'decimal','value':cost,'unit':'SGD','status':'confirmed','source':'Synthetic menu fixture','context':{'scope':'per_person_total'}},
               {'criterion':'atmosphere','value_type':'category','value':atmosphere,'status':'confirmed','source':'Synthetic venue fixture'},
               {'criterion':'cuisine','value_type':'category','value':cuisine,'status':'confirmed','source':'Synthetic menu fixture'}]
        option=call(PLANNING,'POST',f"/v1/proposed_activity/plans/{plan['id']}",{'title':title,'metadata':{'facts':facts}},owner['session_token'],201)
        options[title]=option['id']
    question=call(PLANNING,'POST','/v1/question',{'plan_id':plan['id'],'title':'What preferences or requirements should we consider?',
        'question_type':'CUSTOM_TEXT','is_required':True,'options':{'options':[],'decision':{
            'role':'soft','criterion':'preferences','answer_format':'text','relevance':1}}},owner['session_token'],201)
    round_record=call(PLANNING,'POST',f"/v1/rounds/plans/{plan['id']}",{},owner['session_token'],201)
    root=f"/v1/rounds/{round_record['id']}"
    published=call(PLANNING,'POST',root+'/publish',{'currency':'SGD','currency_minor_digits':2,'cost_scope':'per_person_total',
        'timezone':'UTC','execution_mode':'options','interpretation_policy':'facts-v1'},owner['session_token'])
    for user in users:
        path=f"/rounds/{round_record['id']}/my-response"
        body={'expectedRevision':0,'acknowledgedOptionRevision':published['option_revision'],'availability':[],'budget':{'kind':'UNANSWERED'},
              'activityAnswers':[],'privateNote':None,'answers':[{'question_id':question['id'],
              'value':'I must stay below SGD 100; I prefer somewhere peaceful and Italian.'}]}
        saved=call(PARTICIPATION,'PUT',path,body,user['session_token'])
        call(PLANNING,'POST',root+'/preview',{'expected_revision':saved['revision'],'retry':True},user['session_token'],(200,202))
        review=wait(root+'/preview',user['session_token'],lambda r:'constraints' in r)
        assert not [i for i in review['issues'] if i['code'] not in {'CONFIRM_REQUIREMENT','EXECUTION_ADAPTER_REQUIRED'}],review['issues']
        requirements=review['constraints']
        assert len(requirements)==1 and requirements[0]['constraint_rule']=='less_than_v1',requirements
        assert {p['attribute_id'] for p in review['preferences']}=={'cuisine','atmosphere'},review['preferences']
        body['expectedRevision']=saved['revision']
        body['answers'][0].update(reviewed_revision=saved['revision'],confirmed_requirements=[{
            'attribute_id':r['attribute_id'],'required_value':r['required_value'],'constraint_rule':r['constraint_rule'],'unit':r['unit']} for r in requirements])
        saved=call(PARTICIPATION,'PUT',path,body,user['session_token'])
        call(PARTICIPATION,'POST',path+'/submit',{'expectedRevision':saved['revision']},user['session_token'])
    call(PLANNING,'POST',root+'/close',{},owner['session_token'])
    call(PLANNING,'POST',root+'/recommendations',{},owner['session_token'],(200,202))
    result=wait(root+'/recommendation',owner['session_token'],lambda r:r['status']!='pending')
    assert result['status']=='ranked',result.get('issues')
    view=result['recommendation_view']
    assert view['recommendation']['candidate_id']==options['Synthetic A'],view
    assert options['Synthetic B'] not in [c['candidate_id'] for c in [view['recommendation'],*view['alternatives']]],view
    print('PASS: live Ollama -> two member reviews -> explicit budget confirmation -> close -> deterministic ranking.')
    print('PASS: peaceful matched calm; the venue costing exactly SGD 100 failed the strict budget boundary.')


if __name__=='__main__':main()
