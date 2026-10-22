<template>
  <section v-if="snapshot && draft" :class="['response-flow', { guided }]" aria-labelledby="flow-heading">
    <p v-if="recoveryNotice" class="helper-text">{{ recoveryNotice }}</p>
    <div v-if="snapshot.previous_round_id && draft.revision === 0 && !closed" class="callout">
      <p>This is a new round. You can copy your earlier answers, then review them against the revised options and confirm requirements again.</p>
      <button :disabled="busy" @click="copyEarlier">Copy my earlier answers</button>
      <p v-if="error" role="alert">{{ error }}</p>
    </div>
    <div v-if="page.kind !== 'intro' && page.kind !== 'done'" class="flow-progress">
      <span class="meter" aria-hidden="true"><span :style="{ '--value': progressValue }"></span></span>
      <span class="progress-text">{{ progressLabel }}</span>
    </div>
    <Transition :name="direction > 0 ? 'page-forward' : 'page-back'" mode="out-in" @after-enter="focusHeading">
      <!-- Overview: what is being decided and the options with their facts -->
      <div v-if="page.kind === 'intro'" key="intro" class="flow-page">
        <p class="eyebrow">{{ title }}</p>
        <h1 id="flow-heading" ref="heading" tabindex="-1">{{ question }}</h1>
        <p v-if="description" class="lede">{{ description }}</p>
        <h2 class="section-label">The options <span class="muted">{{ snapshot.options.length }}</span></h2>
        <OptionCards :options="snapshot.options" :currency="snapshot.currency" :round-id="roundId" />
        <p class="privacy-note"><UiIcon name="lock" />Your answers are private. The group only sees the combined result.</p>
        <div class="flow-actions"><button class="btn-primary btn-large" @click="go(1)">{{ answeredCount ? 'Continue your response' : 'Start' }}<UiIcon name="arrow" /></button>
          <span class="helper-text">{{ total }} {{ total === 1 ? 'question' : 'questions' }} · about {{ Math.max(1, Math.round(total * 0.4)) }} min</span></div>
      </div>

      <!-- One question per page -->
      <form v-else-if="page.kind === 'question'" :key="page.q.question_id" class="flow-page" @submit.prevent="next" novalidate>
        <fieldset :disabled="busy || closed">
          <p :class="['role-tag', page.q.role || 'soft']">{{ roleHint(page.q.role) }}</p>
          <template v-if="['choice','multi_choice','boolean','date_intervals'].includes(page.q.answer_format || '')">
            <fieldset class="answer-group" :aria-describedby="error ? 'flow-error' : undefined">
              <legend><h2 id="flow-heading" ref="heading" tabindex="-1" class="question-title">{{ page.q.label }}<span v-if="page.q.required" class="required-mark" aria-hidden="true">*</span></h2></legend>
              <p v-if="page.q.answer_format === 'multi_choice'" class="helper-text choose-any">Choose all that apply.</p>
              <div v-if="page.q.answer_format === 'choice'" class="choice-list stacked">
                <label v-for="choice in page.q.choices" :key="choiceId(choice)" class="choice-option"><input type="radio" :name="page.q.question_id" v-model="values[page.q.question_id]" :value="choiceId(choice)" />{{ choiceLabel(choice) }}</label>
              </div>
              <div v-else-if="page.q.answer_format === 'multi_choice'" class="choice-list stacked">
                <label v-for="choice in page.q.choices" :key="choiceId(choice)" class="choice-option"><input type="checkbox" v-model="values[page.q.question_id]" :value="choiceId(choice)" />{{ choiceLabel(choice) }}</label>
              </div>
              <div v-else-if="page.q.answer_format === 'boolean'" class="choice-list binary">
                <label class="choice-option"><input type="radio" :name="page.q.question_id" v-model="values[page.q.question_id]" :value="true" />Yes</label>
                <label class="choice-option"><input type="radio" :name="page.q.question_id" v-model="values[page.q.question_id]" :value="false" />No</label>
              </div>
              <div v-else class="date-pair"><label>Available from<input type="date" v-model="dates[page.q.question_id]!.start" /></label><label>Through<input type="date" v-model="dates[page.q.question_id]!.end" :min="dates[page.q.question_id]!.start" /></label></div>
            </fieldset>
          </template>
          <template v-else>
            <h2 id="flow-heading" ref="heading" tabindex="-1" class="question-title"><label :for="`answer-${page.q.question_id}`">{{ page.q.label }}<span v-if="page.q.required" class="required-mark" aria-hidden="true">*</span></label></h2>
            <div class="single-input">
              <input v-if="page.q.answer_format === 'number'" :id="`answer-${page.q.question_id}`" v-model.number="values[page.q.question_id]" type="number" step="any" inputmode="decimal" :aria-describedby="error ? 'flow-error' : undefined" />
              <input v-else :id="`answer-${page.q.question_id}`" v-model="values[page.q.question_id]" :aria-describedby="error ? 'flow-error' : undefined" />
              <span v-if="page.q.mapping?.unit" class="unit">{{ page.q.mapping.unit }}</span>
            </div>
          </template>
          <Transition name="reveal"><p v-if="error" id="flow-error" role="alert" class="error">{{ error }}</p></Transition>
          <div class="flow-actions split">
            <button type="button" class="btn-quiet" @click="back"><UiIcon name="back" />Back</button>
            <button type="submit" class="btn-primary btn-large">{{ busy ? 'Saving…' : answered(page.q) || page.q.required ? 'Next' : 'Skip' }}<UiIcon v-if="!busy" name="arrow" /></button>
          </div>
        </fieldset>
      </form>

      <!-- Optional extras -->
      <form v-else-if="page.kind === 'extras'" key="extras" class="flow-page" @submit.prevent="next">
        <fieldset :disabled="busy || closed">
          <h2 id="flow-heading" ref="heading" tabindex="-1" class="question-title">Anything else the organiser should know?</h2>
          <p class="lede">Both are optional.</p>
          <fieldset class="answer-group restrictions">
            <legend>Can you take part in every option?</legend>
            <div v-for="option in snapshot.options" :key="option.option_id" class="restriction-row">
              <span>{{ option.title }}</span>
              <select v-model="flags[option.option_id]" :aria-label="`${option.title}: can you take part?`"><option value="">I can join</option><option value="CANNOT_JOIN">I can’t join this</option><option value="NEEDS_INFORMATION">I need more information</option></select>
            </div>
          </fieldset>
          <p v-if="snapshot.execution_mode === 'scheduled'" class="helper-text">Enter exact local availability times. Times are sent with their UTC instant.</p>
          <div v-if="snapshot.execution_mode === 'scheduled'" class="date-pair"><label>Available from<input type="datetime-local" v-model="availableStart" /></label><label>Until<input type="datetime-local" v-model="availableEnd" /></label></div>
          <label class="note-field">Private note <span class="optional">(only you can see this)</span><textarea v-model="privateNote" maxlength="1000" placeholder="Anything you’d like to keep with your own response" /><span class="char-count" aria-hidden="true">{{ privateNote.length }} / 1000</span></label>
          <Transition name="reveal"><p v-if="error" role="alert" class="error">{{ error }}</p></Transition>
          <div class="flow-actions split">
            <button type="button" class="btn-quiet" @click="back"><UiIcon name="back" />Back</button>
            <button type="submit" class="btn-primary btn-large">{{ busy ? 'Saving…' : 'Review answers' }}<UiIcon v-if="!busy" name="arrow" /></button>
          </div>
        </fieldset>
      </form>

      <!-- Review and submit -->
      <form v-else-if="page.kind === 'review'" key="review" class="flow-page" @submit.prevent="submit">
        <h2 id="flow-heading" ref="heading" tabindex="-1" class="question-title">Review your answers</h2>
        <p class="lede">Check everything before you submit. You can change your answers until collection closes.</p>
        <dl class="answer-summary">
          <div v-for="(q, i) in snapshot.questions" :key="q.question_id" class="rise" :style="{ '--i': i }">
            <dt>{{ q.label }}</dt>
            <dd><span :class="{ muted: !answered(q) }">{{ answerText(q) }}</span><button v-if="!closed" type="button" class="btn-quiet btn-small" @click="go(questionPage(i))">Change<span class="sr-only"> answer to {{ q.label }}</span></button></dd>
          </div>
          <div v-if="flagCount || privateNote" class="rise" :style="{ '--i': total }">
            <dt>Extras</dt>
            <dd><span>{{ [flagCount ? `${flagCount} option ${flagCount === 1 ? 'restriction' : 'restrictions'}` : '', privateNote ? 'Private note added' : ''].filter(Boolean).join(' · ') }}</span><button v-if="!closed" type="button" class="btn-quiet btn-small" @click="go(pages.length - 2)">Change<span class="sr-only"> extras</span></button></dd>
          </div>
        </dl>

        <div class="interpretation-box" aria-live="polite">
          <div v-if="busyAction === 'preview'" class="checking"><span class="pulse" aria-hidden="true"></span>Checking how your answers will be read…</div>
          <template v-else-if="review">
            <h3>How your answers will be read</h3>
            <p v-for="(issue, i) in review.issues" :key="i" class="helper-text">{{ issueLabel(issue) }}</p>
            <dl class="interpretation" v-if="review.preferences?.length || requirements.length">
              <div v-for="(row,index) in review.preferences" :key="`p${index}`"><dt>{{ humanise(row.attribute_id) }}</dt><dd>{{ row.kind === 'indifferent' ? 'No preference' : display(row.preferred_value) }} <span class="kind">Preference</span></dd></div>
              <div v-for="(row,index) in requirements" :key="`r${index}`"><dt>{{ humanise(row.attribute_id) }}</dt><dd>{{ ruleLabel(row.constraint_rule) }} {{ display(row.required_value) }} {{ row.unit || '' }} <span class="kind requirement">Requirement</span></dd></div>
            </dl>
            <details v-if="review.issues.length" class="review-diagnostics"><summary>Technical details</summary><ul><li v-for="(issue, index) in review.issues" :key="index">{{ issue.code }}<template v-if="issue.message">: {{ issue.message }}</template></li></ul></details>
            <label v-if="requirements.length" class="confirm-row choice-option"><input v-model="confirmed" type="checkbox" :disabled="closed" />These requirements match my answers.</label>
          </template>
          <p v-else-if="previewError" class="helper-text">{{ previewError }} <button type="button" class="btn-quiet btn-small" @click="preview">Try again</button></p>
        </div>

        <Transition name="reveal"><p v-if="error" role="alert" class="error">{{ error }}</p></Transition>
        <p v-if="closed" class="callout">{{ unsupportedEditor ? 'This response is read-only to preserve its availability windows.' : 'This round is closed. Your submitted response remains available here.' }}</p>
        <div v-else class="flow-actions split">
          <button type="button" class="btn-quiet" @click="back"><UiIcon name="back" />Back</button>
          <button type="submit" class="btn-primary btn-large" :disabled="busy || (hasRequirementQuestions && !(review && (!requirements.length || confirmed)))" :aria-describedby="hasRequirementQuestions ? 'submit-hint' : undefined">{{ busyAction === 'submit' ? 'Submitting…' : draft.status === 'SUBMITTED' ? 'Update response' : 'Submit response' }}<UiIcon v-if="busyAction !== 'submit'" name="check" /></button>
        </div>
        <p v-if="hasRequirementQuestions && !closed && review && requirements.length && !confirmed" id="submit-hint" class="helper-text submit-hint">Confirm the requirements above to submit.</p>
      </form>

      <!-- Submitted -->
      <div v-else key="done" class="flow-page done">
        <span class="seal" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m6 12.5 4 4L18 8" /></svg></span>
        <h2 id="flow-heading" ref="heading" tabindex="-1" class="question-title">Your response is in</h2>
        <p class="lede">Thanks{{ name ? `, ${name}` : '' }}. Once the organiser closes collection, the recommendation will appear here.</p>
        <div class="flow-actions centred">
          <button v-if="guided" class="btn-primary" @click="emit('refresh')"><UiIcon name="refresh" />Check for results</button>
          <button @click="go(pages.length - 1)">Edit my response</button>
        </div>
        <details v-if="guided" class="done-options"><summary>See the options again</summary><OptionCards :options="snapshot.options" :currency="snapshot.currency" :round-id="roundId" compact /></details>
      </div>
    </Transition>
  </section>
  <section v-else-if="error" class="response-flow"><p role="alert" class="error">{{ error }}</p><button @click="load">Reload response</button></section>
  <div v-else class="response-flow" role="status"><p class="muted">Loading your response…</p><div class="skeleton tall" aria-hidden="true"></div><div class="skeleton" aria-hidden="true"></div></div>
