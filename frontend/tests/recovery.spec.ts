import { test, expect, type Page } from '@playwright/test';

async function setup(page: Page, emptyFacts = false) {
  let holdOverviews = false;
  let holdFacts = false;
  const posts = { overviews: 0, questions: 0, facts: 0, plans: 0 };
  const runs = new Map<string, { task: string; research: unknown }>();
  let serial = 0;
  let plan:Record<string,unknown>={};let metadata:Record<string,unknown>={};
  const savedOptions:Record<string,unknown>[]=[];const savedQuestions:Record<string,unknown>[]=[];
  await page.route('**/api/**', async route => {
    const req = route.request(); const path = new URL(req.url()).pathname;
    const body = ['POST','PATCH','PUT'].includes(req.method()) ? req.postDataJSON() : undefined;
    const reply = (data: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    if (path.endsWith('/v1/users')) return reply({ id: 'recovery-user', username: 'Recovery test', session_token: 'synthetic-recovery-token' });
    if (path.includes('/plans/member/')) return reply([]);
    if (path.endsWith('/research')) {
      if (req.method() === 'POST') {
        const task = body.task as 'overviews' | 'questions' | 'facts'; posts[task]++;
        if(task==='facts'){
          expect(body.input).not.toHaveProperty('questions');
          expect(body.input).not.toHaveProperty('decision_question');
          expect(body.input).not.toHaveProperty('summaries');
          expect(body.input.attributes).toEqual([{criterion:'atmosphere',value_type:'category',unit:null}]);
        }
        const id = `run-${++serial}`;
        const options = body.input.options as { key: string; title: string }[];
        const research = task === 'overviews' ? { options: options.map(o => ({ key: o.key, kind: 'other', place_id: null, overview: { source: 'web_search', summary: `${o.title} verified description`, sources: [], highlights: [] } })) }
          : task === 'questions' ? { questions: [{ title: 'What atmosphere do you prefer?', help: '', type: 'single', value_type: 'category', role: 'preference', criterion: 'atmosphere', choices: ['Quiet', 'Lively'] }] }
          : { facts: emptyFacts && posts.facts === 1 ? [] : options.map(o => ({ option: o.key, criterion: 'atmosphere', value: 'Quiet', value_type: 'category', unit: null, context: {qualifier:'exact',source_text:'The venue is quiet.'}, sources: [{url:'https://example.com/venue'}] })) };
        runs.set(id, { task, research }); return reply({ run_id: id, status: 'pending', issues: [] }, 202);
      }
      const id = new URL(req.url()).searchParams.get('run')!;
      const run = runs.get(id)!;
      return reply({ run_id: id, status: run.task === 'overviews' && holdOverviews || run.task==='facts' && holdFacts ? 'pending' : 'completed', issues: [], research: run.research });
    }
    if (path.endsWith('/v1/plans') && req.method() === 'POST') { posts.plans++;plan={...body,id:'saved-plan',category:body.plan_category,state:'DRAFT'}; return reply({ id: 'saved-plan' }); }
    if(path.endsWith('/v1/plans/saved-plan') && req.method()==='PATCH'){Object.assign(plan,body);return reply(plan);}
    if(path.endsWith('/plans/details/saved-plan'))return reply({...plan,rounds:[{id:'saved-round',round_number:1}],proposed_activities:savedOptions,questions:savedQuestions});
    if(path.endsWith('/draft')){if(req.method()==='PUT')metadata=body;return reply({state:metadata});}
    if (path.includes('/proposed_activity/plans/')) {const row={...body,id:`option-${++serial}`};savedOptions.push(row);return reply(row);}
    if(path.includes('/proposed_activity/') && req.method()==='PATCH'){Object.assign(savedOptions.find(o=>path.endsWith(String(o.id)))!,body);return reply({});}
    if (path.endsWith('/v1/question') && req.method() === 'POST') {const row={...body,type:body.question_type,id:`question-${++serial}`};savedQuestions.push(row);return reply(row);}
    if(path.includes('/v1/question/') && req.method()==='PATCH'){Object.assign(savedQuestions.find(q=>path.endsWith(String(q.id)))!,body);return reply({});}
    if (path.includes('/rounds/plans/')) return req.method()==='GET'?reply({data:[{id:'saved-round',round_number:1}]}):reply({ id: 'saved-round' });
    return reply({});
  });
  await page.goto('/');
  await page.getByLabel('Your display name').fill('Recovery test');
  await page.getByRole('button', { name: 'Create guest session' }).click();
  await page.getByRole('button', { name: 'Create form', exact: true }).first().click();
  return { posts, hold: (value: boolean) => { holdOverviews = value; }, holdFacts:(value:boolean)=>{holdFacts=value;} };
}

async function basics(page: Page) {
  await page.getByLabel('Plan name').fill('A recoverable plan');
  await page.getByRole('radio', { name: /^Event/ }).check();
  await page.getByLabel('Earliest date').fill('2027-06-01');
  await page.getByLabel('Latest date').fill('2027-06-02');
  await page.getByLabel('Location or platform').fill('Singapore');
  await page.getByRole('button', { name: 'Next step' }).click();
  await page.getByLabel('Option 1 name').fill('Restaurant A');
  await page.getByLabel('Option 2 name').fill('Restaurant B');
}

async function evidence(page: Page) {
  await page.getByRole('button',{name:/Overview$/}).click();
  await page.getByText('View or correct supporting facts',{exact:true}).click();
}
async function publishBoundary(page: Page) {
  let policy='';
  await page.route('**/publish',route=>{
    policy=route.request().postDataJSON().interpretation_policy;
    return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({message:'Publication boundary reached'})});
  });
  await page.getByRole('button',{name:'Publish form'}).click();
  await expect(page.getByRole('alert').filter({hasText:'Publication boundary reached'})).toBeVisible();
  expect(policy).toBe('facts-v1');
}

