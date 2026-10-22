import {test,expect} from '@playwright/test';

test('pending recommendations resume after reload and confirmed results appear automatically',async({page})=>{
  let completed=false;let confirmed=false;let recommendationPosts=0;
  const candidate={candidate_id:'option-a',title:'Option A',rank:1,primary_objective_tie_size:1,group_score:0.8,minimum_member_score:0.7,average_member_score:0.8};
  await page.addInitScript(()=>{sessionStorage.setItem('user_id','member');sessionStorage.setItem('username','Member');sessionStorage.setItem('session_token','synthetic-member-token');});
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    const reply=(value:unknown,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)});
    if(path.endsWith('/form'))return reply({plan_id:'plan',round_id:'round',option_revision:1,currency:'SGD',currency_minor_digits:2,execution_mode:'options',decision_question:'Which option?',questions:[],options:[{option_id:'option-a',title:'Option A'}]});
    if(path.endsWith('/v1/plans/plan'))return reply({id:'plan',title:'A shared decision',created_by_user_id:'owner',state:confirmed?'CONFIRMED':'REVIEWING'});
    if(path.endsWith('/rounds/plans/plan'))return reply({data:[{id:'round',round_number:1}]});
    if(path.endsWith('/recommendations')){recommendationPosts++;return reply({});}
    if(path.endsWith('/recommendation'))return reply({run_id:'run',status:completed?'ranked':'pending',issues:[],recommendation_view:{recommendation:completed?candidate:null,alternatives:[],pareto_alternatives:[],unavailable_candidates:[],next_action:null}},completed?200:202);
    if(path.endsWith('/selection'))return confirmed?reply({run_id:'run',candidate_id:'option-a',selection_version:1}):reply({code:'NOT_FOUND'},404);
    if(path.endsWith('/my-rsvp'))return reply({revision:0,status:null});
    return reply({});
  });
  await page.goto('/#round=round');
  await expect(page.getByText('Calculating the recommendation. This usually takes a few seconds.')).toBeVisible();
  await page.reload();completed=true;
  await expect(page.getByRole('heading',{name:'Recommended: Option A'})).toBeVisible();
  expect(recommendationPosts).toBe(0);
  confirmed=true;
  await expect(page.getByRole('heading',{name:'Confirmed selection',exact:true})).toBeVisible();
  await expect(page.getByLabel('Going',{exact:true})).toBeVisible();
});