</template>
<script setup lang="ts">
import UiIcon from './UiIcon.vue';
import OptionCards from './OptionCards.vue';
import { ref, reactive, computed, nextTick, onMounted, onUnmounted, watch } from 'vue';
import { checkpointKey, readCheckpoint, writeCheckpoint, removeCheckpoint } from '@/services/checkpoints';
import { apiService } from '@/services/api';
import { useAuthStore } from '@/stores/auth';
import type { Snapshot, Draft, Answer, Review, Choice, PublishedQuestion } from '@/types/form';
const props = withDefaults(defineProps<{ roundId: string; snapshot: Snapshot; title?: string; description?: string; guided?: boolean }>(), { title: '', description: '', guided: false });
const emit = defineEmits<{ (e: 'saved'): void; (e: 'refresh'): void }>();
const auth = useAuthStore();
const name = auth.username;
// Older rounds stored the plan title as the question; show nothing twice.
const question = computed(() => props.snapshot.decision_question && props.snapshot.decision_question !== props.title ? props.snapshot.decision_question : props.title);
type AnswerValue = string | number | boolean | string[];
type Page = { kind: 'intro' } | { kind: 'question'; q: PublishedQuestion; index: number } | { kind: 'extras' } | { kind: 'review' } | { kind: 'done' };
const draft = ref<Draft>(); const values = reactive<Record<string, AnswerValue>>({});
const dates = reactive<Record<string, { start: string; end: string }>>({}); const flags = reactive<Record<string,string>>({});
const availableStart = ref(''); const availableEnd = ref(''); const privateNote = ref('');
const review = ref<Review>(); const confirmed = ref(false); const busy = ref(false); const busyAction = ref(''); const error = ref(''); const previewError = ref(''); const unsupportedEditor = ref(false);
const heading = ref<HTMLElement>();
const at = ref(0); const direction = ref(1); const submitted = ref(false);
let alive = true; let savedState = ''; let loaded = false;
const recoveryKey = checkpointKey(auth.userID, `response:${props.roundId}`);
const definition = JSON.stringify([props.snapshot.option_revision, props.snapshot.questions]);
interface ResponseRecovery {
  revision: number; definition: string; at: number; dirty: boolean;
  values: Record<string, AnswerValue>; dates: Record<string, { start: string; end: string }>;
  flags: Record<string, string>; note: string; start: string; end: string;
}
const recovered = readCheckpoint<ResponseRecovery>(recoveryKey);
const recoveryNotice = ref('');
watch([values, dates, flags, privateNote, availableStart, availableEnd, at, draft, submitted], () => {
  if (!loaded || !draft.value || closed.value) return;
  if (submitted.value) { removeCheckpoint(recoveryKey); return; }
  if (!writeCheckpoint(recoveryKey, { revision: draft.value.revision, definition, at: at.value, dirty: state() !== savedState,
    values, dates, flags, note: privateNote.value, start: availableStart.value, end: availableEnd.value })) {
    recoveryNotice.value = 'Browser storage is unavailable. Use Next to save each answer before refreshing.';
  }
}, { deep: true, flush: 'sync' });

