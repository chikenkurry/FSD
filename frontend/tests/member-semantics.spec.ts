import { test, expect } from '@playwright/test';

test('written answers are saved in review summary and persist on submit without a blocking preview', async ({
  page,
}) => {
  const answer = 'I must stay below SGD 100; I prefer somewhere peaceful and Italian.';
  let revision = 0;
  let submitted = false;
  let savedAnswers: Record<string, unknown>[] = [];
  await page.addInitScript(() => {
    sessionStorage.setItem('user_id', 'member');
    sessionStorage.setItem('username', 'Member');
    sessionStorage.setItem('session_token', 'synthetic-semantic-token');
  });
  await page.route('**/api/**', async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const reply = (value: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    if (path.endsWith('/form'))
      return reply({
        plan_id: 'plan',
        round_id: 'round',
        interpretation_policy: 'facts-v1',
        option_revision: 1,
        currency: 'SGD',
        currency_minor_digits: 2,
        execution_mode: 'options',
        decision_question: 'Where should we eat?',
        questions: [
          {
            question_id: 'q',
            label: 'What matters to you?',
            role: 'soft',
            criterion: 'preferences',
            answer_format: 'text',
            required: true,
          },
        ],
        options: [
          {
            option_id: 'option-a',
            title: 'Venue A',
            facts: [{ criterion: 'atmosphere', value: 'calm', status: 'confirmed', source: 'Venue description' }],
          },
        ],
      });
    if (path.endsWith('/v1/plans/plan'))
      return reply({ id: 'plan', title: 'A semantic decision', created_by_user_id: 'owner', state: 'COLLECTING' });
    if (path.endsWith('/rounds/plans/plan')) return reply({ data: [{ id: 'round', round_number: 1 }] });
    if (path.endsWith('/my-response')) {
      if (req.method() === 'PUT') {
        const body = req.postDataJSON();
        expect(body.budget.kind).toBe('UNANSWERED');
        savedAnswers = body.answers;
        revision++;
      }
      return reply({
        revision,
        status: submitted ? 'SUBMITTED' : 'DRAFT',
        acknowledgedOptionRevision: 1,
        availability: [],
        budget: { kind: 'UNANSWERED' },
        activityAnswers: [],
        answers: savedAnswers,
        privateNote: null,
        round: { state: 'COLLECTING' },
      });
    }
    if (path.endsWith('/my-response/submit')) {
      submitted = true;
      return reply({
        revision: ++revision,
        status: 'SUBMITTED',
        acknowledgedOptionRevision: 1,
        availability: [],
        budget: { kind: 'UNANSWERED' },
        activityAnswers: [],
        answers: savedAnswers,
        privateNote: null,
        round: { state: 'COLLECTING' },
      });
    }
    return reply({});
  });
  await page.goto('/#round=round');
  await page.getByRole('button', { name: 'Start', exact: true }).click();
  await page.getByRole('textbox', { name: 'What matters to you?' }).fill(answer);
  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await page.getByRole('button', { name: 'Review answers', exact: true }).click();
  await expect(page.getByText('Checking how your answers will be read…')).toHaveCount(0);
  await expect(page.locator('.answer-summary')).toContainText(answer);
  await expect(page.getByRole('button', { name: 'Submit response', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Submit response', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your response is in' })).toBeVisible();
  expect(savedAnswers[0]?.value).toBe(answer);
});