test('creator resumes every step and pending research without duplicate plans or jobs', async ({ page }) => {
  const fixture = await setup(page);await basics(page);
  await page.reload();await expect(page.getByLabel('Option 1 name')).toHaveValue('Restaurant A');
  fixture.hold(true);await page.getByRole('button',{name:'Look them up'}).click();
  await expect.poll(()=>fixture.posts.overviews).toBe(2);await page.reload();
  await expect(page.getByRole('heading',{name:'Your options at a glance'})).toBeVisible();
  fixture.hold(false);await expect(page.locator('.overview-card').first()).toContainText('verified description');
  expect(fixture.posts.overviews).toBe(2);expect(fixture.posts.plans).toBe(1);
  await page.getByRole('button',{name:'Draft questions'}).click();
  await expect(page.getByLabel('Question',{exact:true})).toHaveValue('What atmosphere do you prefer?');
  await page.getByLabel('Help text').fill('Keep this edit');await page.reload();
  await expect(page.getByLabel('Help text')).toHaveValue('Keep this edit');expect(fixture.posts.questions).toBe(1);
  await page.getByRole('button',{name:'Review form'}).click();await page.reload();
  await expect(page.getByRole('heading',{name:'Review and publish'})).toBeVisible();
  await expect(page.getByText('Worth checking before you publish')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Publish form'})).toBeEnabled();
  const restored=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('what2do:checkpoint:v1:recovery-user:creator')!));
  expect(restored.form.id).toBe('saved-plan');expect(restored.form.roundId).toBe('saved-round');
  expect(restored.form.decisionOptions[0].overview).toBeUndefined();
  expect(restored.form.decisionOptions[0].brief.summary).toContain('verified description');expect(fixture.posts.plans).toBe(1);
});

test('slow supporting research never blocks review or publishing and question edits do not trigger lookup', async ({ page }) => {
  const fixture=await setup(page);await basics(page);fixture.holdFacts(true);
  await page.getByRole('button',{name:'Look them up'}).click();
  await expect(page.locator('.overview-card').first()).toContainText('verified description');
  await expect.poll(()=>fixture.posts.facts).toBe(1);
  await page.getByRole('button',{name:'Draft questions'}).click();
  await expect(page.getByLabel('Question',{exact:true})).toHaveValue('What atmosphere do you prefer?');
  await page.getByRole('button',{name:'Review form'}).click();
  await expect(page.getByRole('heading',{name:'Review and publish'})).toBeVisible({timeout:1500});
  await expect(page.getByRole('button',{name:'Publish form'})).toBeEnabled();
  await expect(page.getByRole('heading',{name:'Supporting facts'})).toHaveCount(0);
  await page.getByRole('button',{name:/Questions$/}).click();
  await page.getByLabel('Help text').fill('Editing stays available');
  await page.getByLabel('Question 1 choice 1').fill('Peaceful');
  await page.getByRole('button',{name:'Review form'}).click();
  expect(fixture.posts.facts).toBe(1);await publishBoundary(page);fixture.holdFacts(false);
});

