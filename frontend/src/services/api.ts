import { checkpointKey, readCheckpoint, writeCheckpoint, removeCheckpoint } from './checkpoints';
import type { Form, PlanRow, Question, Session, Snapshot, Round, Draft, Review, Run, Selection, DecisionOption, Fact, PublishedFact, FactCollectionRun, Overview, ResearchRun } from '@/types/form';

// Same-origin proxies keep private service addresses and tokens off browser URLs.
const planning = '/api/planning';
const participation = '/api/participation';
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}
export async function request<T>(path: string, method = 'GET', body?: unknown, token = sessionStorage.getItem('session_token') || ''): Promise<T> {
  const response = await fetch(path, {
    method, cache: 'no-store', headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(30000),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, data.code || 'REQUEST_FAILED', data.message || data.error || `Request failed (${response.status})`);
  return data as T;
}
const roundPath = (id: string) => `${planning}/v1/rounds/${encodeURIComponent(id)}`;
const ownPath = (id: string) => `${participation}/rounds/${encodeURIComponent(id)}/my-response`;
export function questionDefinition(q: Question, index: number) {
  const criterion = q.criterion?.trim() || `preference_${index + 1}`;
  const role = q.role || 'soft';
  const format = q.type === 'Multiple choice' ? 'multi_choice' : q.type === 'Number' ? 'number' : q.type === 'Boolean' ? 'boolean' :
    q.type === 'Duration' ? 'date_intervals' : ['Single choice', 'Location', 'Budget'].includes(q.type) ? 'choice' : 'text';
  // Cost compares exact currency amounts and a requirement means "at most"; other numbers are plain numbers.
  const isCost = criterion === 'max_cost';
  const valueType = q.type === 'Multiple choice' ? 'tag_set' : q.type === 'Number' ? (isCost ? 'decimal' : 'number') : q.type === 'Boolean' ? 'boolean' : 'category';
  const decision: Record<string, unknown> = { role, criterion: role === 'informational' ? 'context' : criterion, relevance: role === 'soft' ? 1 : 0, answer_format: format };
  if (role !== 'informational') {
    decision.mapping = { value_type: valueType, ...(q.unit ? { unit: q.unit } : {}),
      comparison_rule: role === 'hard' ? (valueType === 'tag_set' ? 'contains_all_v1' : isCost ? 'maximum_v1' : 'equals_v1') :
        valueType === 'tag_set' ? 'tag_overlap_v1' : q.type === 'Number' ? 'numeric_target_v1' : 'attribute_match_v1',
      ...(q.type === 'Number' && role === 'soft' ? { scale: q.scale || 1 } : {}) };
    if (q.type === 'Number' && role === 'soft') decision.numeric_intent = 'target';
  }
  return decision;
}
function validateForm(form: Form, draft = false) {
  if (!form.title.trim() || !form.category) throw new Error('Add a title and category.');
  if ((form.decisionQuestion?.trim().length || 0) > 300) throw new Error('Keep the decision question under 300 characters.');
  if (!form.decisionOptions?.length || form.decisionOptions.length > 8 || form.decisionOptions.some(o => !o.title.trim())) throw new Error('Add 1–8 named options.');
  // Drafts saved for fact finding come before the questions are written.
  if ((!draft && !form.questions.length) || form.questions.some(q => !q.title.trim())) throw new Error('Name each question.');
  if (form.questions.some(q => q.type === 'Duration' && q.role !== 'informational')) throw new Error('Date availability requires scenario or scheduled setup. Use an informational date question in this option form.');
  if (form.questions.some(q => q.type === 'Number' && q.role !== 'hard' && q.role !== 'informational' && !(Number(q.scale) > 0))) throw new Error('Numeric preferences need a positive tolerance.');
  // Facts left blank are an unfilled checklist, not an error; they are not saved.
  for (const option of form.decisionOptions) for (const fact of option.facts.filter(f => f.value.trim())) {
    if (!/^[a-z][a-z0-9_]{0,99}$/.test(fact.criterion.trim())) throw new Error('Give each fact a criterion name using lowercase letters, numbers and underscores.');
    if (fact.valueType === 'number' && !Number.isFinite(Number(fact.value))) throw new Error('Numeric facts need a finite number.');
  }
}
function publishSettings(form: Form) {
  const question = form.decisionQuestion?.trim();
  return { currency: form.currency || 'SGD', currency_minor_digits: 2, cost_scope: 'per_person_total',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, execution_mode: 'options', ...(question ? { decision_question: question } : {}) };
}
// The collector searches for this identity; acceptance rejects claims if it changes afterwards.
export function optionIdentity(option: DecisionOption, form: Form) {
  const link = option.identity?.source_url?.trim();
  const { place_id, kind } = option.identity || {};
  return { model_id: option.title.trim(), ...(form.location.trim() ? { region: form.location.trim() } : {}), ...(link ? { source_url: link } : {}),
    ...(place_id ? { place_id } : {}), ...(kind ? { kind } : {}) };
}
function optionMetadata(option: DecisionOption, form: Form) {
  const facts = option.facts.filter(f => f.value.trim()).map(f => ({ criterion: f.criterion.trim(), value_type: f.valueType,
    value: f.valueType === 'number' ? Number(f.value) : f.valueType === 'boolean' ? f.value === 'true' : f.valueType === 'tag_set' ? f.value.split(',').map(x => x.trim()).filter(Boolean) : f.value,
    ...(f.unit ? { unit: f.unit } : {}),
    ...(f.context || f.criterion === 'max_cost' ? { context: { ...f.context, ...(f.criterion === 'max_cost' ? { scope: 'per_person_total' } : {}) } } : {}),
    status: 'confirmed', source: f.source || 'Organiser supplied' }));
  // The summary is stored as the option description so members see it; place content is not.
  return { identity: optionIdentity(option, form), facts, ...(option.brief ? { brief: option.brief } : {}) };
}
export function localFact(row: PublishedFact): Fact {
  const value = Array.isArray(row.value) ? row.value.join(', ') : String(row.value ?? '');
  return { criterion: row.criterion, value, valueType: (row.value_type || 'category') as Fact['valueType'], unit: row.unit || '', source: row.source || '', ...(row.context ? { context: row.context } : {}) };
}
export interface FactRequest { option_id: string; attribute_id: string; value_type: Fact['valueType']; unit: string | null }
export const apiService = {
  register: (username: string) => request<Session>(`${planning}/v1/users`, 'POST', { username }, ''),
  resume: (id: string, token: string) => request<{ id: string; username: string }>(`${planning}/v1/users/${encodeURIComponent(id)}`, 'GET', undefined, token),
  revoke: () => request(`${planning}/v1/session/revoke`, 'POST', {}),
  async getForms(userID: string): Promise<Form[]> {
    const response = await request<Array<Omit<PlanRow, 'category'> & { plan_category: string }>>(`${planning}/v1/plans/organiser/${encodeURIComponent(userID)}`);
    const states: Record<string, Form['state']> = { DRAFT: 'Draft', COLLECTING: 'Collecting', REVIEWING: 'Reviewing', CONFIRMED: 'Confirmed', ARCHIVED: 'Archived' };
    return (response || []).map(row => ({ id: row.id, title: row.title, description: row.description || '', category: ({ TRAVEL: 'Travel', DINING: 'Event', MEETING: 'Work', GENERAL: 'General' } as Record<string, string>)[row.plan_category] || row.plan_category,
      state: states[row.state] || 'Draft', membersCount: row.members_count, createdBy: row.organiser_name || 'You',
      questions: [], startDateRange: '', endDateRange: '', location: '' }));
  },
  // Creates or updates the unpublished plan, options, questions and draft round.
  async saveFormDraft(form: Form, userId: string, username: string): Promise<Form> {
    validateForm(form, true);
    const description = [form.description, form.location ? `Location: ${form.location}` : ''].filter(Boolean).join('\n');
    const timeWindow = { ...(form.startDateRange ? { time_window_start: `${form.startDateRange}T00:00:00Z` } : {}),
      ...(form.endDateRange ? { time_window_end: `${form.endDateRange}T23:59:59Z` } : {}) };
    if (!form.id) {
      const row = await request<PlanRow>(`${planning}/v1/plans`, 'POST', { title: form.title, description, ...timeWindow,
        plan_category: ({ Travel: 'TRAVEL', Event: 'DINING', Work: 'MEETING', General: 'GENERAL' } as Record<string, string>)[form.category] || 'GENERAL',
        plan_state: 'DRAFT', organiser_id: userId, organiser_name: username });
      form.id = row.id;
    } else await request(`${planning}/v1/plans/${form.id}`, 'PATCH', { title: form.title, description, ...timeWindow });
    // Items removed after an earlier draft save still exist on the server.
    while (form.removedOptionIds?.length) { await request(`${planning}/v1/proposed_activity/${form.removedOptionIds[0]}`, 'DELETE'); form.removedOptionIds.shift(); }
    while (form.removedQuestionIds?.length) { await request(`${planning}/v1/question/${form.removedQuestionIds[0]}`, 'DELETE'); form.removedQuestionIds.shift(); }
    // Keep acknowledged IDs to resume the same draft after a partial failure.
    for (const option of form.decisionOptions || []) {
      const body = { title: option.title, description: option.summary || '', metadata: optionMetadata(option, form) };
      if (option.id) await request(`${planning}/v1/proposed_activity/${option.id}`, 'PATCH', body);
      else option.id = (await request<{ id: string }>(`${planning}/v1/proposed_activity/plans/${form.id}`, 'POST', body)).id;
    }
    for (const [index, question] of form.questions.entries()) {
      const body = { title: question.title, description: question.description, question_type:
        question.type === 'Multiple choice' ? 'CUSTOM_MULTI_CHOICE' : ['Single choice', 'Location', 'Budget'].includes(question.type) ? 'CUSTOM_SINGLE_CHOICE' : 'CUSTOM_TEXT',
        is_required: question.isRequired !== false, sort_order: index,
        options: { options: question.options, decision: questionDefinition(question, index) } };
      if (question.id) await request(`${planning}/v1/question/${question.id}`, 'PATCH', body);
      else question.id = (await request<{ id: string }>(`${planning}/v1/question`, 'POST', { ...body, plan_id: form.id })).id;
    }
    if (!form.roundId) form.roundId = (await request<Round>(`${planning}/v1/rounds/plans/${form.id}`, 'POST', {})).id;
    return form;
  },
  async publishForm(form: Form, userId: string, username: string): Promise<Form> {
    validateForm(form);
    if (form.roundId && form.publishAttempted) {
      try {
        const published = await apiService.snapshot(form.roundId);
        if (published?.options?.length) { form.state = 'Collecting'; return form; }
      } catch (error) { if (!(error instanceof ApiError && error.status === 404)) throw error; }
      // A previous publish may still be in a recoverable cross-service handoff.
      // Retry that command before attempting guarded definition mutations.
      try {
        await request(`${roundPath(form.roundId)}/publish`, 'POST', publishSettings(form));
        form.state = 'Collecting'; return form;
      } catch (error) {
        if (!(error instanceof ApiError && error.code === 'INVALID_DEFINITION')) throw error;
      }
    }
    await apiService.saveFormDraft(form, userId, username);
    form.publishAttempted = true;
    await request(`${roundPath(form.roundId!)}/publish`, 'POST', publishSettings(form));
    form.state = 'Collecting';
    return form;
  },
  // Only currency and cost scope matter to collection; free-form plan text stays out of web searches.
  collectFacts: (form: Form, requests: FactRequest[], retry = false) => request<FactCollectionRun>(`${roundPath(form.roundId!)}/fact-collection`, 'POST', { requests, retry, settings: { currency: form.currency || 'SGD', cost_scope: 'per_person_total' } }),
  factCollection: (roundId: string) => request<FactCollectionRun>(`${roundPath(roundId)}/fact-collection`),
  acceptFacts: (roundId: string, body: { operation_id: string; collection_run_id: string; claim_ids: string[]; reviewed: true; replace_existing: boolean }) => request(`${roundPath(roundId)}/accept-facts`, 'POST', body),
  // Organiser research runs as background jobs; callers poll until each one completes.
  async research<T>(roundId: string, task: 'overviews' | 'questions' | 'fit', input: Record<string, unknown>, signal?: { cancelled: boolean }): Promise<T> {
    const signature = JSON.stringify(input);
    // LAN HTTP may not expose Web Crypto. Exact input is also a collision-free local key.
    const digest = globalThis.crypto?.subtle ? await crypto.subtle.digest('SHA-256', new TextEncoder().encode(signature)) : undefined;
    const hash = digest ? Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('') : signature;
    const key = checkpointKey(sessionStorage.getItem('user_id') || '', `research:${roundId}:${task}:${hash}`);
    const pending = readCheckpoint<string>(key);
    let run: ResearchRun<T> | undefined;
    if (pending) {
      try { run = await request<ResearchRun<T>>(`${roundPath(roundId)}/research?run=${encodeURIComponent(pending)}`); }
      catch (error) { if (!(error instanceof ApiError) || error.status !== 404) throw error; removeCheckpoint(key); }
    }
    if (!run) {
      run = await request<ResearchRun<T>>(`${roundPath(roundId)}/research`, 'POST', { task, input, retry: true });
      writeCheckpoint(key, run.run_id);
    }
    const until = Date.now() + 180000;
    while (run.status === 'pending' && Date.now() < until && !signal?.cancelled) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      run = await request<ResearchRun<T>>(`${roundPath(roundId)}/research?run=${encodeURIComponent(run.run_id)}`);
    }
    if (run.status !== 'pending') removeCheckpoint(key);
    if (run.status !== 'completed' || !run.research) throw new ApiError(503, run.issues[0]?.code || (run.status === 'pending' ? 'EXECUTION_DEADLINE_EXCEEDED' : 'RESEARCH_UNAVAILABLE'), 'Research unavailable');
    return run.research;
  },
  placeCard: (roundId: string, placeId: string) => request<Overview>(`${roundPath(roundId)}/place?place_id=${encodeURIComponent(placeId)}`),
  placePhotoUrl: (roundId: string, name: string) => `${roundPath(roundId)}/place-photo?name=${encodeURIComponent(name)}`,
  async storedFacts(optionId: string): Promise<Fact[]> {
    const row = await request<{ metadata?: { facts?: PublishedFact[] } }>(`${planning}/v1/proposed_activity/${optionId}`);
    return (row.metadata?.facts || []).map(localFact);
  },
  rounds: (id: string) => request<{ data: Round[] }>(`${planning}/v1/rounds/plans/${id}`),
  plan: (id: string) => request<PlanRow>(`${planning}/v1/plans/${id}`),
  snapshot: (id: string) => request<Snapshot>(`${roundPath(id)}/form`),
  invite: (planId: string, userId: string) => request<{ token: string }>(`${planning}/v1/plans/${planId}/invites`, 'POST', { created_by: userId }),
  join: (invite: string, id: string, username: string) => request(`${planning}/v1/invites/${encodeURIComponent(invite)}/join`, 'POST', { user_id: id, display_name: username }),
  draft: (id: string) => request<Draft>(ownPath(id)),
  saveDraft: (id: string, body: unknown) => request<Draft>(ownPath(id), 'PUT', body),
  submit: (id: string, revision: number) => request<Draft>(`${ownPath(id)}/submit`, 'POST', { expectedRevision: revision }),
  preview: (id: string, revision: number) => request<Run>(`${roundPath(id)}/preview`, 'POST', { expected_revision: revision, retry: true }),
  review: (id: string) => request<Review | { status: 'pending' }>(`${roundPath(id)}/preview`),
  close: (id: string) => request(`${roundPath(id)}/close`, 'POST', {}),
  recommend: (id: string) => request<Run>(`${roundPath(id)}/recommendations`, 'POST', { retry: true }),
  result: (id: string) => request<Run>(`${roundPath(id)}/recommendation`),
  selection: (id: string) => request<Selection>(`${roundPath(id)}/selection`),
  confirm: (id: string, run: string, candidate: string, operation: string) => request<Selection>(`${roundPath(id)}/confirm`, 'POST', { operation_id: operation, run_id: run, candidate_id: candidate }),
  reopen: (id: string, operation: string) => request<Round>(`${roundPath(id)}/reopen`, 'POST', { operation_id: operation }),
  rsvp: (id: string) => request<{ revision: number; status: string | null }>(`${participation}/rounds/${id}/my-rsvp`),
  saveRsvp: (id: string, selectionVersion: number, expectedRevision: number, status: string) => request(`${participation}/rounds/${id}/my-rsvp`, 'PUT', { selectionVersion, expectedRevision, status }),
};
