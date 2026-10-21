import { test, expect, type Page } from '@playwright/test';

async function setup(page: Page, emptyFit = false) {
  let holdOverviews = false;
  const posts = { overviews: 0, questions: 0, fit: 0, plans: 0 };
  const runs = new Map<string, { task: string; research: unknown }>();
  let serial = 0;
  await page.route('**/api/**', async route => {
    const req = route.request(); const path = new URL(req.url()).pathname;
    const body = req.method() === 'POST' || req.method() === 'PATCH' ? req.postDataJSON() : undefined;
    const reply = (data: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    if (path.endsWith('/v1/users')) return reply({ id: 'recovery-user', username: 'Recovery test', session_token: 'synthetic-recovery-token' });
    if (path.includes('/plans/organiser/')) return reply([]);
    if (path.endsWith('/research')) {
      if (req.method() === 'POST') {
        const task = body.task as 'overviews' | 'questions' | 'fit'; posts[task]++;
        const id = `run-${++serial}`;
        const options = body.input.options as { key: string; title: string }[];
        const research = task === 'overviews' ? { options: options.map(o => ({ key: o.key, kind: 'other', place_id: null, overview: { source: 'web_search', summary: `${o.title} verified description`, sources: [], highlights: [] } })) }
          : task === 'questions' ? { questions: [{ title: 'What atmosphere do you prefer?', help: '', type: 'single', role: 'preference', criterion: 'atmosphere', choices: ['Quiet', 'Lively'] }] }
          : { facts: emptyFit && posts.fit === 1 ? [] : options.map(o => ({ option: o.key, criterion: 'atmosphere', values: ['Quiet'], reason: 'Synthetic evidence', sources: [] })) };
        runs.set(id, { task, research }); return reply({ run_id: id, status: 'pending', issues: [] }, 202);
      }
      const id = new URL(req.url()).searchParams.get('run')!;
      const run = runs.get(id)!;
      return reply({ run_id: id, status: run.task === 'overviews' && holdOverviews ? 'pending' : 'completed', issues: [], research: run.research });
    }
    if (path.endsWith('/v1/plans') && req.method() === 'POST') { posts.plans++; return reply({ id: 'saved-plan' }); }
    if (path.includes('/proposed_activity/plans/')) return reply({ id: `option-${++serial}` });
    if (path.endsWith('/v1/question') && req.method() === 'POST') return reply({ id: `question-${++serial}` });
    if (path.includes('/rounds/plans/')) return reply({ id: 'saved-round' });
    return reply({});
  });
  await page.goto('/');
  await page.getByLabel('Your display name').fill('Recovery test');
  await page.getByRole('button', { name: 'Create guest session' }).click();
  await page.getByRole('button', { name: 'Create form', exact: true }).first().click();
  return { posts, hold: (value: boolean) => { holdOverviews = value; } };
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

test('creator resumes every step and pending research without duplicate plans or jobs', async ({ page }) => {
  const fixture = await setup(page);
  await basics(page);
  await page.reload();
  await expect(page.getByLabel('Option 1 name')).toHaveValue('Restaurant A');
  fixture.hold(true);
  await page.getByRole('button', { name: 'Look them up' }).click();
  await expect.poll(() => fixture.posts.overviews).toBe(2);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Your options at a glance' })).toBeVisible();
  fixture.hold(false);
  await expect(page.locator('.overview-card').first()).toContainText('verified description');
  expect(fixture.posts.overviews).toBe(2);
  expect(fixture.posts.plans).toBe(1);
  await page.getByRole('button', { name: 'Draft questions' }).click();
  await expect(page.getByLabel('Question', { exact: true })).toHaveValue('What atmosphere do you prefer?');
  await page.getByLabel('Help text').fill('Keep this edit');
  await page.reload();
  await expect(page.getByLabel('Help text')).toHaveValue('Keep this edit');
  expect(fixture.posts.questions).toBe(1);
  await page.getByRole('button', { name: 'Review form' }).click();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Review and publish' })).toBeVisible();
  await expect(page.getByText('Worth checking before you publish')).toHaveCount(0);
  const restored = await page.evaluate(() => JSON.parse(sessionStorage.getItem('what2do:checkpoint:v1:recovery-user:creator')!));
  expect(restored.form.id).toBe('saved-plan');
  expect(restored.form.roundId).toBe('saved-round');
  expect(restored.form.decisionOptions[0].overview).toBeUndefined();
  expect(restored.form.decisionOptions[0].brief.summary).toContain('verified description');
  expect(fixture.posts.plans).toBe(1);
});

test('missing comparisons explain the evidence gap and can be retried', async ({ page }) => {
  const fixture = await setup(page, true);
  await basics(page);
  await page.getByRole('button', { name: 'Look them up' }).click();
  await expect(page.locator('.overview-card').first()).toContainText('verified description');
  await page.getByRole('button', { name: 'Draft questions' }).click();
  await expect.poll(() => fixture.posts.fit).toBe(1);
  // Visit review directly after the first fit finishes to exercise the explicit retry action.
  await expect.poll(async () => page.evaluate(() => {
    const row = JSON.parse(sessionStorage.getItem('what2do:checkpoint:v1:recovery-user:creator')!);
    return row.form.questions.length;
  })).toBe(1);
  await page.getByRole('button', { name: /^5\s*Review$/ }).click();
  await expect(page.getByText('Worth checking before you publish')).toBeVisible();
  await expect(page.getByText(/Ranking may be blocked/)).toBeVisible();
  await expect(page.getByText(/won’t affect those options/)).toHaveCount(0);
  await page.getByRole('button', { name: 'Retry missing comparisons' }).click();
  await expect(page.getByText('Worth checking before you publish')).toHaveCount(0);
  expect(fixture.posts.fit).toBe(2);
});


test('storage failure is visible instead of promising refresh recovery', async ({ page }) => {
  await page.addInitScript(() => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      if (key.startsWith('what2do:checkpoint:')) throw new DOMException('Synthetic full storage', 'QuotaExceededError');
      return original.call(this, key, value);
    };
  });
  await setup(page);
  await page.getByLabel('Plan name').fill('Unsaved browser edit');
  await expect(page.getByRole('alert')).toContainText('Browser storage is unavailable');
});
