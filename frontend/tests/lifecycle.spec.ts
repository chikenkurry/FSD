import { test, expect, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';

async function capture(page: Page, project: string, screen: string) {
  const root = process.env.UI_CAPTURE_DIR;
  if (!root) return;
  await mkdir(root, { recursive: true });
  await page.evaluate(() => document.fonts.ready);
  // Let entrance and step transitions settle so captures show the resting state.
  await page.evaluate(() => Promise.all(document.getAnimations().filter(a => a.effect?.getTiming().iterations !== Infinity).map(a => a.finished.catch(() => undefined))));
  await page.screenshot({ path: join(root, `${project}-${screen}.png`), fullPage: true });
}

async function fits(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
}
async function activeStepFits(page: Page) {
  const box = await page.locator('.step-pill[aria-current="step"]').boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
}
async function invited(page: Page, name: string) {
  await expect(page.getByRole('heading', { name: 'Help your group decide' })).toBeVisible();
  await page.getByLabel('Your name').fill(name);
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
}
async function guest(page: Page, name: string) {
  await page.getByLabel('Your display name').fill(name);
  await page.getByRole('button', { name: 'Create guest session', exact: true }).click();
  await expect(page.getByRole('button', { name: 'My forms', exact: true })).toBeVisible();
}

test('create, invite, privately review, submit, rank, confirm and RSVP', async ({ page, browser }, info) => {
  const name = `Browser ${info.project.name} ${Date.now()}`;
  // Observe autosave from the start, including recovery before option research.
  let planCreates = 0;
  page.on('request', req => { if (req.method() === 'POST' && req.url().endsWith('/v1/plans')) planCreates++; });
  await page.goto('/'); await fits(page); await capture(page, info.project.name, 'login'); await guest(page, name);
  await expect(page.getByRole('heading', { name: 'What would you like to decide?' })).toBeVisible();
  await capture(page, info.project.name, 'empty');
  await page.getByRole('button', { name: 'Create form', exact: true }).first().click();
  await page.getByRole('button', { name: 'Next step' }).click();
  await activeStepFits(page);
  await expect(page.getByRole('alert')).toContainText('Add a plan name and choose a category');
  await expect(page.getByLabel('Plan name')).toHaveAttribute('aria-invalid', 'true');
  await activeStepFits(page);
  await capture(page, info.project.name, 'creator');
  await page.getByLabel('Plan name').fill(name);
  await page.reload();
  await expect(page.getByLabel('Plan name')).toHaveValue(name);
  await page.getByRole('radio', { name: /^General/ }).check();
  await page.locator('input[type=date]').nth(0).fill('2027-06-03');
  await page.locator('input[type=date]').nth(1).fill('2027-06-01');
  await expect(page.getByText('The latest date must be on or after the earliest date.')).toBeVisible();
  await page.locator('input[type=date]').nth(0).fill('2027-06-01');
  await page.locator('input[type=date]').nth(1).fill('2027-06-03');
  await expect(page.getByText('A 3-day window.')).toBeVisible();
  await page.getByLabel('Location or platform').fill('Group choice');
  await page.getByRole('button', { name: 'Next step' }).click();
  await activeStepFits(page);
  await expect(page.locator('.step-pill[aria-current="step"]')).toContainText('Options');
  await page.reload();
  await expect(page.locator('.step-pill[aria-current="step"]')).toContainText('Options');
  await page.getByLabel('The question your group is answering').fill('Where should we meet?');
  await page.getByLabel('Option 1 name').fill('Cafe');
  await page.getByLabel('Option 1 name').press('Enter');
  await expect(page.getByLabel('Option 2 name')).toBeFocused();
  await page.getByLabel('Option 2 name').fill('Park');
  await fits(page);
  // Live AI research is exercised separately; this journey uses fixed research results.
  const researchRuns = new Map<string, unknown>();
  await page.route('**/research*', async route => {
    const request = route.request();
    if (request.method() === 'GET') {
      const id = new URL(request.url()).searchParams.get('run')!;
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ run_id: id, status: 'completed', issues: [], research: researchRuns.get(id) }) });
    }
    const { task, input } = request.postDataJSON();
    const id = `00000000-0000-4000-8000-${String(researchRuns.size + 1).padStart(12, '0')}`;
    const options = input.options as { key: string; title: string }[];
    researchRuns.set(id, task === 'overviews' ? { options: options.map(o => ({ key: o.key, kind: 'place', place_id: null,
      overview: { source: 'web_search', name: o.title, summary: `${o.title} is a synthetic ${o.title === 'Cafe' ? 'indoor' : 'outdoor'} meeting spot.`, highlights: ['Synthetic fixture'], sources: [], photos: [] } })) }
      : task === 'questions' ? { questions: [{ title: 'Indoors or outdoors?', help: '', type: 'single', role: 'preference', criterion: 'environment', choices: ['indoor', 'outdoor'] }] }
      : { facts: options.map(o => ({ option: o.key, criterion: 'environment', value: o.title === 'Cafe' ? 'indoor' : 'outdoor', value_type:'category', unit:null, context:{qualifier:'exact',source_text:'Synthetic venue environment.'}, sources:[{url:'https://example.com/venue'}] })) });
    return route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ run_id: id, status: 'pending', issues: [] }) });
  });
  await page.getByRole('button', { name: 'Look them up' }).click();
  await activeStepFits(page);
  await expect(page.getByRole('heading', { name: 'Your options at a glance' })).toBeVisible();
  await expect(page.locator('.overview-card').first()).toContainText('synthetic indoor meeting spot');
  await expect(page.locator('.overview-card').nth(1)).toContainText('synthetic outdoor meeting spot');
  await capture(page, info.project.name, 'overview');
  await fits(page);
  await page.getByRole('button', { name: 'Draft questions' }).click();
  await activeStepFits(page);
  await expect(page.locator('.step-pill[aria-current="step"]')).toContainText('Questions');
  // Question drafting and sourced facts are separate; facts retain their own values.
  await expect(page.getByLabel('Question', { exact: true })).toHaveValue('Indoors or outdoors?');
  await page.reload();
  await expect(page.getByLabel('Question', { exact: true })).toHaveValue('Indoors or outdoors?');
  await page.getByLabel('Question', { exact: true }).fill('Required environment?');
  await page.getByRole('radio', { name: /^Requirement/ }).check();
  await capture(page, info.project.name, 'questions');
  await page.getByRole('button', { name: 'Review form' }).click();
  await activeStepFits(page);
  await expect(page.getByRole('heading', { name: 'Review and publish' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Review and publish' })).toBeVisible();
  await expect(page.getByText('Worth checking before you publish')).toHaveCount(0);
  // Recover from server data after discarding the tab-local creator checkpoint.
  await expect.poll(async()=>page.evaluate(async()=>{
    const user=sessionStorage.getItem('user_id');const saved=JSON.parse(sessionStorage.getItem(`what2do:checkpoint:v1:${user}:creator`)!);
    const response=await fetch(`/api/planning/v1/plans/details/${saved.form.id}`,{headers:{Authorization:`Bearer ${sessionStorage.getItem('session_token')}`}});
    const row=await response.json();return (row.proposed_activities || []).map((o:{metadata?:{facts?:{status?:string;context?:{verification?:string}}[]}})=>
      (o.metadata?.facts || []).map(f=>({status:f.status,verification:f.context?.verification})));
  })).toEqual([[{status:'confirmed',verification:'grounded_search'}],[{status:'confirmed',verification:'grounded_search'}]]);
  await page.evaluate(()=>sessionStorage.removeItem(`what2do:checkpoint:v1:${sessionStorage.getItem('user_id')}:creator`));
  await page.reload();
  await expect(page.getByRole('heading',{name:'Review and publish'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Supporting facts'})).toHaveCount(0);
  await fits(page);
  await page.route('**/v1/rounds/*/publish', route => route.fulfill({ status: 503, contentType: 'application/json',
    body: JSON.stringify({ code: 'UPSTREAM_UNAVAILABLE', message: 'Temporary test outage' }) }), { times: 1 });
  await page.getByRole('button', { name: 'Publish form' }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Your draft is saved.' })).toBeVisible();
  await page.reload();
  await page.getByRole('button', { name: 'Publish form' }).click();
  await expect(page.getByRole('heading', { name: 'Organiser controls' })).toBeVisible();
  expect(planCreates).toBe(1);
  const roundHash = new URL(page.url()).hash;
  await page.getByRole('link', { name: 'Skip to content' }).focus();
  await page.getByRole('link', { name: 'Skip to content' }).press('Enter');
  await expect(page.locator('main')).toBeFocused();
  expect(new URL(page.url()).hash).toBe(roundHash);
  await expect(page.getByText('Question 1 of 1')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Option facts' })).toHaveCount(0);
  await expect(page.locator('.option-cards')).toContainText('synthetic indoor meeting spot');
  await expect(page.getByRole('button', { name: 'Create invitation link' })).toBeEnabled();
  await page.getByRole('button', { name: 'Refresh status', exact: true }).focus();
  await capture(page, info.project.name, 'collecting');
  await fits(page);
  await page.getByRole('button', { name: 'Create invitation link' }).click();
  const share = await page.getByLabel('Invitation link').inputValue();
  const context = await browser.newContext({ viewport: page.viewportSize() || { width: 390, height: 844 } });
  const member = await context.newPage(); await member.goto(share); await invited(member, `${name} member`);
  // Members see what is being decided, with each option's facts, before the questions.
  await expect(member.getByRole('heading', { name: 'Where should we meet?', exact: true })).toBeVisible();
  await expect(member.getByText(name, { exact: true })).toBeVisible();
  await expect(member.locator('.option-cards')).toContainText('Cafe');
  await expect(member.locator('.option-cards')).toContainText('synthetic outdoor meeting spot');
  await expect(member.getByRole('heading', { name: 'Organiser controls' })).toHaveCount(0);
  await capture(member, info.project.name, 'invite-overview');
  await fits(member);
  await member.getByRole('button', { name: 'Start' }).click();
  for (const who of [page, member]) {
    await expect(who.getByRole('heading', { name: 'Required environment?' })).toBeVisible();
    await who.getByRole('button', { name: 'Next' }).click();
    await expect(who.getByRole('alert')).toContainText('Answer this question');
    await who.getByRole('radio', { name: 'indoor' }).check();
    await who.reload();
    await expect(who.getByRole('radio', { name: 'indoor' })).toBeChecked();
    await who.getByRole('button', { name: 'Next' }).click();
    await expect(who.getByRole('heading', { name: 'Anything else the organiser should know?' })).toBeVisible();
    await who.getByLabel('Private note').fill('Synthetic private note');
    await who.reload();
    await expect(who.getByLabel('Private note')).toHaveValue('Synthetic private note');
    await who.getByRole('button', { name: 'Review answers' }).click();
    await expect(who.getByRole('heading', { name: 'Review your answers' })).toBeVisible();
    await expect(who.locator('.answer-summary')).toContainText('indoor');
    if (who === page) await capture(who, info.project.name, 'review');
    await who.reload();
    await expect(who.getByRole('heading', { name: 'Review your answers' })).toBeVisible();
    await expect(who.locator('.answer-summary')).toContainText('indoor');
    await who.getByRole('button', { name: 'Submit response', exact: true }).click();
    await expect(who.getByRole('heading', { name: 'Your response is in' })).toBeVisible();
    await fits(who);
  }
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Close collection', exact: true }).click();
  await page.getByRole('button', { name: 'Calculate recommendation' }).click();
  await expect(page.getByRole('heading', { name: 'Recommended: Cafe' })).toBeVisible();
  await expect(page.getByText('Meets the requirements. No scored preferences were collected.')).toBeVisible();
  await capture(page, info.project.name, 'recommendation');
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Confirm Cafe', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Confirmed selection', exact: true })).toBeVisible();
  await expect(member.getByRole('heading', { name: 'Confirmed selection', exact: true })).toBeVisible();
  await member.getByRole('radio', { name: 'Going' }).check();
  await member.getByRole('button', { name: 'Save RSVP', exact: true }).click();
  await expect(member.getByRole('status').filter({ hasText: 'RSVP saved.' })).toBeVisible();
  await fits(page); await fits(member);
  await capture(member, info.project.name, 'rsvp');
  // Wait for the actual restored RSVP below, rather than unrelated page-load work.
  await member.reload({ waitUntil: 'domcontentloaded' });
  await expect(member.getByRole('radio', { name: 'Going' })).toBeChecked();
  await expect(member.getByRole('button', { name: 'Update RSVP' })).toBeDisabled();
  await page.getByRole('button', { name: 'My forms', exact: true }).click();
  await expect(page.getByRole('button', { name, exact: true })).toBeVisible();
  await fits(page);
  await expect(page.getByRole('cell', { name: /^(Category )?General$/ })).toBeVisible();
  await capture(page, info.project.name, 'dashboard');
  await page.getByLabel('Search forms').fill('No matching form fixture');
  await expect(page.getByRole('status')).toContainText('No forms match');
  await page.getByRole('button', { name: 'Clear filters' }).click();
  await page.getByLabel('Filter by status').selectOption('Confirmed');
  await expect(page.getByRole('button', { name, exact: true })).toBeVisible();
  await page.getByRole('button',{name,exact:true}).click();
  page.once('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:'Revise in a new round',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Review and publish'})).toBeVisible();
  await expect(page.getByTestId('fact-Cafe-environment')).toHaveCount(0);
  await page.getByRole('button',{name:/Overview$/}).click();
  await page.getByText('View or correct supporting facts',{exact:true}).click();
  await expect(page.getByTestId('fact-Cafe-environment').getByLabel('Fact value')).toHaveValue('indoor');
  await page.getByRole('button',{name:/Review$/}).click();
  await page.getByRole('button',{name:'Publish form',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Organiser controls'})).toBeVisible();
  await member.getByRole('button',{name:'My forms',exact:true}).click();
  await expect(member.getByRole('button',{name,exact:true})).toBeVisible();
  await member.getByRole('button',{name,exact:true}).click();
  await member.getByRole('button',{name:'Copy my earlier answers'}).click();
  await expect(member.getByText('Earlier answers copied as a draft.',{exact:false})).toBeVisible();
  // Reopening cannot change the earlier saved selection or attendance.
  await member.goto(`${new URL(member.url()).origin}/${roundHash}`);
  await expect(member.getByRole('heading',{name:'Confirmed selection',exact:true})).toBeVisible();
  await expect(member.getByRole('radio',{name:'Going',exact:true})).toBeChecked();
  await expect(member.getByRole('radio',{name:'Going',exact:true})).toBeDisabled();
  await context.close();
});

test('public browser proxy never exposes internal APIs', async ({ request }) => {
  for (const service of ['planning', 'participation']) {
    const response = await request.get(`/api/${service}/internal/metrics`);
    expect(response.status()).toBe(404);
  }
  const response = await request.get('/api/planning/v1/plans/organiser/00000000-0000-0000-0000-000000000000');
  expect(response.status()).toBe(401);
  expect(response.headers()['cache-control']).toBe('no-store');
});


test('dashboard recovery, long content and session details fit the viewport', async ({ page }, info) => {
  const longTitle = 'A'.repeat(255);
  let attempts = 0;
  await page.route('**/v1/plans/member/*', route => {
    attempts++;
    return route.fulfill(attempts === 1 ? {
      status: 503, contentType: 'application/json', body: JSON.stringify({ message: 'Synthetic outage' }),
    } : { status: 200, contentType: 'application/json', body: JSON.stringify([
      { id: '00000000-0000-0000-0000-000000000001', title: longTitle, plan_category: 'MEETING',
        state: 'COLLECTING', members_count: 30, organiser_name: 'Long name '.repeat(25) },
      { id: '00000000-0000-0000-0000-000000000002', title: 'A shared weekend plan', plan_category: 'GENERAL',
        state: 'DRAFT', members_count: 1, organiser_name: 'Organiser' },
    ]) });
  });
  await page.goto('/'); await guest(page, 'UI edge cases');
  await expect(page.getByRole('alert')).toContainText('Check that the system is running');
  await fits(page);
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByRole('button', { name: longTitle, exact: true })).toBeVisible();
  await expect(page.getByRole('cell', { name: /^(Category )?Work$/ })).toBeVisible();
  await fits(page);
  await capture(page, info.project.name, 'long-content');
  await page.getByText('Session details', { exact: true }).click();
  const box = await page.locator('.session-popover').boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
  await fits(page);
});
