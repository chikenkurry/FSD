<template>
  <section v-if="snapshot && draft" class="response-panel">
    <h2>Your response</h2><p>Saved status: {{ draft.status }} · revision {{ draft.revision }}</p>
    <p v-if="message" role="status">{{ message }}</p><p v-if="error" role="alert" class="error">{{ error }}</p>
    <form @submit.prevent="submit">
      <fieldset :disabled="busy || closed">
        <div v-for="q in snapshot.questions" :key="q.question_id" class="question-card">
          <label>{{ q.label }} {{ q.required ? '*' : '' }}
            <select v-if="q.answer_format === 'choice'" v-model="values[q.question_id]" :required="q.required"><option value="">Choose…</option><option v-for="choice in q.choices" :key="choiceId(choice)" :value="choiceId(choice)">{{ choiceLabel(choice) }}</option></select>
            <select v-else-if="q.answer_format === 'boolean'" v-model="values[q.question_id]"><option value="">Choose…</option><option :value="true">Yes</option><option :value="false">No</option></select>
            <input v-else-if="q.answer_format === 'number'" v-model.number="values[q.question_id]" type="number" step="any" :required="q.required" />
            <input v-else-if="!['multi_choice','date_intervals'].includes(q.answer_format || '')" v-model="values[q.question_id]" :required="q.required" />
          </label>
          <template v-if="q.answer_format === 'multi_choice'"><label v-for="choice in q.choices" :key="choiceId(choice)"><input v-model="values[q.question_id]" type="checkbox" :value="choiceId(choice)" /> {{ choiceLabel(choice) }}</label></template>
          <template v-if="q.answer_format === 'date_intervals'"><label>Available from<input type="date" v-model="dates[q.question_id]!.start" /></label><label>Through<input type="date" v-model="dates[q.question_id]!.end" /></label></template>
        </div>
        <details><summary>Availability and option restrictions</summary>
          <p v-if="snapshot.execution_mode === 'scheduled'">Enter exact local availability times. Times are sent with their UTC instant.</p>
          <div v-if="snapshot.execution_mode === 'scheduled'"><label>Available from<input type="datetime-local" v-model="availableStart" /></label><label>Until<input type="datetime-local" v-model="availableEnd" /></label></div>
          <label v-for="option in snapshot.options" :key="option.option_id">{{ option.title }}<select v-model="flags[option.option_id]"><option value="">No restriction</option><option value="CANNOT_JOIN">Cannot join</option><option value="NEEDS_INFORMATION">Need more information</option></select></label>
        </details>
        <label>Private note<textarea v-model="privateNote" maxlength="1000" /></label>
        <div class="actions"><button type="button" @click="saveOnly">Save draft</button><button type="button" @click="preview">Save & review interpretation</button><button type="submit">Submit response</button></div>
        <div v-if="review" class="review-panel">
          <h3>Your private interpretation</h3>
          <p>Status: {{ review.status }}. Editing an answer invalidates this review.</p>
          <ul><li v-for="(issue,i) in review.issues" :key="i">{{ issue.message || issue.code }}</li></ul>
          <ul v-if="review.preferences?.length"><li v-for="(row,index) in review.preferences" :key="index">{{ row.attribute_id }}: {{ row.kind === 'indifferent' ? 'No preference' : row.preferred_value }}</li></ul>
          <div v-for="(row,index) in requirements" :key="index"><strong>{{ row.attribute_id }}</strong>: {{ ruleLabel(row.constraint_rule) }} {{ row.required_value }} {{ row.unit || '' }}</div>
          <label v-if="requirements.length"><input v-model="confirmed" type="checkbox" /> I reviewed these requirements and confirm they match my answers.</label>
        </div>
      </fieldset>
    </form>
    <p v-if="closed">{{ unsupportedEditor ? 'This response is read-only to preserve its availability windows.' : 'This round is closed. Your submitted response remains available here.' }}</p>
  </section>
  <section v-else-if="error" class="response-panel"><p role="alert" class="error">{{ error }}</p><button @click="load">Reload response</button></section>
  <p v-else>Loading your response…</p>