const pages = computed<Page[]>(() => [
  ...(props.guided ? [{ kind: 'intro' } as Page] : []),
  ...props.snapshot.questions.map((q, index) => ({ kind: 'question', q, index }) as Page),
  { kind: 'extras' }, { kind: 'review' },
]);
const page = computed<Page>(() => submitted.value ? { kind: 'done' } : pages.value[Math.min(at.value, pages.value.length - 1)]!);
const firstQuestion = computed(() => props.guided ? 1 : 0);
function questionPage(index: number) { return firstQuestion.value + index; }
const total = computed(() => props.snapshot.questions.length);
const progressValue = computed(() => (at.value - firstQuestion.value + 1) / (pages.value.length - firstQuestion.value));
const progressLabel = computed(() => page.value.kind === 'question' ? `Question ${page.value.index + 1} of ${total.value}` : page.value.kind === 'extras' ? 'Almost done' : 'Review');

function roleHint(role?: string) { return role === 'hard' ? 'Requirement · options that don’t match are ruled out' : role === 'informational' ? 'For context · doesn’t affect the ranking' : 'Preference · helps rank the options'; }
function issueLabel(issue: Review['issues'][number]) {
  if (issue.code === 'EXECUTION_ADAPTER_REQUIRED') return 'This preview interprets your answers. The organiser calculates option rankings after collection closes.';
  return issue.message || issue.code.toLowerCase().replaceAll('_', ' ');
}
function choiceId(choice: Choice) { return typeof choice === 'string' ? choice : choice.choice_id; }
function choiceLabel(choice: Choice) { return typeof choice === 'string' ? choice : choice.label; }
function ruleLabel(rule: string) { return ({ equals_v1:'must be', maximum_v1:'at most', minimum_v1:'at least', contains_all_v1:'must include all of' } as Record<string,string>)[rule] || 'requirement'; }
function humanise(id: string) { return id === 'max_cost' ? 'Cost per person' : id.replaceAll('_', ' ').replace(/^./, c => c.toUpperCase()); }
function display(value: unknown) { return Array.isArray(value) ? value.join(', ') : typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value ?? ''); }
const closed = computed(() => unsupportedEditor.value || (!!draft.value && draft.value.round.state !== 'COLLECTING'));
const requirements = computed(() => (review.value?.constraints || []).filter(row => row.kind !== 'unlimited'));
const hasRequirementQuestions = computed(() => props.snapshot.questions.some(q => q.role === 'hard'));
const answeredCount = computed(() => answers().length);
const flagCount = computed(() => Object.values(flags).filter(Boolean).length);
watch([values, dates, flags, availableStart, availableEnd], () => { review.value = undefined; confirmed.value = false; }, { deep: true, flush: 'sync' });

