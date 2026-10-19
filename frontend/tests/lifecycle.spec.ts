import { test, expect, type Page } from '@playwright/test';

async function fits(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
}
async function guest(page: Page, name: string) {
  await page.getByLabel('Your display name').fill(name);
  await page.getByRole('button', { name: 'Create guest session', exact: true }).click();
  await expect(page.getByRole('button', { name: 'My forms', exact: true })).toBeVisible();
}

test('create, invite, privately review, submit, rank, confirm and RSVP', async ({ page, browser }, info) => {
  const name = `Browser ${info.project.name} ${Date.now()}`;
  await page.goto('/'); await fits(page); await guest(page, name);
  await page.getByRole('button', { name: 'Create form', exact: true }).first().click();
  await page.getByPlaceholder('eg. Europe Summer Trip 2026').fill(name);
  await page.getByRole('button', { name: 'Next Step' }).click();
  await page.locator('.step-card select').selectOption('General');
  await page.getByRole('button', { name: 'Next Step' }).click();
  await page.locator('input[type=date]').nth(0).fill('2027-06-01');
  await page.locator('input[type=date]').nth(1).fill('2027-06-03');
  await page.getByRole('button', { name: 'Next Step' }).click();
  await page.getByPlaceholder('eg, Zoom, Botanic Gardens').fill('Group choice');
  await page.getByRole('button', { name: 'Proceed to questions' }).click();
  await fits(page);
  for (const [index, [title, environment]] of [['Cafe', 'indoor'], ['Park', 'outdoor']].entries()) {
    const option = page.locator('.option-editor article').nth(index);
    await option.getByLabel('Option name').fill(title!);
    await option.getByRole('button', { name: 'Add fact' }).click();
    await option.getByLabel('Criterion', { exact: true }).fill('environment');
    await option.getByLabel('Value', { exact: true }).fill(environment!);
    await option.getByLabel('Source', { exact: true }).fill('Synthetic browser fixture');
  }
  await page.getByPlaceholder('Question title').fill('Required environment?');
  await page.locator('.question-controls select').selectOption('Single choice');
  await page.getByLabel('How this answer is used').selectOption('hard');
  await page.getByLabel('Criterion name').fill('environment');
  await page.locator('.options-container input[type=text]').first().fill('indoor');
  await page.locator('.question-card').getByRole('button', { name: /Add option/ }).click();
  await page.locator('.options-container input[type=text]').nth(1).fill('outdoor');
  let planCreates = 0;
  page.on('request', req => { if (req.method() === 'POST' && req.url().endsWith('/v1/plans')) planCreates++; });
  await page.route('**/v1/rounds/*/publish', route => route.fulfill({ status: 503, contentType: 'application/json',
    body: JSON.stringify({ code: 'UPSTREAM_UNAVAILABLE', message: 'Temporary test outage' }) }), { times: 1 });
  await page.getByRole('button', { name: 'Save & Publish Form' }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Your saved draft is retained' })).toBeVisible();
  await page.getByRole('button', { name: 'Save & Publish Form' }).click();
  await expect(page.getByRole('heading', { name: 'Organiser controls' })).toBeVisible();
  expect(planCreates).toBe(1);
  await fits(page);
  await page.getByRole('button', { name: 'Create invitation link' }).click();
  const share = await page.getByLabel('Invitation link').inputValue();
  const context = await browser.newContext({ viewport: page.viewportSize() || { width: 390, height: 844 } });
  const member = await context.newPage(); await member.goto(share); await guest(member, `${name} member`);
  await expect(member.getByRole('heading', { name: 'Your response' })).toBeVisible();
  await expect(member.getByRole('heading', { name: 'Organiser controls' })).toHaveCount(0);
  for (const who of [page, member]) {
    await who.getByLabel('Required environment?').selectOption('indoor');
    await who.getByRole('button', { name: 'Save & review interpretation' }).click();
    await expect(who.getByRole('heading', { name: 'Your private interpretation' })).toBeVisible();
    await who.getByLabel('I reviewed these requirements').check();
    await who.getByRole('button', { name: 'Submit response', exact: true }).click();
    await expect(who.getByRole('status')).toContainText('Response submitted.');
    await fits(who);
  }
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Close collection', exact: true }).click();
  await page.getByRole('button', { name: 'Calculate recommendation' }).click();
  await expect(page.getByRole('heading', { name: 'Recommended: Cafe' })).toBeVisible();
  await expect(page.getByText('Meets the requirements. No scored preferences were collected.')).toBeVisible();
  await page.getByRole('button', { name: 'Confirm Cafe', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Confirmed selection', exact: true })).toBeVisible();
  await member.getByRole('button', { name: 'Refresh status', exact: true }).click();
  await expect(member.getByRole('heading', { name: 'Confirmed selection', exact: true })).toBeVisible();
  await member.getByLabel('Your RSVP').selectOption('GOING');
  await member.getByRole('button', { name: 'Save RSVP', exact: true }).click();
  await expect(member.getByRole('status').filter({ hasText: 'RSVP saved.' })).toBeVisible();
  await fits(page); await fits(member);
  // Wait for the actual restored RSVP below, rather than unrelated page-load work.
  await member.reload({ waitUntil: 'domcontentloaded' });
  await expect(member.getByLabel('Your RSVP')).toHaveValue('GOING');
  await page.getByRole('button', { name: 'My forms', exact: true }).click();
  await expect(page.getByRole('button', { name, exact: true })).toBeVisible();
  await fits(page);
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
