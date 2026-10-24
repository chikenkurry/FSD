// Helpers for full-stack specs (tagged @stack). They drive the real Planning,
// Participation and Decision services; only third-party research is mocked.
import { expect, type Browser, type BrowserContext, type Page } from '@playwright/test';

export const STACK_URL = process.env.FRONTEND_URL || 'http://127.0.0.1:15173';

export async function newPerson(browser: Browser, viewport = { width: 1440, height: 900 }): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ viewport, timezoneId: 'Asia/Singapore', locale: 'en-GB', baseURL: STACK_URL });
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: new URL(STACK_URL).origin });
  return { context, page: await context.newPage() };
}

export async function guest(page: Page, name: string) {
  await page.goto('/');
  await page.getByLabel('Your display name').fill(name);
  await page.getByRole('button', { name: 'Create guest session', exact: true }).click();
  await expect(page.getByRole('button', { name: 'My forms', exact: true })).toBeVisible();
}

/** Research (web search and AI drafting) is the only external dependency; it returns fixed results. */
export async function mockResearch(page: Page, options: { questionWeight?: 'less' | 'normal' | 'more'; closedOnPlanDates?: string[] } = {}) {
  const runs = new Map<string, unknown>();
  let factsServed = 0;
  await page.route('**/research*', async route => {
    const request = route.request();
    if (request.method() === 'GET') {
      const id = new URL(request.url()).searchParams.get('run')!;
      if ((runs.get(id) as { facts?: unknown })?.facts) factsServed++;
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ run_id: id, status: 'completed', issues: [], research: runs.get(id) }) });
    }
    const { task, input } = request.postDataJSON();
    const id = `00000000-0000-4000-8000-${String(runs.size + 1).padStart(12, '0')}`;
    const items = input.options as { key: string; title: string }[];
    const environment = (title: string) => (title === 'Cafe' ? 'indoor' : 'outdoor');
    runs.set(id, task === 'overviews'
      ? { options: items.map(o => ({ key: o.key, kind: 'place', place_id: null, overview: { source: 'web_search', name: o.title,
          summary: `${o.title} is a synthetic ${environment(o.title)} meeting spot.`, highlights: ['Synthetic fixture'], sources: [], photos: [] } })) }
      : task === 'questions'
        ? { questions: [{ title: 'Indoors or outdoors?', help: '', type: 'single', role: 'preference', criterion: 'environment',
            choices: ['indoor', 'outdoor'], ...(options.questionWeight ? { weight: options.questionWeight } : {}) }] }
        : { facts: items.flatMap(o => (input.attributes as { criterion: string }[]).map(a => a.criterion === 'open_on_plan_dates'
            ? { option: o.key, criterion: a.criterion, value: !(options.closedOnPlanDates || []).includes(o.title), value_type: 'boolean', unit: null,
                context: { qualifier: 'exact', source_text: 'Synthetic opening hours.' }, sources: [{ url: 'https://example.com/hours', title: 'Opening hours' }] }
            : { option: o.key, criterion: 'environment', value: environment(o.title), value_type: 'category', unit: null,
                context: { qualifier: 'exact', source_text: 'Synthetic venue environment.' }, sources: [{ url: 'https://example.com/venue' }] })) });
    return route.fulfill({ status: 202, contentType: 'application/json', body: JSON.stringify({ run_id: id, status: 'pending', issues: [] }) });
  });
  return { factsServed: () => factsServed };
}

export interface FormSetup { name: string; ratings?: boolean; datePoll?: boolean; deadline?: string; beforeReview?: (page: Page) => Promise<void>; research?: { factsServed: () => number } }

/** Creates and publishes a two-option form (Cafe indoors, Park outdoors) from the organiser's page. */
export async function publishForm(page: Page, setup: FormSetup) {
  await page.getByRole('button', { name: 'Create form', exact: true }).first().click();
  await page.getByLabel('Plan name').fill(setup.name);
  await page.getByRole('radio', { name: /^General/ }).check();
  await page.locator('input[type=date]').nth(0).fill('2027-06-01');
  await page.locator('input[type=date]').nth(1).fill('2027-06-03');
  await page.getByLabel('Location or platform').fill('Singapore');
  await page.getByRole('button', { name: 'Next step' }).click();
  await page.getByLabel('Option 1 name').fill('Cafe');
  await page.getByLabel('Option 2 name').fill('Park');
  await page.getByRole('button', { name: 'Look them up' }).click();
  await expect(page.locator('.overview-card').nth(1)).toContainText('synthetic outdoor');
  await page.getByRole('button', { name: 'Draft questions' }).click();
  await expect(page.getByLabel('Question', { exact: true })).toHaveValue('Indoors or outdoors?');
  if (setup.ratings) await page.getByRole('button', { name: 'Ask them to rate each option' }).click();
  if (setup.datePoll) await page.getByRole('button', { name: 'Ask which dates work' }).click();
  await setup.beforeReview?.(page);
  // Publish only after the option facts have been looked up, so ranking never falls back to live web research.
  if (setup.research) await expect.poll(setup.research.factsServed, { timeout: 30_000 }).toBeGreaterThan(0);
  await page.getByRole('button', { name: 'Review form' }).click();
  if (setup.deadline) await page.getByLabel('Collect answers until').fill(setup.deadline);
  await page.getByRole('button', { name: 'Publish form' }).click();
  await expect(page.getByRole('heading', { name: 'Organiser controls' })).toBeVisible();
}

export async function inviteLink(page: Page) {
  await page.getByRole('button', { name: 'Create invitation link' }).click();
  return page.getByLabel('Invitation link').inputValue();
}

export async function join(page: Page, link: string, name: string) {
  await page.goto(link);
  await expect(page.getByRole('heading', { name: 'Help your group decide' })).toBeVisible();
  await page.getByLabel('Your name').fill(name);
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
}

/** Picks one segment of a labelled radio group, e.g. rate(page, 'Park', 'Love it'). */
export async function pick(page: Page, group: string, label: string) {
  await page.getByRole('radiogroup', { name: group }).getByText(label, { exact: true }).click();
}

export async function submitFromReview(page: Page) {
  await page.getByRole('button', { name: 'Review answers' }).click();
  await page.getByRole('button', { name: 'Submit response', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your response is in' })).toBeVisible();
}