function valueOf(q: PublishedQuestion) {
  const date = dates[q.question_id];
  return q.answer_format === 'date_intervals' ? date?.start && date?.end ? [{ start_date: date.start, end_date: date.end }] : [] : values[q.question_id];
}
function answered(q: PublishedQuestion) { const v = valueOf(q); return !(v === '' || v === undefined || (Array.isArray(v) && !v.length)); }
function answers() { return props.snapshot.questions.flatMap(q => answered(q) ? [{ question_id: q.question_id, value: valueOf(q) }] : []); }
function answerText(q: PublishedQuestion) {
  if (!answered(q)) return 'Not answered';
  const v = values[q.question_id];
  if (q.answer_format === 'date_intervals') { const d = dates[q.question_id]!; return `${d.start} to ${d.end}`; }
  const label = (id: unknown) => { const c = q.choices?.find(c => choiceId(c) === id); return c ? choiceLabel(c) : String(id); };
  if (Array.isArray(v)) return v.map(label).join(', ');
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  return q.choices?.length ? label(v) : `${v}${q.mapping?.unit ? ` ${q.mapping.unit}` : ''}`;
}
function state() { return JSON.stringify([answers(), flags, privateNote.value, availableStart.value, availableEnd.value]); }

async function save(useConfirmation = false) {
  if (!draft.value) throw new Error('Reload your response first.');
  const list: Answer[] = answers();
  if (useConfirmation) {
    if (!review.value || review.value.response_revision !== draft.value.revision) throw new Error('Review the current saved revision first.');
    for (const answer of list) {
      const own = requirements.value.filter(row => row.source_question_id === answer.question_id);
      if (own.length) {
        answer.reviewed_revision = draft.value.revision;
        answer.confirmed_requirements = own.map(row => ({ attribute_id: row.attribute_id, required_value: row.required_value, constraint_rule: row.constraint_rule, unit: row.unit ?? null }));
      }
    }
  }
  const availability = props.snapshot.execution_mode === 'scheduled' && availableStart.value && availableEnd.value ?
    [{ startAt: new Date(availableStart.value).toISOString(), endAt: new Date(availableEnd.value).toISOString() }] : draft.value.availability;
  draft.value = await apiService.saveDraft(props.roundId, { expectedRevision: draft.value.revision, acknowledgedOptionRevision: props.snapshot.option_revision,
    availability, budget: draft.value.budget.kind === 'CAP' ? { kind: 'CAP', capMinor: draft.value.budget.capMinor } : { kind: draft.value.budget.kind },
    activityAnswers: Object.entries(flags).filter(([,value]) => value).map(([activityId,kind]) => ({ activityId, kind })), privateNote: privateNote.value, answers: list });
  savedState = state();
  review.value = undefined; confirmed.value = false;
}
async function action(name: string, fn: () => Promise<void>) {
  if (busy.value) return false; busy.value = true; busyAction.value = name; error.value = '';
  try { await fn(); emit('saved'); return true; } catch(e) { error.value = e instanceof Error ? e.message : 'Request failed. Reload if another tab changed your response.'; return false; }
  finally { busy.value = false; busyAction.value = ''; }
}

