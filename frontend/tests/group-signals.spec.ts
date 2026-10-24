import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { guest, inviteLink, join, mockResearch, newPerson, pick, publishForm, submitFromReview } from './support/stack';

// The flow builds its own desktop and phone contexts, so one project is enough.
test.beforeEach(({}, info) => test.skip(info.project.name !== 'desktop', 'Runs its own desktop and phone contexts'));

const day = (iso: string) => new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' });

test('ratings, importance, weights, deadline, early close, fact re-check and a dated confirmation', { tag: '@stack' }, async ({ browser }) => {
  test.setTimeout(240_000);
  const name = `Group signals ${Date.now()}`;
  const organiser = await newPerson(browser);
  const page = organiser.page;
  const research = await mockResearch(page, { questionWeight: 'more', closedOnPlanDates: ['Park'] });
  await guest(page, 'Olivia');

  await test.step('AI weight suggestion is pre-filled and the organiser can keep it', async () => {
    await publishForm(page, { name, research, ratings: true, datePoll: true, deadline: '2030-01-15T18:00', beforeReview: async () => {
      const cards = page.locator('.question-card');
      await expect(cards.nth(0).getByText('AI suggested “More” for this decision.')).toBeVisible();
      await expect(cards.nth(0).getByRole('radio', { name: 'More' })).toBeChecked();
      await expect(cards.nth(1).getByRole('radio', { name: 'Normal' })).toBeChecked();
      await expect(cards.nth(2)).toContainText('This picks when');
      await expect(cards.nth(2).getByLabel('Date option 1')).toHaveValue('2027-06-01');
    } });
    await expect(page.locator('.deadline-value')).toContainText('15 Jan');
  });

  await test.step('organiser answers: indoors, neutral ratings, dates', async () => {
    await page.getByRole('radio', { name: 'indoor' }).check();
    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.getByRole('alert')).toContainText('Rate every option');
    await pick(page, 'Cafe', 'Fine'); await pick(page, 'Park', 'Fine');
    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.getByRole('alert')).toContainText('Answer every date');
    await pick(page, day('2027-06-01'), 'Can’t'); await pick(page, day('2027-06-02'), 'Works'); await pick(page, day('2027-06-03'), 'If needed');
    await page.getByRole('button', { name: 'Next' }).click();
    await submitFromReview(page);
  });

  const share = await inviteLink(page);
  const member = await newPerson(browser, { width: 390, height: 844 });
  await test.step('a member on a phone sees the deadline and answers with importance', async () => {
    await join(member.page, share, 'Mei');
    await expect(member.page.locator('.due')).toContainText('Answers due');
    await member.page.getByRole('button', { name: 'Start' }).click();
    await member.page.getByRole('radio', { name: 'outdoor' }).check();
    await member.page.getByRole('radio', { name: 'A lot' }).check();
    await member.page.getByRole('button', { name: 'Next' }).click();
    await pick(member.page, 'Cafe', 'Meh'); await pick(member.page, 'Park', 'Love it');
    await member.page.getByRole('button', { name: 'Next' }).click();
    await pick(member.page, day('2027-06-01'), 'Works'); await pick(member.page, day('2027-06-02'), 'Works'); await pick(member.page, day('2027-06-03'), 'Can’t');
    await member.page.getByRole('button', { name: 'Next' }).click();
    await submitFromReview(member.page);
  });

  const silent = await newPerson(browser);
  await join(silent.page, share, 'Sam');
  await expect(silent.page.getByRole('button', { name: 'Start' })).toBeVisible();

  await test.step('organiser reminds the silent member and closes early', async () => {
    await page.getByRole('button', { name: 'Refresh status', exact: true }).click();
    await page.getByRole('button', { name: 'Remind Sam' }).click();
    await expect(page.getByRole('button', { name: 'Reminder copied' })).toBeVisible();
    const reminder = await page.evaluate(() => navigator.clipboard.readText());
    expect(reminder).toContain(name);
    expect(reminder).toContain('invite=');
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: 'Close with 2 of 3 responses' }).click();
    await page.getByRole('button', { name: 'Calculate recommendation' }).click();
  });

  await test.step('ratings, importance and weights decide the ranking', async () => {
    await expect(page.getByRole('heading', { name: 'Recommended: Park' })).toBeVisible({ timeout: 120_000 });
    await expect(page.getByText('1 member hadn’t responded when collection closed')).toBeVisible();
    // Environment counts "More" (2/3) vs ratings (1/3); Mei's "A lot" doubles her environment weight.
    await expect(page.locator('.board-rows li').nth(0)).toContainText('58%');
    await expect(page.locator('.board-rows li').nth(1)).toContainText('5%');
    await expect(page.locator('.attr-reason').filter({ hasText: 'judged by AI' })).toHaveCount(0);
  });

  await test.step('the fact re-check flags a closure on the plan dates', async () => {
    await page.getByRole('button', { name: 'Check top options' }).click();
    await expect(page.locator('.recheck-results')).toContainText('May be closed then');
  });

  await test.step('the date poll picks the best date and the organiser confirms with a time', async () => {
    await expect(page.locator('.date-poll-result')).toContainText(`Best: ${day('2027-06-02')}`);
    await page.getByRole('button', { name: 'Confirm Park', exact: true }).click();
    await expect(page.getByRole('combobox', { name: 'Date', exact: true })).toHaveValue('2027-06-02');
    await page.getByLabel('Start time').fill('19:00');
    await page.getByRole('button', { name: `Confirm for ${day('2027-06-02')}` }).click();
    await expect(page.getByRole('heading', { name: 'Confirmed selection', exact: true })).toBeVisible();
    await expect(page.locator('.event-when')).toContainText('2 June');
  });

  await test.step('members see the date and get a calendar file for it', async () => {
    await member.page.reload();
    await expect(member.page.locator('.event-when')).toContainText('2 June');
    const download = member.page.waitForEvent('download');
    await member.page.getByRole('button', { name: 'Calendar (.ics)' }).click();
    const ics = await readFile(await (await download).path(), 'utf8');
    expect(ics).toContain('DTSTART:20270602T110000Z'); // 19:00 in Singapore
    expect(ics).toContain('SUMMARY:');
  });

  await Promise.all([organiser.context.close(), member.context.close(), silent.context.close()]);
});