test('pending supporting facts resume across refresh without another research job',async({page})=>{
  const fixture=await setup(page);await basics(page);fixture.holdFacts(true);
  await page.getByRole('button',{name:'Look them up'}).click();
  await expect.poll(()=>fixture.posts.facts).toBe(1);
  await page.getByRole('button',{name:'Draft questions'}).click();
  await expect(page.getByLabel('Question',{exact:true})).toHaveValue('What atmosphere do you prefer?');
  await page.reload();fixture.holdFacts(false);await evidence(page);
  await expect(page.getByTestId('fact-Restaurant A-atmosphere').getByLabel('Fact value')).toHaveValue('Quiet');
  await expect(page.getByTestId('fact-Restaurant A-atmosphere').getByText('Sourced',{exact:true})).toBeVisible();
  expect(fixture.posts.facts).toBe(1);
});

test('missing evidence is optional at option review and can be researched again without a publishing gate', async ({ page }) => {
  const fixture=await setup(page,true);await basics(page);
  await page.getByRole('button',{name:'Look them up'}).click();
  await expect.poll(()=>fixture.posts.facts).toBe(1);
  await page.getByText('View or correct supporting facts',{exact:true}).click();
  const row=page.getByTestId('fact-Restaurant A-atmosphere');
  await expect(row.getByText('Missing',{exact:true})).toBeVisible();
  await row.getByText('Research or correct this fact',{exact:true}).click();
  await expect(row.getByRole('button',{name:'Research again',exact:true})).toBeEnabled();
  await row.getByRole('button',{name:'Research again',exact:true}).click();
  await expect(row.getByLabel('Fact value')).toHaveValue('Quiet');
  await expect(row.getByText('Sourced',{exact:true})).toBeVisible();expect(fixture.posts.facts).toBe(2);
  await page.getByRole('button',{name:'Draft questions'}).click();
  await expect(page.getByLabel('Question',{exact:true})).toHaveValue('What atmosphere do you prefer?');
  await page.getByRole('button',{name:'Review form'}).click();
  await expect(page.getByText('Worth checking before you publish')).toHaveCount(0);await publishBoundary(page);
});

test('slow research preserves manual corrections and changing option identity invalidates old evidence',async({page})=>{
  const fixture=await setup(page);await basics(page);
  await page.getByRole('button',{name:'Look them up'}).click();
  await expect.poll(()=>fixture.posts.facts).toBe(1);
  await page.getByText('View or correct supporting facts',{exact:true}).click();
  const row=page.getByTestId('fact-Restaurant A-atmosphere');
  await expect(row.getByLabel('Fact value')).toHaveValue('Quiet');
  await row.getByText('Research or correct this fact',{exact:true}).click();fixture.holdFacts(true);
  await row.getByRole('button',{name:'Research again',exact:true}).click();
  await expect.poll(()=>fixture.posts.facts).toBe(2);
  await row.getByLabel('Fact value').fill('Lively');await row.getByRole('button',{name:'Use my correction'}).click();
  fixture.holdFacts(false);await expect(row.getByRole('button',{name:'Research again',exact:true})).toBeEnabled();
  await expect(row.getByLabel('Fact value')).toHaveValue('Lively');await expect(row.getByText('Corrected',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:/Options$/}).click();await page.getByLabel('Option 1 name').fill('Restaurant A revised');
  await evidence(page);const revised=page.getByTestId('fact-Restaurant A revised-atmosphere');
  await expect(revised.getByText('Needs updating',{exact:true})).toBeVisible();
});