function go(index: number) {
  direction.value = submitted.value || index >= at.value ? 1 : -1;
  error.value = ''; submitted.value = false; at.value = index;
  if (pages.value[index]?.kind === 'review' && !closed.value && !review.value) preview();
}
function back() { go(Math.max(0, at.value - 1)); }
function problem() {
  const p = page.value;
  if (p.kind !== 'question') return '';
  const d = dates[p.q.question_id];
  if (p.q.answer_format === 'date_intervals' && d && (!!d.start !== !!d.end)) return 'Add both dates, or leave both empty.';
  if (p.q.answer_format === 'date_intervals' && d?.start && d.end && d.end < d.start) return 'The second date must be on or after the first.';
  if (p.q.answer_format === 'number' && values[p.q.question_id] !== '' && !Number.isFinite(Number(values[p.q.question_id]))) return 'Enter a number.';
  if (p.q.required && !answered(p.q)) return 'Answer this question to continue.';
  return '';
}
// Each step saves the draft, so nothing is lost if the member leaves part way.
async function next() {
  const issue = problem();
  if (issue) { error.value = issue; return; }
  if (!closed.value && state() !== savedState && !(await action('save', () => save()))) return;
  go(at.value + 1);
}
function focusHeading() { heading.value?.focus({ preventScroll: true }); }
watch(at, async () => { await nextTick(); const top = document.querySelector('.response-flow'); if (top && top.getBoundingClientRect().top < 0) top.scrollIntoView({ behavior: 'smooth', block: 'start' }); });

