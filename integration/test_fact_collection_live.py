"""Explicit live smoke test: creates a test draft and makes Gemini Search calls.

Run only when GEMINI_API_KEY is configured in the running integration stack.
The normal CI/lifecycle suite never invokes an external provider.
"""
import json
import time
import argparse
from uuid import uuid4

from test_http_lifecycle import PLANNING, call


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--accept-reviewed',action='store_true',help='Verify the known 170 g source claim, accept it into the test draft and run a recommendation')
    args=parser.parse_args()
    user = call(PLANNING, "POST", "/v1/users", {"username": "gemini-smoke-" + str(uuid4())}, status=201)
    token = user["session_token"]
    plan = call(PLANNING, "POST", "/v1/plans", {
        "title": "Gemini source evidence smoke test", "plan_category": "GENERAL", "plan_state": "DRAFT",
        "organiser_id": user["id"], "organiser_name": "Smoke test"}, token, 201)
    option = call(PLANNING, "POST", f"/v1/proposed_activity/plans/{plan['id']}", {
        "title": "Apple iPhone 16", "metadata": {"identity": {
            "model_id": "Apple iPhone 16", "variant": "standard iPhone 16, not Plus or Pro", "region": "SG",
            "source_url": "https://support.apple.com/en-us/121029"}, "facts": []}}, token, 201)
    round_record = call(PLANNING, "POST", f"/v1/rounds/plans/{plan['id']}", {}, token, 201)
    root = f"/v1/rounds/{round_record['id']}"
    started = time.monotonic()
    call(PLANNING, "POST", root + "/fact-collection", {
        "requests": [{"option_id": option["id"], "attribute_id": "mass", "value_type": "number", "unit": "g"}]},
        token, (200, 202))
    while True:
        run = call(PLANNING, "GET", root + "/fact-collection", token=token, status=(200, 202))
        if run["status"] != "pending":
            break
        if time.monotonic() - started > 240:
            raise SystemExit("Gemini smoke test timed out")
        time.sleep(1)
    claims = run.get("collection", {}).get("claims", [])
    print(json.dumps({"status": run["status"], "claim_count": len(claims),
                      "issues": run.get("collection", {}).get("issues", run.get("issues", [])), "elapsed_seconds": round(time.monotonic() - started, 2)}))
    if run["status"] != "needs_review" or not claims:
        raise SystemExit(1)
    # Independently referenced Apple specification is 170 grams; this is one smoke
    # example, not an accuracy benchmark. Claims remain pending and unconfirmed.
    if not any(claim["value"] == 170 and claim["sources"] and claim["review_state"] == "pending" for claim in claims):
        raise SystemExit("Collected mass did not match the referenced specification")
    if args.accept_reviewed:
        reviewed=next((claim for claim in claims if claim['value']==170 and claim['qualifier']=='exact'),None)
        if not reviewed:
            raise SystemExit('The known source claim retained qualifiers; exact-fact acceptance is intentionally blocked')
        acceptance={'operation_id':str(uuid4()),'collection_run_id':run['run_id'],'claim_ids':[reviewed['claim_id']],'reviewed':True}
        accepted=call(PLANNING,'POST',root+'/accept-facts',acceptance,token)
        if accepted!=call(PLANNING,'POST',root+'/accept-facts',acceptance,token):
            raise SystemExit('Acceptance replay changed the operation result')
        question=call(PLANNING,'POST','/v1/question',{
            'plan_id':plan['id'],'title':'Preferred mass?','question_type':'CUSTOM_TEXT','is_required':True,
            'options':{'decision':{'role':'soft','criterion':'mass','relevance':1,'answer_format':'number','numeric_intent':'target',
                                   'mapping':{'value_type':'number','unit':'g','comparison_rule':'numeric_target_v1','scale':200}}}},token,201)
        published=call(PLANNING,'POST',root+'/publish',{'currency':'SGD','currency_minor_digits':2,'cost_scope':'per_person_total','timezone':'UTC','execution_mode':'options'},token)
        # Reviewed collection can never mutate an already published definition.
        call(PLANNING,'POST',root+'/accept-facts',acceptance|{'operation_id':str(uuid4())},token,409)
        from test_http_lifecycle import PARTICIPATION
        own=f"/rounds/{round_record['id']}/my-response"
        saved=call(PARTICIPATION,'PUT',own,{'expectedRevision':0,'acknowledgedOptionRevision':published['option_revision'],
                   'availability':[],'budget':{'kind':'UNANSWERED'},'activityAnswers':[],
                   'answers':[{'question_id':question['id'],'value':170}]},token)
        call(PARTICIPATION,'POST',own+'/submit',{'expectedRevision':saved['revision']},token)
        call(PLANNING,'POST',root+'/close',{},token)
        call(PLANNING,'POST',root+'/recommendations',{},token,(200,202))
        for _ in range(100):
            result=call(PLANNING,'GET',root+'/recommendation',token=token,status=(200,202))
            if result['status']!='pending': break
            time.sleep(0.05)
        if result['status']!='ranked':
            raise SystemExit('Reviewed source fact did not reach an authoritative recommendation')
        print('Reviewed fact acceptance, replay, publication protection and ranking passed')


if __name__ == "__main__":
    main()
