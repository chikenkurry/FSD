import { test, expect } from '@playwright/test';
import { guest, inviteLink, join, mockResearch, newPerson, publishForm, submitFromReview } from './support/stack';

test.beforeEach(({}, info) => test.skip(info.project.name !== 'desktop', 'Runs its own browser contexts'));

test('members return as themselves: same device, return link on another device, and sign-out everywhere', { tag: '@stack' }, async ({ browser }) => {
  test.setTimeout(180_000);
  const organiser = await newPerson(browser);
  const research = await mockResearch(organiser.page);
  await guest(organiser.page, 'Olivia');
  await publishForm(organiser.page, { name: `Returning ${Date.now()}`, research });
  const share = await inviteLink(organiser.page);

  const member = await newPerson(browser, { width: 390, height: 844 });
  await test.step('member answers, then copies their return link', async () => {
    await join(member.page, share, 'Mei');
    await member.page.getByRole('button', { name: 'Start' }).click();
    await member.page.getByRole('radio', { name: 'outdoor' }).check();
    await member.page.getByRole('button', { name: 'Next' }).click();
    await submitFromReview(member.page);
  });
  await member.page.getByRole('button', { name: 'Copy my return link' }).click();
  await expect(member.page.getByRole('button', { name: 'Return link copied' })).toBeVisible();
  const returnLink = await member.page.evaluate(() => navigator.clipboard.readText());
  expect(returnLink).toContain('resume=');

  await test.step('closing the tab and reopening the invitation keeps the same person', async () => {
    await member.page.close();
    const again = await member.context.newPage();
    await again.goto(share);
    await expect(again.getByRole('heading', { name: 'Your response is in' })).toBeVisible();
    await expect(again.getByRole('heading', { name: 'Help your group decide' })).toHaveCount(0);
    await organiser.page.getByRole('button', { name: 'Refresh status', exact: true }).click();
    await expect(organiser.page.locator('.collect-figure')).toContainText('/2'); // Olivia and Mei, not a duplicate Mei
  });

  await test.step('the return link signs the member in on another device', async () => {
    const laptop = await newPerson(browser);
    await laptop.page.goto(returnLink);
    await expect(laptop.page.getByRole('heading', { name: 'Your response is in' })).toBeVisible();
    expect(laptop.page.url()).not.toContain('resume=');
    await laptop.context.close();
  });

  await test.step('signing out in one tab signs out the others on that device', async () => {
    const first = member.context.pages()[0]!;
    const second = await member.context.newPage();
    await second.goto('/');
    await expect(second.getByRole('button', { name: 'My forms', exact: true })).toBeVisible();
    await first.getByRole('button', { name: 'Sign out' }).click();
    await expect(first.getByRole('heading', { name: 'Help your group decide' }).or(first.getByLabel('Your display name'))).toBeVisible();
    await expect(second.getByLabel('Your display name')).toBeVisible();
  });

  await Promise.all([organiser.context.close(), member.context.close()]);
});
