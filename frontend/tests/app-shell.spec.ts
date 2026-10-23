import { test, expect, type Page } from '@playwright/test';

// UI-only: every API call is answered here, so this runs without the services.
async function mockApi(page: Page) {
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname;
    const reply = (value: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    if (path.includes('/plans/member/')) return reply([]);
    if (path.endsWith('/v1/users/remembered-user')) return reply({ id: 'remembered-user', username: 'Rosa' });
    if (path.endsWith('/v1/users')) return reply({ id: 'new-user', username: 'Nia', session_token: 'synthetic-token' });
    return reply({});
  });
}
const signedIn = (page: Page, name = 'Rosa') => page.addInitScript(([user]) => {
  sessionStorage.setItem('user_id', 'remembered-user'); sessionStorage.setItem('username', user!); sessionStorage.setItem('session_token', 'synthetic-token');
}, [name]);

test('landing offers start and join, and rejects links that are not invitations', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Different preferences/ })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Start a plan' })).toHaveAttribute('aria-selected', 'true');
  await page.getByRole('tab', { name: 'Join with a link' }).click();
  await page.getByLabel('Paste your invitation link').fill('https://example.com/not-an-invite');
  await page.getByRole('button', { name: 'Open invitation' }).click();
  await expect(page.getByText('doesn’t look like an invitation link')).toBeVisible();
  await page.getByLabel('Paste your invitation link').fill('http://localhost/#round=r-1&invite=t-1');
  await page.getByRole('button', { name: 'Open invitation' }).click();
  await expect(page.getByRole('heading', { name: 'Help your group decide' })).toBeVisible();
  expect(new URL(page.url()).hash).toBe('#round=r-1&invite=t-1');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
});

test('a session is remembered on this device after the tab closes', async ({ page, context }) => {
  await mockApi(page);
  await page.goto('/');
  await page.getByLabel('Your display name').fill('Nia');
  await page.getByRole('button', { name: 'Create guest session', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'What would you like to decide?' })).toBeVisible();
  await page.close();
  const reopened = await context.newPage();
  await mockApi(reopened);
  await reopened.goto('/');
  await expect(reopened.getByRole('button', { name: 'My forms', exact: true })).toBeVisible();
  expect(await reopened.evaluate(() => sessionStorage.getItem('username'))).toBe('Nia');
});

test('a return link signs in and is removed from the address bar', async ({ page }) => {
  await mockApi(page);
  const link = Buffer.from(JSON.stringify({ u: 'remembered-user', t: 'synthetic-token' })).toString('base64url');
  await page.goto(`/#resume=${link}`);
  await expect(page.getByRole('button', { name: 'My forms', exact: true })).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('username'))).toBe('Rosa');
  expect(page.url()).not.toContain('resume=');
});

test('sidebar collapses, remembers it, and the join dialog validates links', async ({ page }, info) => {
  test.skip(info.project.name !== 'desktop', 'The collapsible rail is a desktop layout; phones use a tab bar');
  await mockApi(page); await signedIn(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Collapse sidebar' }).click();
  await expect(page.locator('.shell')).toHaveClass(/collapsed/);
  await page.reload();
  await expect(page.locator('.shell')).toHaveClass(/collapsed/);
  await expect(page.getByRole('button', { name: 'My forms', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Expand sidebar' }).click();
  await page.getByRole('button', { name: 'Join with a link', exact: true }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Join a plan' });
  await dialog.getByLabel('Paste the invitation link').fill('nonsense');
  await dialog.getByRole('button', { name: 'Open invitation' }).click();
  await expect(dialog.getByText('doesn’t look like an invitation link')).toBeVisible();
  await dialog.getByRole('button', { name: 'Close' }).click();
  await expect(dialog).toHaveCount(0);
});

test('phones get a bottom tab bar that fits the screen', async ({ page }, info) => {
  test.skip(info.project.name === 'desktop', 'Phone layout only');
  await mockApi(page); await signedIn(page);
  await page.goto('/');
  const tabs = page.getByRole('navigation', { name: 'Main navigation' });
  await expect(tabs.getByRole('button', { name: 'My forms' })).toBeVisible();
  const box = (await tabs.boundingBox())!;
  expect(box.y + box.height).toBeLessThanOrEqual(page.viewportSize()!.height + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
});