</template>
<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue';
import { apiService } from '@/services/api';
import type { Snapshot, Draft, Answer, Review, Choice } from '@/types/form';
const props = defineProps<{ roundId: string; snapshot: Snapshot }>();
const emit = defineEmits<{ (e: 'saved'): void }>();
type AnswerValue = string | number | boolean | string[];
const draft = ref<Draft>(); const values = reactive<Record<string, AnswerValue>>({});
const dates = reactive<Record<string, { start: string; end: string }>>({}); const flags = reactive<Record<string,string>>({});
const availableStart = ref(''); const availableEnd = ref(''); const privateNote = ref('');
const review = ref<Review>(); const confirmed = ref(false); const busy = ref(false); const error = ref(''); const message = ref(''); const unsupportedEditor = ref(false);
let alive = true;
function choiceId(choice: Choice) { return typeof choice === 'string' ? choice : choice.choice_id; }
function choiceLabel(choice: Choice) { return typeof choice === 'string' ? choice : choice.label; }
function ruleLabel(rule: string) { return ({ equals_v1:'must equal', maximum_v1:'at most', minimum_v1:'at least', contains_all_v1:'must include all of' } as Record<string,string>)[rule] || 'requirement'; }
const closed = computed(() => unsupportedEditor.value || (!!draft.value && draft.value.round.state !== 'COLLECTING'));
const requirements = computed(() => (review.value?.constraints || []).filter(row => row.kind !== 'unlimited'));
watch([values, dates, flags, availableStart, availableEnd], () => { review.value = undefined; confirmed.value = false; }, { deep: true, flush: 'sync' });
function answered() {
  return props.snapshot.questions.flatMap(q => {
    const date = dates[q.question_id];
    const value = q.answer_format === 'date_intervals' ? date?.start && date?.end ? [{ start_date: date.start, end_date: date.end }] : [] : values[q.question_id];
    return value === '' || value === undefined || (Array.isArray(value) && !value.length) ? [] : [{ question_id: q.question_id, value }];
  });
}
async function save(useConfirmation = false) {
  if (!draft.value) throw new Error('Reload your response first.');
  const answers: Answer[] = answered();
  if (useConfirmation) {
    if (!review.value || review.value.response_revision !== draft.value.revision) throw new Error('Review the current saved revision first.');
    for (const answer of answers) {
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
    activityAnswers: Object.entries(flags).filter(([,value]) => value).map(([activityId,kind]) => ({ activityId, kind })), privateNote: privateNote.value, answers });
  review.value = undefined; confirmed.value = false;
}
async function action(fn: () => Promise<void>) {
  if (busy.value) return; busy.value = true; error.value = ''; message.value = '';
  try { await fn(); emit('saved'); } catch(e) { error.value = e instanceof Error ? e.message : 'Request failed. Reload if another tab changed your response.'; }
  finally { busy.value = false; }
}
async function saveOnly() { await action(async () => { await save(); message.value = 'Draft saved.'; }); }
async function preview() { await action(async () => {
  await save(); await apiService.preview(props.roundId, draft.value!.revision);
  const until = Date.now() + 30000;
  while (alive && Date.now() < until) {
    const result = await apiService.review(props.roundId);
    if ('constraints' in result) { review.value = result; message.value = 'Review your interpreted answers below.'; return; }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error('Interpretation is still running. Try the review again shortly.');
}); }
async function submit() { await action(async () => {
  if (requirements.value.length && !confirmed.value) throw new Error('Confirm the requirements after reviewing them.');
  await save(confirmed.value);
  draft.value = await apiService.submit(props.roundId, draft.value!.revision);
  message.value = 'Response submitted.';
}); }
async function load() { await action(async () => {
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
}); }
onMounted(load); onUnmounted(() => { alive = false; });
</script>
<style scoped>
.response-panel { background: white; padding: 1.5rem; border-radius: 8px; margin: 1rem 0; }fieldset { border: 0; padding: 0; }.question-card { padding: .8rem 0; border-bottom: 1px solid #eee; }select { display: block; }.actions { display: flex; gap: .8rem; flex-wrap: wrap; }button { padding: .7rem; }.error { color: #a02020; }.review-panel { margin-top: 1rem; padding: 1rem; background: #f2f6fa; overflow-wrap: anywhere; }
</style>
