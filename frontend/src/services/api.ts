import { checkpointKey, readCheckpoint, writeCheckpoint, removeCheckpoint } from './checkpoints';
import { OPTION_RATING, decisionQuestion, factDefinitions, factStatus, factType, tagValues, validFact } from './optionFacts';
import type { Form, PlanRow, Question, Session, Snapshot, Round, Draft, Review, Run, Selection, DecisionOption, Fact, PublishedFact, Overview, ResearchRun, RsvpSummary } from '@/types/form';

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
  if (!response.ok) {
    const messages:Record<string,string>={RESPONSES_INCOMPLETE:'A member has not submitted a complete response. Collection is still open; refresh the progress before closing again.',STALE_DRAFT:'A newer draft round exists. Return to My forms and open it.',REOPEN_REQUIRED:'This round is published. Revise it in a new round to change its definition.'};
    throw new ApiError(response.status, data.code || 'REQUEST_FAILED', messages[data.code] || data.message || data.error || `Request failed (${response.status})`);
  }
  return data as T;
}
const roundPath = (id: string) => `${planning}/v1/rounds/${encodeURIComponent(id)}`;
const ownPath = (id: string) => `${participation}/rounds/${encodeURIComponent(id)}/my-response`;
export function questionDefinition(q: Question, index: number) {
  // Members rate each option directly; Decision compares the option's own identity.
  if (q.type === 'Option rating') return { role: 'soft', criterion: OPTION_RATING, relevance: 1, answer_format: 'option_rating' };
  const criterion = q.criterion?.trim() || `preference_${index + 1}`;
  const role = q.role || 'soft';
  const format = q.type === 'Multiple choice' ? 'multi_choice' : q.type === 'Number' ? 'number' : q.type === 'Boolean' ? 'boolean' :
    q.type === 'Duration' ? 'date_intervals' : ['Single choice', 'Location', 'Budget'].includes(q.type) ? 'choice' : 'text';
  // Cost compares exact currency amounts and a requirement means "at most"; other numbers are plain numbers.
  const isCost = criterion === 'max_cost';
  const valueType = factType(q);
  const decision: Record<string, unknown> = { role, criterion: role === 'informational' ? 'context' : criterion, relevance: role === 'soft' ? 1 : 0, answer_format: format };
  if (role !== 'informational' && criterion !== 'preferences') {
    decision.mapping = { value_type: valueType, ...(q.unit ? { unit: q.unit } : {}),
      comparison_rule: role === 'hard' ? (valueType === 'tag_set' ? 'contains_all_v1' : isCost ? 'maximum_v1' : 'equals_v1') :
        valueType === 'tag_set' ? 'tag_overlap_v1' : ['number', 'decimal'].includes(valueType) ? 'numeric_target_v1' : 'attribute_match_v1',
      ...(['number', 'decimal'].includes(valueType) && role === 'soft' ? { scale: q.scale || 1 } : {}) };
    if (q.type === 'Number' && role === 'soft') decision.numeric_intent = 'target';
  }
  return decision;
}
function validateForm(form: Form, draft = false) {
  if (!form.title.trim() || !form.category) throw new Error('Add a title and category.');
  if ((form.decisionQuestion?.trim().length || 0) > 300) throw new Error('Keep the decision question under 300 characters.');
  if ((form.decisionOptions?.length || 0) > 8 || (!draft && (!form.decisionOptions?.length || form.decisionOptions.some(o => !o.title.trim())))) throw new Error('Add 1–8 named options.');
  // Drafts saved for fact finding come before the questions are written.
  if (!draft && (!form.questions.length || form.questions.some(q => !q.title.trim()))) throw new Error('Name each question.');
  const definitions = factDefinitions(form);
  if (definitions.length > 8) throw new Error('Use up to eight distinct option attributes. Reuse attributes across questions.');
  // Publishing validates the form structure. Missing evidence is supplemented
  // during Decision processing; it is not a per-question organiser checklist.
  if (form.questions.filter(q => q.type === 'Option rating').length > 1) throw new Error('Ask members to rate the options once.');
  for (const q of form.questions.filter(q => q.role !== 'informational' && q.type !== 'Option rating')) {
    if (!draft && !/^[a-z][a-z0-9_]{0,59}$/.test(q.criterion || '') && q.title.trim()) throw new Error('Choose the option detail each question compares.');
    const definition = definitions.find(d => d.criterion === q.criterion);
    if (definition && (definition.valueType !== factType(q) || definition.unit !== (q.unit || ''))) throw new Error('Questions about the same attribute must use the same fact type and unit.');
  }
  if (form.questions.some(q => q.type === 'Duration' && q.role !== 'informational')) throw new Error('Date availability requires scenario or scheduled setup. Use an informational date question in this option form.');
  if (form.questions.some(q => q.type === 'Number' && q.role !== 'hard' && q.role !== 'informational' && !(Number(q.scale) > 0))) throw new Error('Numeric preferences need a positive tolerance.');
  // Blank facts persist as typed unknowns, including pending research/recovery metadata.
  for (const option of form.decisionOptions || []) for (const fact of option.facts.filter(f => f.value.trim())) {
    if (!/^[a-z][a-z0-9_]{0,99}$/.test(fact.criterion.trim())) throw new Error('Give each fact a criterion name using lowercase letters, numbers and underscores.');
    if (fact.valueType === 'number' && !Number.isFinite(Number(fact.value))) throw new Error('Numeric facts need a finite number.');
  }
}
function publishSettings(form: Form) {
  const question = decisionQuestion(form);
  return { currency: form.currency || 'SGD', currency_minor_digits: 2, cost_scope: 'per_person_total',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, execution_mode: 'options', interpretation_policy: 'facts-v1', ...(question ? { decision_question: question } : {}) };
}
// The collector searches for this identity; acceptance rejects claims if it changes afterwards.
export function optionIdentity(option: DecisionOption, form: Form) {
  const link = option.identity?.source_url?.trim();
  const { place_id, kind } = option.identity || {};
  return { model_id: option.title.trim(), ...(form.location.trim() ? { region: form.location.trim() } : {}), ...(link ? { source_url: link } : {}),
    ...(place_id ? { place_id } : {}), ...(kind ? { kind } : {}) };
}
function optionMetadata(option: DecisionOption, form: Form) {
  const facts = option.facts.map(f => ({ criterion: f.criterion.trim(), value_type: f.valueType,
    value: !f.value.trim() ? null : f.valueType === 'number' ? Number(f.value) : f.valueType === 'boolean' ? f.value === 'true' : f.valueType === 'tag_set' ? tagValues(f.value) : f.value,
    ...(f.unit ? { unit: f.unit } : {}),
    ...(f.context || f.criterion === 'max_cost' ? { context: { ...f.context, ...(f.criterion === 'max_cost' ? { scope: 'per_person_total' } : {}) } } : {}),
    status: f.value.trim() ? factStatus(f) : 'unknown', source: f.source || 'Organiser supplied' }));
  // The summary is stored as the option description so members see it; place content is not.
  return { identity: optionIdentity(option, form), facts, ...(option.brief ? { brief: option.brief } : {}) };
}
export function localFact(row: PublishedFact): Fact {
  const value = Array.isArray(row.value) ? row.value_type==='tag_set' ? JSON.stringify(row.value) : row.value.join(', ') : String(row.value ?? '');
  return { criterion: row.criterion, value, valueType: (row.value_type || 'category') as Fact['valueType'], unit: row.unit || '', source: row.source || '', status: row.status as Fact['status'], ...(row.context ? { context: row.context } : {}) };
}
export const apiService = {
  register: (username: string) => request<Session>(`${planning}/v1/users`, 'POST', { username }, ''),
  resume: (id: string, token: string) => request<{ id: string; username: string }>(`${planning}/v1/users/${encodeURIComponent(id)}`, 'GET', undefined, token),
  revoke: () => request(`${planning}/v1/session/revoke`, 'POST', {}),
  async getForms(userID: string): Promise<Form[]> {
    const response = await request<Array<Omit<PlanRow, 'category'> & { plan_category: string }>>(`${planning}/v1/plans/member/${encodeURIComponent(userID)}`);
    const states: Record<string, Form['state']> = { DRAFT: 'Draft', COLLECTING: 'Collecting', REVIEWING: 'Reviewing', CONFIRMED: 'Confirmed', ARCHIVED: 'Archived' };
    return (response || []).map(row => ({ id: row.id, title: row.title, description: row.description || '', category: ({ TRAVEL: 'Travel', DINING: 'Event', MEETING: 'Work', GENERAL: 'General' } as Record<string, string>)[row.plan_category] || row.plan_category,
      state: states[row.state] || 'Draft', membersCount: row.members_count, createdBy: row.organiser_name || 'You', createdByUserId: row.created_by_user_id,
      questions: [], startDateRange: '', endDateRange: '', location: '' }));
  },
  async loadFormDraft(planId: string): Promise<Form> {
    const plan = await request<PlanRow & { time_window_start?: string; time_window_end?: string;
      rounds: Round[]; proposed_activities?: { id:string; title:string; description?:string; metadata?: { identity?:DecisionOption['identity']; facts?:PublishedFact[]; brief?:DecisionOption['brief'] } }[];
      questions?: { id:string; title:string; description?:string; is_required:boolean; sort_order:number; type:string;
        options?: { options?:string[]; decision?: { role?:Question['role']; criterion?:string; answer_format?:string; mapping?: { value_type?:Fact['valueType']; unit?:string; scale?:number } } } }[] }>(`${planning}/v1/plans/details/${planId}`);
    const round = [...(plan.rounds || [])].sort((a,b) => b.round_number-a.round_number)[0];
    if (!round || plan.state !== 'DRAFT') throw new Error('This plan is already published. Open its round instead.');
    const { state } = await request<{state: {currency?:string; decision_question?:string; location?:string; step?:number; visited?:number}}>(`${roundPath(round.id)}/draft`);
    return { id:plan.id, roundId:round.id, sourceRoundId:round.source_round_id, title:plan.title, description:plan.description || '',
      category:({TRAVEL:'Travel',DINING:'Event',MEETING:'Work',GENERAL:'General'} as Record<string,string>)[plan.category] || plan.category,
      state:'Draft', currency:state.currency || 'SGD', decisionQuestion:state.decision_question || '', location:state.location || '',
      startDateRange:plan.time_window_start?.slice(0,10) || '', endDateRange:plan.time_window_end?.slice(0,10) || '',
      wizardStep:state.step || (round.source_round_id ? 4 : 1), wizardVisited:state.visited || 1,
      decisionOptions:(plan.proposed_activities || []).map(o => ({id:o.id,title:o.title,summary:o.description || '',identity:o.metadata?.identity,
        brief:o.metadata?.brief,facts:(o.metadata?.facts || []).map(localFact)})),
      questions:[...(plan.questions || [])].sort((a,b)=>a.sort_order-b.sort_order).map(q => { const d=q.options?.decision;
        return {id:q.id,title:q.title,description:q.description || '',isRequired:q.is_required,options:q.options?.options || [],role:d?.role || 'soft',criterion:d?.criterion,
          unit:d?.mapping?.unit,valueType:d?.mapping?.value_type,scale:d?.mapping?.scale,type:({choice:'Single choice',multi_choice:'Multiple choice',number:'Number',boolean:'Boolean',date_intervals:'Duration',option_rating:'Option rating'} as Record<string,Question['type']>)[d?.answer_format || ''] || 'Short answer'}; }) };
  },
  // Creates or updates the unpublished plan, options, questions and draft round.
  async saveFormDraft(form: Form, userId: string, username: string): Promise<Form> {
    validateForm(form, true);
    const description = form.description;
    const timeWindow = { ...(form.startDateRange ? { time_window_start: `${form.startDateRange}T00:00:00Z` } : {}),
      ...(form.endDateRange ? { time_window_end: `${form.endDateRange}T23:59:59Z` } : {}) };
    if (form.roundId) {
      await request(`${roundPath(form.roundId)}/draft`, 'PUT', { currency:form.currency || 'SGD', decision_question:form.decisionQuestion || '',
        location:form.location, step:form.wizardStep || 1, visited:Math.max(form.wizardStep || 1, form.wizardVisited || 1) });
    }
    if (!form.id) {
      const row = await request<PlanRow>(`${planning}/v1/plans`, 'POST', { title: form.title, description, ...timeWindow,
        plan_category: ({ Travel: 'TRAVEL', Event: 'DINING', Work: 'MEETING', General: 'GENERAL' } as Record<string, string>)[form.category] || 'GENERAL',
        plan_state: 'DRAFT', organiser_id: userId, organiser_name: username });
      form.id = row.id;
    } else await request(`${planning}/v1/plans/${form.id}`, 'PATCH', { title: form.title, description, ...timeWindow,
      plan_category:({Travel:'TRAVEL',Event:'DINING',Work:'MEETING',General:'GENERAL'} as Record<string,string>)[form.category] || 'GENERAL' });
    // Items removed after an earlier draft save still exist on the server.
    while (form.removedOptionIds?.length) { await request(`${planning}/v1/proposed_activity/${form.removedOptionIds[0]}`, 'DELETE'); form.removedOptionIds.shift(); }
    while (form.removedQuestionIds?.length) { await request(`${planning}/v1/question/${form.removedQuestionIds[0]}`, 'DELETE'); form.removedQuestionIds.shift(); }
    if (!form.roundId) {
      form.roundId = (await request<Round>(`${planning}/v1/rounds/plans/${form.id}`, 'POST', {})).id;
      await request(`${roundPath(form.roundId)}/draft`, 'PUT', { currency:form.currency || 'SGD', decision_question:form.decisionQuestion || '',
        location:form.location, step:form.wizardStep || 1, visited:Math.max(form.wizardStep || 1, form.wizardVisited || 1) });
    }
    for (const [index, question] of form.questions.entries()) {
      if (!question.title.trim()) continue;
      const body = { title: question.title, description: question.description, question_type:
        question.type === 'Multiple choice' ? 'CUSTOM_MULTI_CHOICE' : ['Single choice', 'Location', 'Budget'].includes(question.type) ? 'CUSTOM_SINGLE_CHOICE' : 'CUSTOM_TEXT',
        is_required: question.isRequired !== false, sort_order: index,
        options: { options: question.options, decision: questionDefinition(question, index) } };
      if (question.id) await request(`${planning}/v1/question/${question.id}`, 'PATCH', body);
      else question.id = (await request<{ id: string }>(`${planning}/v1/question`, 'POST', { ...body, plan_id: form.id })).id;
    }
    // Keep acknowledged IDs to resume the same draft after a partial failure.
    for (const option of (form.decisionOptions || []).filter(o => o.title.trim())) {
      const body = { title: option.title, description: option.summary || '', metadata: optionMetadata(option, form) };
      if (option.id) await request(`${planning}/v1/proposed_activity/${option.id}`, 'PATCH', body);
      else option.id = (await request<{ id: string }>(`${planning}/v1/proposed_activity/plans/${form.id}`, 'POST', body)).id;
    }
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
    for (const option of form.decisionOptions || []) for (const fact of option.facts) {
      if (validFact(fact, { criterion: fact.criterion, valueType: fact.valueType, unit: fact.unit }) && (!Array.isArray(fact.context?.alternatives) || !fact.context.alternatives.length)) {
        fact.status = 'confirmed';
        fact.context = { ...fact.context, reviewed: Boolean(fact.context?.corrected || fact.context?.reviewed), verification: fact.context?.corrected ? 'organiser' : fact.context?.verification || 'grounded_search' };
      }
    }
    await apiService.saveFormDraft(form, userId, username);
    form.publishAttempted = true;
    await request(`${roundPath(form.roundId!)}/publish`, 'POST', publishSettings(form));
    form.state = 'Collecting';
    // The deadline is guidance for the group; publishing never fails because of it.
    if (form.deadline) await apiService.setDeadline(form.roundId!, new Date(form.deadline).toISOString()).catch(() => undefined);
    return form;
  },
  // Organiser research runs as background jobs; callers poll until each one completes.
  async research<T>(roundId: string, task: 'overviews' | 'questions' | 'facts', input: Record<string, unknown>, signal?: { cancelled: boolean }): Promise<T> {
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
  rounds: (id: string) => request<{ data: Round[] }>(`${planning}/v1/rounds/plans/${id}`),
  plan: (id: string) => request<PlanRow>(`${planning}/v1/plans/${id}`),
  deletePlan: (id: string) => request(`${planning}/v1/plans/${encodeURIComponent(id)}`, 'DELETE'),
  removeMember: (id: string) => request(`${planning}/v1/members/${encodeURIComponent(id)}`, 'DELETE'),
  snapshot: (id: string) => request<Snapshot>(`${roundPath(id)}/form`),
  invite: (planId: string, userId: string) => request<{ token: string }>(`${planning}/v1/plans/${planId}/invites`, 'POST', { created_by: userId }),
  join: (invite: string, id: string, username: string) => request(`${planning}/v1/invites/${encodeURIComponent(invite)}/join`, 'POST', { user_id: id, display_name: username }),
  draft: (id: string) => request<Draft>(ownPath(id)),
  saveDraft: (id: string, body: unknown) => request<Draft>(ownPath(id), 'PUT', body),
  copyResponse: (id: string, source: string) => request<Draft>(`${ownPath(id)}/copy`, 'POST', { sourceRoundId: source }),
  submit: (id: string, revision: number) => request<Draft>(`${ownPath(id)}/submit`, 'POST', { expectedRevision: revision }),
  preview: (id: string, revision: number) => request<Run>(`${roundPath(id)}/preview`, 'POST', { expected_revision: revision, retry: true }),
  review: (id: string) => request<Review | { status: 'pending' }>(`${roundPath(id)}/preview`),
  // Early close counts only members with a submitted, current response.
  close: (id: string, countRespondedOnly = false) => request(`${roundPath(id)}/close`, 'POST', countRespondedOnly ? { count_responded_only: true } : {}),
  setDeadline: (id: string, deadline: string | null) => request(`${roundPath(id)}/deadline`, 'POST', { deadline_at: deadline }),
  recommend: (id: string) => request<Run>(`${roundPath(id)}/recommendations`, 'POST', { retry: true }),
  result: (id: string) => request<Run>(`${roundPath(id)}/recommendation`),
  selection: (id: string) => request<Selection>(`${roundPath(id)}/selection`),
  confirm: (id: string, run: string, candidate: string, operation: string) => request<Selection>(`${roundPath(id)}/confirm`, 'POST', { operation_id: operation, run_id: run, candidate_id: candidate }),
  reopen: (id: string, operation: string) => request<Round>(`${roundPath(id)}/reopen`, 'POST', { operation_id: operation }),
  rsvp: (id: string) => request<{ revision: number; status: string | null; summary?: RsvpSummary }>(`${participation}/rounds/${id}/my-rsvp`),
  saveRsvp: (id: string, selectionVersion: number, expectedRevision: number, status: string) => request(`${participation}/rounds/${id}/my-rsvp`, 'PUT', { selectionVersion, expectedRevision, status }),
};