test('neutral facts and saved corrections survive wording and choice edits without choice tagging',async({page})=>{
  const fixture=await setup(page);await basics(page);await page.getByRole('button',{name:'Look them up'}).click();
  await expect.poll(()=>fixture.posts.facts).toBe(1);await page.getByText('View or correct supporting facts',{exact:true}).click();
  const row=page.getByTestId('fact-Restaurant A-atmosphere');await expect(row.getByLabel('Fact value')).toHaveValue('Quiet');
  await row.getByLabel('Fact value').fill('Calm and intimate');await row.getByRole('button',{name:'Use my correction'}).click();
  await page.getByRole('button',{name:'Draft questions'}).click();
  await page.getByLabel('Question',{exact:true}).fill('What setting should we choose?');
  await page.getByLabel('Question 1 choice 1').fill('Peaceful');await page.getByLabel('Question 1 choice 2').fill('Social');
  await evidence(page);await expect(row.getByLabel('Fact value')).toHaveValue('Calm and intimate');
  await expect(row.getByText('Corrected',{exact:true})).toBeVisible();expect(fixture.posts.facts).toBe(1);
  await page.reload();await page.getByText('View or correct supporting facts',{exact:true}).click();
  await expect(row.getByLabel('Fact value')).toHaveValue('Calm and intimate');await expect(row.getByText('Corrected',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:/Review$/}).click();await publishBoundary(page);
});

test('switching answer formats saves typed definitions and keeps written answers scored',async({page})=>{
  await setup(page);await basics(page);await page.getByRole('button',{name:'Look them up'}).click();
  await page.getByRole('button',{name:'Draft questions'}).click();
  await expect(page.getByLabel('Question',{exact:true})).toHaveValue('What atmosphere do you prefer?');
  const numeric=page.waitForRequest(r=>r.method()==='PATCH'&&r.url().includes('/v1/question/')&&r.postDataJSON()?.options?.decision?.answer_format==='number');
  await page.getByLabel('Answer type').selectOption('Number');const definition=(await numeric).postDataJSON().options.decision;
  expect(definition.mapping.value_type).toBe('number');expect(definition.mapping.comparison_rule).toBe('numeric_target_v1');
  const written=page.waitForRequest(r=>r.method()==='PATCH'&&r.url().includes('/v1/question/')&&r.postDataJSON()?.options?.decision?.answer_format==='text');
  await page.getByLabel('Answer type').selectOption('Short answer');const text=(await written).postDataJSON().options.decision;
  expect(text.role).toBe('soft');expect(text.mapping.value_type).toBe('number');
});

test('storage failure is visible instead of promising refresh recovery', async ({ page }) => {
  await page.addInitScript(()=>{const original=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){
    if(key.startsWith('what2do:checkpoint:'))throw new DOMException('Synthetic full storage','QuotaExceededError');return original.call(this,key,value);
  };});
  await setup(page);await page.getByLabel('Plan name').fill('Unsaved browser edit');
  await expect(page.getByRole('alert')).toContainText('Browser storage is unavailable');
});

test('fresh research updates only the selected fact and keeps other organiser corrections', async ({page})=>{
  await page.addInitScript(()=>Object.defineProperty(crypto,'randomUUID',{value:undefined,configurable:true}));
  const fixture=await setup(page);await basics(page);await page.getByRole('button',{name:'Look them up'}).click();
  await expect.poll(()=>fixture.posts.facts).toBe(1);await page.getByText('View or correct supporting facts',{exact:true}).click();
  const first=page.getByTestId('fact-Restaurant A-atmosphere');const second=page.getByTestId('fact-Restaurant B-atmosphere');
  await expect(first.getByText('Sourced',{exact:true})).toBeVisible();
  for(const row of [first,second]){await row.getByLabel('Fact value').fill('Lively');await row.getByRole('button',{name:'Use my correction'}).click();}
  await first.getByText('Research or correct this fact',{exact:true}).click();
  await first.getByLabel('What should research check?').fill('Check the latest venue description.');
  await first.getByRole('button',{name:'Research again',exact:true}).click();
  await expect(first.getByLabel('Fact value')).toHaveValue('Quiet');await expect(first.getByText('Sourced',{exact:true})).toBeVisible();
  await expect(second.getByLabel('Fact value')).toHaveValue('Lively');await expect(second.getByText('Corrected',{exact:true})).toBeVisible();
  expect(fixture.posts.facts).toBe(2);
});