async function preview() {
  if (busy.value) return;
  previewError.value = '';
  busy.value = true; busyAction.value = 'preview';
  try {
    if (state() !== savedState || !draft.value!.revision) await save();
    await apiService.preview(props.roundId, draft.value!.revision);
    const until = Date.now() + 30000;
    while (alive && Date.now() < until) {
      const result = await apiService.review(props.roundId);
      if ('constraints' in result) { review.value = result; return; }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    throw new Error('Checking your answers is taking longer than usual.');
  } catch (e) { previewError.value = e instanceof Error ? e.message : 'Your answers couldn’t be checked.'; }
  finally { busy.value = false; busyAction.value = ''; }
}
async function submit() {
  const ok = await action('submit', async () => {
    if (requirements.value.length && !confirmed.value) throw new Error('Confirm the requirements after reviewing them.');
    await save(confirmed.value);
    draft.value = await apiService.submit(props.roundId, draft.value!.revision);
  });
  if (ok) { direction.value = 1; submitted.value = true; }
}
async function copyEarlier(){
  const ok=await action('copy',async()=>{await apiService.copyResponse(props.roundId,props.snapshot.previous_round_id!);});
  if(ok){await load();review.value=undefined;confirmed.value=false;recoveryNotice.value='Earlier answers copied as a draft. Check each answer and review requirements again before submitting.';}
}
async function load() { await action('load', async () => {
  const own = await apiService.draft(props.roundId); draft.value = own; privateNote.value = own.privateNote || '';
  if (own.availability.length > 1 || own.answers.some(answer =>
      props.snapshot.questions.find(q => q.question_id === answer.question_id)?.answer_format === 'date_intervals' && Array.isArray(answer.value) && answer.value.length > 1)) {
    unsupportedEditor.value = true;
    throw new Error('This response has multiple availability windows. The form is read-only here to preserve them.');
  }
  for (const q of props.snapshot.questions) { values[q.question_id] = q.answer_format === 'multi_choice' ? [] : ''; dates[q.question_id] = { start: '', end: '' }; }
  for (const answer of own.answers) {
    if (props.snapshot.questions.find(q => q.question_id === answer.question_id)?.answer_format === 'date_intervals') {
      const ranges = answer.value as { start_date: string; end_date: string }[];
      dates[answer.question_id] = { start: ranges[0]?.start_date || '', end: ranges[0]?.end_date || '' };
    } else values[answer.question_id] = answer.value as AnswerValue;
  }
  for (const option of props.snapshot.options) flags[option.option_id] = own.activityAnswers.find(row => row.activityId === option.option_id)?.kind || '';
  function local(instant?: string) { if (!instant) return ''; const d = new Date(instant); return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16); }
  availableStart.value = local(own.availability[0]?.startAt); availableEnd.value = local(own.availability[0]?.endAt);
  savedState = state();
  if (closed.value) { at.value = pages.value.length - 1; removeCheckpoint(recoveryKey); }
  else {
    if (own.status === 'SUBMITTED') submitted.value = true;
    if (recovered && recovered.definition === definition && recovered.revision === own.revision) {
      if (recovered.dirty) {
        Object.assign(values, recovered.values); Object.assign(dates, recovered.dates); Object.assign(flags, recovered.flags);
        privateNote.value = recovered.note; availableStart.value = recovered.start; availableEnd.value = recovered.end;
        submitted.value = false;
      }
      at.value = Math.max(0, Math.min(pages.value.length - 1, recovered.at));
      recoveryNotice.value = 'Your response and place in the form were restored. Review requirements again before submitting.';
    } else if (recovered) {
      removeCheckpoint(recoveryKey);
      recoveryNotice.value = 'A newer response or form version was found. Loaded the saved server response instead of older browser edits.';
    }
  }
  loaded = true;
}); }
onMounted(async () => { await load(); if (loaded && !submitted.value && !closed.value && page.value.kind === 'review') await preview(); }); onUnmounted(() => { alive = false; });
</script>
<style scoped>
.response-flow { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 32px; margin: 24px 0; overflow: hidden; scroll-margin-top: 24px; }
.response-flow.guided { max-width: 760px; margin: 0 auto; padding: 40px 44px 36px; }
.response-flow .tall { height: 140px; }
.flow-progress { display: flex; align-items: center; gap: 14px; margin-bottom: 28px; }
.flow-progress .meter { flex: 1; }
.progress-text { color: var(--muted); font-size: .75rem; font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; }
.flow-page { min-width: 0; }
.flow-page > fieldset { min-width: 0; }
.flow-page h1 { font-size: 2rem; margin-bottom: 10px; overflow-wrap: anywhere; }
.flow-page h1:focus, .flow-page h2:focus { outline: none; }
.eyebrow { font-size: .8125rem; font-weight: 600; color: var(--accent); margin-bottom: 8px; }
.lede { color: var(--muted); white-space: pre-wrap; overflow-wrap: anywhere; }
.section-label { font-size: .875rem; margin: 28px 0 12px; display: flex; gap: 8px; align-items: baseline; }
.section-label .muted { font-weight: 500; }
.privacy-note { display: flex; gap: 8px; color: var(--muted); font-size: .8125rem; margin: 24px 0 0; }
.privacy-note .ui-icon { width: 16px; height: 16px; margin-top: 3px; }
.role-tag { font-size: .75rem; font-weight: 600; color: var(--muted); margin-bottom: 10px; }
.role-tag.hard { color: #805114; }
.question-title { font-size: 1.5rem; line-height: 1.3; letter-spacing: -.02em; margin-bottom: 20px; overflow-wrap: anywhere; }
.question-title label { margin: 0; font-size: inherit; font-weight: inherit; }
.answer-group > legend { width: 100%; }
.answer-group > legend .question-title { margin-bottom: 20px; }
.choose-any { margin: -12px 0 14px; }
.choice-list.stacked { grid-template-columns: minmax(0, 1fr); }
.choice-list.stacked .choice-option, .choice-list.binary .choice-option { min-height: 56px; font-size: 1rem; }
.choice-list.binary { grid-template-columns: repeat(2, minmax(0, 1fr)); max-width: 420px; }
.choice-option input[type='radio'], .choice-option input[type='checkbox'] { margin-right: 12px; }
.single-input { display: flex; align-items: center; gap: 12px; max-width: 460px; }
.single-input input { font-size: 1.125rem; min-height: 54px; }
.unit { color: var(--muted); font-weight: 600; }
.date-pair { display: grid; grid-template-columns: repeat(2, minmax(0, 240px)); gap: 0 16px; }
.date-pair label { margin: 0; }
.flow-page .error { margin: 20px 0 0; }
.flow-actions { display: flex; align-items: center; gap: 16px; margin-top: 32px; flex-wrap: wrap; }
.flow-actions.split { justify-content: space-between; padding-top: 24px; border-top: 1px solid var(--line); }
.flow-actions.centred { justify-content: center; }
.flow-actions .helper-text { margin: 0; }
.btn-large { min-height: 50px; padding: 12px 24px; font-size: 1rem; min-width: 150px; }
.restrictions { margin-top: 8px; }
.restrictions > legend { margin-bottom: 12px; }
.restriction-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 240px); gap: 12px; align-items: center; padding: 8px 0; border-top: 1px solid var(--line); font-size: .9375rem; overflow-wrap: anywhere; }
.note-field { position: relative; margin-top: 24px; }
.char-count { position: absolute; right: 0; top: 0; font-size: .75rem; font-weight: 400; color: var(--muted); font-variant-numeric: tabular-nums; }
.answer-summary { margin: 8px 0 0; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
.answer-summary > div { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: 16px; padding: 12px 16px; font-size: .875rem; }
.answer-summary > div + div { border-top: 1px solid var(--line); }
.answer-summary dt { color: var(--muted); overflow-wrap: anywhere; }
.answer-summary dd { margin: 0; display: flex; justify-content: space-between; align-items: center; gap: 8px; font-weight: 600; overflow-wrap: anywhere; }
.answer-summary dd .muted { font-weight: 400; }
.answer-summary dd button { flex-shrink: 0; color: var(--accent); }
.interpretation-box { margin-top: 20px; }
.interpretation-box:empty { display: none; }
.interpretation-box > * + * { margin-top: 12px; }
.interpretation-box h3 { font-size: .9375rem; margin-bottom: 4px; }
.checking { display: flex; align-items: center; gap: 12px; padding: 14px 16px; border-radius: 8px; background: #f3f6f2; color: var(--muted); font-size: .875rem; }
.pulse { width: 10px; height: 10px; border-radius: 50%; background: var(--accent); animation: pulse 1.2s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: .35; transform: scale(.8); } }
.interpretation { margin: 0; display: grid; gap: 1px; background: #c9dccd; border: 1px solid #c9dccd; border-radius: 8px; overflow: hidden; }
.interpretation > div { display: grid; grid-template-columns: minmax(120px, 1fr) 2fr; gap: 16px; padding: 10px 14px; background: #f7faf7; font-size: .875rem; }
.interpretation dt { color: var(--muted); }
.interpretation dd { margin: 0; font-weight: 600; display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; }
.kind { font-size: .6875rem; font-weight: 600; color: var(--muted); }
.kind.requirement { color: #805114; }
.review-diagnostics { border-color: var(--line); }
.review-diagnostics li { font-size: .75rem; }
.confirm-row { font-size: .875rem; }
.submit-hint { text-align: right; max-width: none; }
.done { text-align: center; padding: 24px 0 8px; }
.done .lede { margin-left: auto; margin-right: auto; }
.seal { display: grid; place-items: center; width: 64px; height: 64px; margin: 0 auto 20px; border-radius: 50%; background: var(--accent); animation: pop-in 420ms var(--ease-out) both; }
.seal svg { width: 32px; height: 32px; fill: none; stroke: #fff; stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; stroke-dasharray: 20; animation: draw 520ms 220ms var(--ease-out) both; }
@keyframes draw { from { stroke-dashoffset: 20; } }
@keyframes pop-in { from { opacity: 0; transform: scale(.7); } }
.done-options { margin-top: 32px; text-align: left; }
.done-options[open] summary { margin-bottom: 12px; }
@media(max-width:700px) {
  .response-flow, .response-flow.guided { padding: 22px 20px; margin: 16px 0; }
  .flow-page h1 { font-size: 1.625rem; }
  .question-title { font-size: 1.25rem; }
  .flow-actions.split { flex-direction: column-reverse; align-items: stretch; }
  .flow-actions.split button, .flow-actions .btn-large { width: 100%; }
  .flow-actions.centred { flex-direction: column; align-items: stretch; }
  .date-pair { grid-template-columns: minmax(0, 1fr); gap: 12px; }
  .restriction-row, .answer-summary > div, .interpretation > div { grid-template-columns: minmax(0, 1fr); gap: 4px; }
  .submit-hint { text-align: left; }
}
</style>
