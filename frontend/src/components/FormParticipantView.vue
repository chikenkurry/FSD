<template>
  <section v-if="snapshot && draft" :class="['response-flow', { guided }]" aria-labelledby="flow-heading">
    <Transition name="reveal"
      ><p v-if="recoveryNotice" class="flow-notice" role="status">
        <UiIcon name="refresh" /><span>{{ recoveryNotice }}</span
        ><button type="button" class="btn-quiet btn-icon" aria-label="Dismiss" @click="recoveryNotice = ''">
          <UiIcon name="close" />
        </button></p
    ></Transition>
    <div v-if="snapshot.previous_round_id && draft.revision === 0 && !closed" class="callout">
      <p>
        This is a new round. You can copy your earlier answers, then review them against the revised options and confirm
        requirements again.
      </p>
      <button :disabled="busy" @click="copyEarlier">Copy my earlier answers</button>
      <p v-if="error" role="alert">{{ error }}</p>
    </div>
    <div v-if="page.kind !== 'intro' && page.kind !== 'done'" class="flow-progress">
      <span class="meter" aria-hidden="true"><span :style="{ '--value': progressValue }"></span></span>
      <span class="progress-text">{{ progressLabel }}</span>
    </div>
    <Transition :name="direction > 0 ? 'page-forward' : 'page-back'" mode="out-in" @after-enter="focusHeading">
      <!-- Overview: what is being decided and the options with their facts -->
      <div v-if="page.kind === 'intro'" key="intro" class="flow-page intro">
        <div class="intro-head">
          <div>
            <p v-if="question !== title" class="plan-context">
              <UiIcon name="people" /><span
                >Part of <strong>{{ title }}</strong></span
              >
            </p>
            <h1 id="flow-heading" ref="heading" tabindex="-1">{{ question }}</h1>
            <p v-if="description" class="lede">{{ description }}</p>
          </div>
          <div class="intro-start">
            <button class="btn-primary btn-large" @click="go(1)">
              {{ answeredCount ? 'Continue your response' : 'Start' }}<UiIcon name="arrow" />
            </button>
            <span class="helper-text"
              >{{ total }} {{ total === 1 ? 'question' : 'questions' }} · about
              {{ Math.max(1, Math.round(total * 0.4)) }} min</span
            >
            <span v-if="dueText" :class="['due', { overdue: overdue }]">{{ dueText }}</span>
          </div>
        </div>
        <div class="options-head">
          <h2 class="section-label">
            The options <span class="muted">{{ snapshot.options.length }}</span>
          </h2>
          <p class="helper-text">Have a look before you start. The questions ask what matters to you.</p>
        </div>
        <OptionCards :options="snapshot.options" :currency="snapshot.currency" :round-id="roundId" />
        <p class="privacy-note">
          <UiIcon name="lock" />Your answers are private. The group only sees the combined result.
        </p>
      </div>

      <!-- One question per page -->
      <form
        v-else-if="page.kind === 'question'"
        :key="page.q.question_id"
        class="flow-page"
        @submit.prevent="next"
        novalidate
      >
        <fieldset :disabled="busy || closed">
          <div class="question-tags">
            <span :class="['role-tag', page.q.role || 'soft']">{{ questionKind(page.q).name }}</span>
            <span v-if="page.q.required" class="required-tag">Required</span>
          </div>
          <template v-if="page.q.answer_format === 'date_poll'">
            <fieldset class="answer-group" :aria-describedby="error ? 'flow-error' : undefined">
              <legend>
                <h2 id="flow-heading" ref="heading" tabindex="-1" class="question-title">
                  {{ page.q.label }}
                </h2>
                <span class="question-help">{{ questionKind(page.q).help }}</span>
              </legend>
              <ul class="rating-list">
                <li v-for="(day, di) in pollDates(page.q)" :key="day" class="rating-row" :style="{ '--i': di }">
                  <span class="rating-option" :id="`poll-label-${day}`">{{ longDate(day) }}</span>
                  <div class="rating-scale poll-scale" role="radiogroup" :aria-labelledby="`poll-label-${day}`">
                    <label
                      v-for="level in pollLevels"
                      :key="level.value"
                      :class="[
                        'rating-step',
                        `poll-${level.value}`,
                        { on: pollOf(page.q.question_id, day) === level.value },
                      ]"
                    >
                      <input
                        type="radio"
                        :name="`poll-${page.q.question_id}-${day}`"
                        :value="level.value"
                        :checked="pollOf(page.q.question_id, day) === level.value"
                        @change="mark(page.q.question_id, day, level.value)"
                      />
                      <span>{{ level.label }}</span>
                    </label>
                  </div>
                </li>
              </ul>
            </fieldset>
          </template>
          <template v-else-if="page.q.answer_format === 'option_rating'">
            <fieldset class="answer-group" :aria-describedby="error ? 'flow-error' : undefined">
              <legend>
                <h2 id="flow-heading" ref="heading" tabindex="-1" class="question-title">
                  {{ page.q.label }}
                </h2>
                <span class="question-help">{{ questionKind(page.q).help }}</span>
              </legend>
              <ul class="rating-list">
                <li
                  v-for="(option, oi) in snapshot.options"
                  :key="option.option_id"
                  class="rating-row"
                  :style="{ '--i': oi }"
                >
                  <span class="rating-option" :id="`rate-label-${option.option_id}`"
                    >{{ splitTitle(option.title).name
                    }}<template v-if="splitTitle(option.title).detail"
                      ><span class="sr-only"> – </span
                      ><span class="rating-detail">{{ splitTitle(option.title).detail }}</span></template
                    ></span
                  >
                  <div class="rating-scale" role="radiogroup" :aria-labelledby="`rate-label-${option.option_id}`">
                    <label
                      v-for="level in ratingLevels"
                      :key="level.value"
                      :class="['rating-step', { on: ratingOf(page.q.question_id, option.option_id) === level.value }]"
                    >
                      <input
                        type="radio"
                        :name="`rate-${page.q.question_id}-${option.option_id}`"
                        :value="level.value"
                        :checked="ratingOf(page.q.question_id, option.option_id) === level.value"
                        @change="rate(page.q.question_id, option.option_id, level.value)"
                      />
                      <span>{{ level.label }}</span>
                    </label>
                  </div>
                </li>
              </ul>
            </fieldset>
          </template>
          <template
            v-else-if="['choice', 'multi_choice', 'boolean', 'date_intervals'].includes(page.q.answer_format || '')"
          >
            <fieldset class="answer-group" :aria-describedby="error ? 'flow-error' : undefined">
              <legend>
                <h2 id="flow-heading" ref="heading" tabindex="-1" class="question-title">
                  {{ page.q.label }}
                </h2>
                <span class="question-help">{{ questionKind(page.q).help }}</span>
              </legend>
              <div v-if="page.q.answer_format === 'choice'" class="choice-list stacked">
                <label v-for="choice in page.q.choices" :key="choiceId(choice)" class="choice-option"
                  ><input
                    type="radio"
                    :name="page.q.question_id"
                    v-model="values[page.q.question_id]"
                    :value="choiceId(choice)"
                  />{{ choiceLabel(choice) }}</label
                >
              </div>
              <div v-else-if="page.q.answer_format === 'multi_choice'" class="choice-list stacked">
                <label v-for="choice in page.q.choices" :key="choiceId(choice)" class="choice-option"
                  ><input type="checkbox" v-model="values[page.q.question_id]" :value="choiceId(choice)" />{{
                    choiceLabel(choice)
                  }}</label
                >
              </div>
              <div v-else-if="page.q.answer_format === 'boolean'" class="choice-list binary">
                <label class="choice-option"
                  ><input
                    type="radio"
                    :name="page.q.question_id"
                    v-model="values[page.q.question_id]"
                    :value="true"
                  />Yes</label
                >
                <label class="choice-option"
                  ><input
                    type="radio"
                    :name="page.q.question_id"
                    v-model="values[page.q.question_id]"
                    :value="false"
                  />No</label
                >
              </div>
              <div v-else class="date-pair">
                <label>Available from<input type="date" v-model="dates[page.q.question_id]!.start" /></label
                ><label
                  >Through<input
                    type="date"
                    v-model="dates[page.q.question_id]!.end"
                    :min="dates[page.q.question_id]!.start"
                /></label>
              </div>
            </fieldset>
          </template>
          <template v-else>
            <h2 id="flow-heading" ref="heading" tabindex="-1" class="question-title">
              <label :for="`answer-${page.q.question_id}`">{{ page.q.label }}</label>
            </h2>
            <p :id="`help-${page.q.question_id}`" class="question-help">{{ questionKind(page.q).help }}</p>
            <div v-if="page.q.answer_format === 'number'" class="number-field">
              <input
                :id="`answer-${page.q.question_id}`"
                v-model.number="values[page.q.question_id]"
                type="number"
                step="any"
                inputmode="decimal"
                placeholder="0"
                :aria-describedby="describedBy(page.q)"
              />
              <span v-if="page.q.mapping?.unit" class="unit">{{ page.q.mapping.unit }}</span>
            </div>
            <div v-else class="text-answer">
              <textarea
                :id="`answer-${page.q.question_id}`"
                :value="textValue(page.q)"
                @input="values[page.q.question_id] = ($event.target as HTMLTextAreaElement).value"
                rows="4"
                :maxlength="textLimit"
                placeholder="Write your answer in your own words"
                :aria-describedby="describedBy(page.q)"
                @keydown.ctrl.enter.exact.prevent="next"
                @keydown.meta.enter.exact.prevent="next"
              ></textarea>
              <div class="text-answer-foot" aria-hidden="true">
                <span class="shortcut"
                  ><kbd>{{ submitKey }}</kbd> + <kbd>Enter</kbd> to continue</span
                >
                <span :class="['char-count', { near: textLength(page.q) > textLimit * 0.9 }]"
                  >{{ textLength(page.q) }} / {{ textLimit }}</span
                >
              </div>
            </div>
          </template>
          <fieldset v-if="weighable(page.q)" class="importance">
            <legend>How much does this matter to you?</legend>
            <p class="helper-text">This only changes how much your own answer counts.</p>
            <div class="importance-scale">
              <label
                v-for="level in importanceLevels"
                :key="level.value"
                :class="['importance-step', { on: (importances[page.q.question_id] || 'normal') === level.value }]"
              >
                <input
                  type="radio"
                  :name="`importance-${page.q.question_id}`"
                  :value="level.value"
                  :checked="(importances[page.q.question_id] || 'normal') === level.value"
                  @change="importances[page.q.question_id] = level.value"
                />
                <span>{{ level.label }}</span>
              </label>
            </div>
          </fieldset>
          <Transition name="reveal"
            ><p v-if="error" id="flow-error" role="alert" class="error">{{ error }}</p></Transition
          >
          <div class="flow-actions split">
            <button type="button" class="btn-quiet" @click="back"><UiIcon name="back" />Back</button>
            <button type="submit" class="btn-primary btn-large">
              {{ busy ? 'Saving…' : answered(page.q) || page.q.required ? 'Next' : 'Skip'
              }}<UiIcon v-if="!busy" name="arrow" />
            </button>
          </div>
          <details v-if="guided" class="done-options">
            <summary>See the options ({{ snapshot.options.length }})</summary>
            <OptionCards :options="snapshot.options" :currency="snapshot.currency" :round-id="roundId" compact />
          </details>
        </fieldset>
      </form>

      <!-- Optional extras -->
      <form v-else-if="page.kind === 'extras'" key="extras" class="flow-page" @submit.prevent="next">
        <fieldset :disabled="busy || closed">
          <h2 id="flow-heading" ref="heading" tabindex="-1" class="question-title">
            Anything else the organiser should know?
          </h2>
          <p class="lede">Both are optional.</p>
          <fieldset class="answer-group restrictions">
            <legend>Can you take part in every option?</legend>
            <p class="helper-text restriction-hint">Choosing “I can’t join this” rules the option out for the group.</p>
            <div v-for="option in snapshot.options" :key="option.option_id" class="restriction-row">
              <span>{{ option.title }}</span>
              <select v-model="flags[option.option_id]" :aria-label="`${option.title}: can you take part?`">
                <option value="">I can join</option>
                <option value="CANNOT_JOIN">I can’t join this</option>
                <option value="NEEDS_INFORMATION">I need more information</option>
              </select>
            </div>
          </fieldset>
          <p v-if="snapshot.execution_mode === 'scheduled'" class="helper-text">
            Enter exact local availability times. Times are sent with their UTC instant.
          </p>
          <div v-if="snapshot.execution_mode === 'scheduled'" class="date-pair">
            <label>Available from<input type="datetime-local" v-model="availableStart" /></label
            ><label>Until<input type="datetime-local" v-model="availableEnd" /></label>
          </div>
          <label class="note-field"
            >Private note <span class="optional">(only you can see this)</span
            ><textarea
              v-model="privateNote"
              maxlength="1000"
              placeholder="Anything you’d like to keep with your own response"
            /><span class="char-count" aria-hidden="true">{{ privateNote.length }} / 1000</span></label
          >
          <Transition name="reveal"
            ><p v-if="error" role="alert" class="error">{{ error }}</p></Transition
          >
          <div class="flow-actions split">
            <button type="button" class="btn-quiet" @click="back"><UiIcon name="back" />Back</button>
            <button type="submit" class="btn-primary btn-large">
              {{ busy ? 'Saving…' : 'Review answers' }}<UiIcon v-if="!busy" name="arrow" />
            </button>
          </div>
          <details v-if="guided" class="done-options">
            <summary>See the options ({{ snapshot.options.length }})</summary>
            <OptionCards :options="snapshot.options" :currency="snapshot.currency" :round-id="roundId" compact />
          </details>
        </fieldset>
      </form>

      <!-- Review and submit -->
      <form v-else-if="page.kind === 'review'" key="review" class="flow-page" @submit.prevent="submit">
        <h2 id="flow-heading" ref="heading" tabindex="-1" class="question-title">Review your answers</h2>
        <p class="lede">Check everything before you submit. You can change your answers until collection closes.</p>
        <dl class="answer-summary">
          <div v-for="(q, i) in snapshot.questions" :key="q.question_id" class="rise" :style="{ '--i': i }">
            <dt>{{ q.label }}</dt>
            <dd>
              <span :class="{ muted: !answered(q) }">{{ answerText(q) }}</span
              ><button v-if="!closed" type="button" class="btn-quiet btn-small" @click="go(questionPage(i))">
                Change<span class="sr-only"> answer to {{ q.label }}</span>
              </button>
            </dd>
          </div>
          <div v-if="flagCount || privateNote" class="rise" :style="{ '--i': total }">
            <dt>Extras</dt>
            <dd>
              <span>{{
                [
                  flagCount ? `${flagCount} option ${flagCount === 1 ? 'restriction' : 'restrictions'}` : '',
                  privateNote ? 'Private note added' : '',
                ]
                  .filter(Boolean)
                  .join(' · ')
              }}</span
              ><button v-if="!closed" type="button" class="btn-quiet btn-small" @click="go(pages.length - 2)">
                Change<span class="sr-only"> extras</span>
              </button>
            </dd>
          </div>
        </dl>

        <Transition name="reveal"
          ><p v-if="error" role="alert" class="error">{{ error }}</p></Transition
        >
        <p v-if="closed" class="callout">
          {{
            unsupportedEditor
              ? 'This response is read-only to preserve its availability windows.'
              : 'This round is closed. Your submitted response remains available here.'
          }}
        </p>
        <div v-else class="flow-actions split">
          <button type="button" class="btn-quiet" @click="back"><UiIcon name="back" />Back</button>
          <button type="submit" class="btn-primary btn-large" :disabled="busy">
            {{
              busyAction === 'submit'
                ? 'Submitting…'
                : draft.status === 'SUBMITTED'
                  ? 'Update response'
                  : 'Submit response'
            }}<UiIcon v-if="busyAction !== 'submit'" name="check" />
          </button>
        </div>
      </form>

      <!-- Submitted -->
      <div v-else key="done" class="flow-page done">
        <p class="done-status"><UiIcon name="check" />Submitted</p>
        <h2 id="flow-heading" ref="heading" tabindex="-1" class="question-title">Your response is in</h2>
        <p class="lede">
          Thanks{{ name ? `, ${name}` : '' }}. Only you can see these answers. When the organiser closes the round, the
          options are ranked using everyone’s answers and the result appears on this page.
        </p>
        <p v-if="dueText && !overdue" class="done-due">{{ dueText }}. You can change your answers until then.</p>

        <div class="done-answers">
          <h3>Your answers</h3>
          <dl>
            <div v-for="q in snapshot.questions" :key="q.question_id">
              <dt>{{ q.label }}</dt>
              <dd :class="{ muted: !answered(q) }">{{ answerText(q) }}</dd>
            </div>
          </dl>
        </div>

        <div class="flow-actions">
          <button v-if="guided" class="btn-primary" @click="emit('refresh')">
            <UiIcon name="refresh" />Check for results
          </button>
          <button @click="go(pages.length - 1)">Edit my response</button>
        </div>
        <p class="return-line">
          <span>On another phone or computer?</span>
          <button type="button" class="btn-quiet btn-small" @click="copyReturn">
            <UiIcon :name="returnCopied ? 'check' : 'link'" />{{
              returnCopied ? 'Return link copied' : 'Copy my return link'
            }}
          </button>
        </p>
        <details v-if="guided" class="done-options">
          <summary>See the options again</summary>
          <OptionCards :options="snapshot.options" :currency="snapshot.currency" :round-id="roundId" compact />
        </details>
      </div>
    </Transition>
  </section>
  <section v-else-if="error" class="response-flow">
    <p role="alert" class="error">{{ error }}</p>
    <button @click="load">Reload response</button>
  </section>
  <div v-else class="response-flow" role="status">
    <p class="muted">Loading your response…</p>
    <div class="skeleton tall" aria-hidden="true"></div>
    <div class="skeleton" aria-hidden="true"></div>
  </div>
</template>
<script setup lang="ts">
import UiIcon from './UiIcon.vue';
import OptionCards from './OptionCards.vue';
import { ref, reactive, computed, nextTick, onMounted, watch } from 'vue';
import { checkpointKey, readCheckpoint, writeCheckpoint, removeCheckpoint } from '@/services/checkpoints';
import { apiService } from '@/services/api';
import { returnLink } from '@/services/returnLink';
import { splitTitle } from '@/services/labels';
import { useAuthStore } from '@/stores/auth';
import type { Snapshot, Draft, Answer, Choice, DateAnswer, Importance, PublishedQuestion } from '@/types/form';
const props = withDefaults(
  defineProps<{
    roundId: string;
    snapshot: Snapshot;
    title?: string;
    description?: string;
    guided?: boolean;
    deadline?: string | null;
  }>(),
  { title: '', description: '', guided: false, deadline: null },
);
const overdue = computed(() => !!props.deadline && Date.parse(props.deadline) <= Date.now());
const dueText = computed(() =>
  props.deadline
    ? overdue.value
      ? 'The deadline has passed, but you can still answer until collection closes.'
      : `Answers due ${new Date(props.deadline).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}`
    : '',
);
const emit = defineEmits<{ (e: 'saved'): void; (e: 'refresh'): void }>();
const auth = useAuthStore();
const name = auth.username;
const returnCopied = ref(false);
async function copyReturn() {
  try {
    await navigator.clipboard.writeText(returnLink(auth.userID, auth.token, props.roundId));
    returnCopied.value = true;
    setTimeout(() => {
      returnCopied.value = false;
    }, 2400);
  } catch {
    error.value = 'Clipboard unavailable. Open Session details to copy your return link.';
  }
}
// Older rounds stored the plan title as the question; show nothing twice.
const question = computed(() =>
  props.snapshot.decision_question && props.snapshot.decision_question !== props.title
    ? props.snapshot.decision_question
    : props.title,
);
type AnswerValue = string | number | boolean | string[] | Record<string, number>;
type Page =
  | { kind: 'intro' }
  | { kind: 'question'; q: PublishedQuestion; index: number }
  | { kind: 'extras' }
  | { kind: 'review' }
  | { kind: 'done' };
const draft = ref<Draft>();
const values = reactive<Record<string, AnswerValue>>({});
const dates = reactive<Record<string, { start: string; end: string }>>({});
const flags = reactive<Record<string, string>>({});
const importances = reactive<Record<string, Importance>>({});
const ratingLevels = [
  { value: 0, label: 'Not for me' },
  { value: 1, label: 'Meh' },
  { value: 2, label: 'Fine' },
  { value: 3, label: 'Good' },
  { value: 4, label: 'Love it' },
];
const importanceLevels: { value: Importance; label: string }[] = [
  { value: 'low', label: 'A little' },
  { value: 'normal', label: 'Somewhat' },
  { value: 'high', label: 'A lot' },
];
// Importance tilts a member's own weights; it applies to scored preferences on one detail.
function weighable(q: PublishedQuestion) {
  return (q.role || 'soft') === 'soft' && !!q.criterion && !['preferences', 'context'].includes(q.criterion);
}
const pollLevels: { value: DateAnswer; label: string }[] = [
  { value: 'yes', label: 'Works' },
  { value: 'maybe', label: 'If needed' },
  { value: 'no', label: 'Can’t' },
];
function pollDates(q: PublishedQuestion) {
  return (q.choices || [])
    .map((c) => choiceId(c))
    .filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d))
    .sort();
}
function longDate(day: string) {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  });
}
function pollOf(qid: string, day: string) {
  const v = values[qid];
  return v && typeof v === 'object' && !Array.isArray(v)
    ? (v as unknown as Record<string, DateAnswer>)[day]
    : undefined;
}
function mark(qid: string, day: string, answer: DateAnswer) {
  const v = values[qid];
  values[qid] = {
    ...(v && typeof v === 'object' && !Array.isArray(v) ? v : {}),
    [day]: answer,
  } as unknown as AnswerValue;
}
function ratingOf(qid: string, optionId: string) {
  const v = values[qid];
  return v && typeof v === 'object' && !Array.isArray(v) ? v[optionId] : undefined;
}
function rate(qid: string, optionId: string, rating: number) {
  const v = values[qid];
  values[qid] = { ...(v && typeof v === 'object' && !Array.isArray(v) ? v : {}), [optionId]: rating };
}
const availableStart = ref('');
const availableEnd = ref('');
const privateNote = ref('');
const busy = ref(false);
const busyAction = ref('');
const error = ref('');
const unsupportedEditor = ref(false);
const heading = ref<HTMLElement>();
const at = ref(0);
const direction = ref(1);
const submitted = ref(false);
let savedState = '';
let loaded = false;
const recoveryKey = checkpointKey(auth.userID, `response:${props.roundId}`);
const definition = JSON.stringify([props.snapshot.option_revision, props.snapshot.questions]);
interface ResponseRecovery {
  revision: number;
  definition: string;
  at: number;
  dirty: boolean;
  values: Record<string, AnswerValue>;
  dates: Record<string, { start: string; end: string }>;
  flags: Record<string, string>;
  note: string;
  start: string;
  end: string;
  importances?: Record<string, Importance>;
}
const recovered = readCheckpoint<ResponseRecovery>(recoveryKey);
const recoveryNotice = ref('');
watch(
  [values, dates, flags, importances, privateNote, availableStart, availableEnd, at, draft, submitted],
  () => {
    if (!loaded || !draft.value || closed.value) return;
    if (submitted.value) {
      removeCheckpoint(recoveryKey);
      return;
    }
    if (
      !writeCheckpoint(recoveryKey, {
        revision: draft.value.revision,
        definition,
        at: at.value,
        dirty: state() !== savedState,
        values,
        dates,
        flags,
        importances,
        note: privateNote.value,
        start: availableStart.value,
        end: availableEnd.value,
      })
    ) {
      recoveryNotice.value = 'Browser storage is unavailable. Use Next to save each answer before refreshing.';
    }
  },
  { deep: true, flush: 'sync' },
);

const pages = computed<Page[]>(() => [
  ...(props.guided ? [{ kind: 'intro' } as Page] : []),
  ...props.snapshot.questions.map((q, index) => ({ kind: 'question', q, index }) as Page),
  { kind: 'extras' },
  { kind: 'review' },
]);
const page = computed<Page>(() =>
  submitted.value ? { kind: 'done' } : pages.value[Math.min(at.value, pages.value.length - 1)]!,
);
const firstQuestion = computed(() => (props.guided ? 1 : 0));
function questionPage(index: number) {
  return firstQuestion.value + index;
}
const total = computed(() => props.snapshot.questions.length);
const progressValue = computed(() => (at.value - firstQuestion.value + 1) / (pages.value.length - firstQuestion.value));
const progressLabel = computed(() =>
  page.value.kind === 'question'
    ? `Question ${page.value.index + 1} of ${total.value}`
    : page.value.kind === 'extras'
      ? 'Almost done'
      : 'Review',
);

// A short name for what the question does, and one plain sentence on how the answer is used.
function questionKind(q: PublishedQuestion) {
  const extra = q.answer_format === 'multi_choice' ? ' Choose all that apply.' : '';
  if (q.answer_format === 'option_rating')
    return { name: 'Your ratings', help: 'Options you love rank higher for the group.' };
  if (q.answer_format === 'date_poll')
    return { name: 'Dates', help: 'This helps pick the date. It doesn’t change which option wins.' };
  if (q.role === 'hard') return { name: 'Requirement', help: `Options that don’t meet this are ruled out.${extra}` };
  if (q.role === 'informational')
    return { name: 'For context', help: `This is shared with the organiser and doesn’t affect the ranking.${extra}` };
  return { name: 'Preference', help: `Your answer helps rank the options.${extra}` };
}
// Written answers are stored with the rest of the response, which the server caps at 16,000 characters.
const textLimit = 2000;
const submitKey = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.userAgent) ? '⌘' : 'Ctrl';
function textValue(q: PublishedQuestion) {
  const v = values[q.question_id];
  return typeof v === 'string' ? v : '';
}
function textLength(q: PublishedQuestion) {
  return textValue(q).length;
}
function describedBy(q: PublishedQuestion) {
  return [`help-${q.question_id}`, error.value ? 'flow-error' : ''].filter(Boolean).join(' ');
}
function choiceId(choice: Choice) {
  return typeof choice === 'string' ? choice : choice.choice_id;
}
function choiceLabel(choice: Choice) {
  return typeof choice === 'string' ? choice : choice.label;
}
const closed = computed(() => unsupportedEditor.value || (!!draft.value && draft.value.round.state !== 'COLLECTING'));
const answeredCount = computed(() => answers().length);
const flagCount = computed(() => Object.values(flags).filter(Boolean).length);

function valueOf(q: PublishedQuestion) {
  const date = dates[q.question_id];
  return q.answer_format === 'date_intervals'
    ? date?.start && date?.end
      ? [{ start_date: date.start, end_date: date.end }]
      : []
    : values[q.question_id];
}
function answered(q: PublishedQuestion) {
  const v = valueOf(q);
  return !(
    v === '' ||
    v === undefined ||
    (Array.isArray(v) && !v.length) ||
    (v !== null && typeof v === 'object' && !Array.isArray(v) && !Object.keys(v).length)
  );
}
function answers(): Answer[] {
  return props.snapshot.questions.flatMap((q) =>
    answered(q)
      ? [
          {
            question_id: q.question_id,
            value: valueOf(q),
            ...(weighable(q) && importances[q.question_id] && importances[q.question_id] !== 'normal'
              ? { importance: importances[q.question_id] }
              : {}),
          },
        ]
      : [],
  );
}
function answerText(q: PublishedQuestion) {
  if (!answered(q)) return 'Not answered';
  const v = values[q.question_id];
  if (q.answer_format === 'date_intervals') {
    const d = dates[q.question_id]!;
    return `${d.start} to ${d.end}`;
  }
  if (q.answer_format === 'date_poll')
    return pollLevels
      .map((level) => {
        const days = pollDates(q)
          .filter((day) => pollOf(q.question_id, day) === level.value)
          .map(longDate);
        return days.length ? `${level.label}: ${days.join(', ')}` : '';
      })
      .filter(Boolean)
      .join(' · ');
  if (q.answer_format === 'option_rating')
    return props.snapshot.options
      .filter((o) => ratingOf(q.question_id, o.option_id) !== undefined)
      .map((o) => `${o.title}: ${ratingLevels[ratingOf(q.question_id, o.option_id)!]?.label}`)
      .join(' · ');
  const label = (id: unknown) => {
    const c = q.choices?.find((c) => choiceId(c) === id);
    return c ? choiceLabel(c) : String(id);
  };
  if (Array.isArray(v)) return v.map(label).join(', ');
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  return q.choices?.length ? label(v) : `${v}${q.mapping?.unit ? ` ${q.mapping.unit}` : ''}`;
}
function state() {
  return JSON.stringify([answers(), flags, privateNote.value, availableStart.value, availableEnd.value]);
}

async function save() {
  if (!draft.value) throw new Error('Reload your response first.');
  const list: Answer[] = answers();
  const availability =
    props.snapshot.execution_mode === 'scheduled' && availableStart.value && availableEnd.value
      ? [{ startAt: new Date(availableStart.value).toISOString(), endAt: new Date(availableEnd.value).toISOString() }]
      : draft.value.availability;
  draft.value = await apiService.saveDraft(props.roundId, {
    expectedRevision: draft.value.revision,
    acknowledgedOptionRevision: props.snapshot.option_revision,
    availability,
    budget:
      draft.value.budget.kind === 'CAP'
        ? { kind: 'CAP', capMinor: draft.value.budget.capMinor }
        : { kind: draft.value.budget.kind },
    activityAnswers: Object.entries(flags)
      .filter(([, value]) => value)
      .map(([activityId, kind]) => ({ activityId, kind })),
    privateNote: privateNote.value,
    answers: list,
  });
  savedState = state();
}
async function action(name: string, fn: () => Promise<void>) {
  if (busy.value) return false;
  busy.value = true;
  busyAction.value = name;
  error.value = '';
  try {
    await fn();
    emit('saved');
    return true;
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Request failed. Reload if another tab changed your response.';
    return false;
  } finally {
    busy.value = false;
    busyAction.value = '';
  }
}

function go(index: number) {
  direction.value = submitted.value || index >= at.value ? 1 : -1;
  error.value = '';
  submitted.value = false;
  at.value = index;
}
function back() {
  go(Math.max(0, at.value - 1));
}
function problem() {
  const p = page.value;
  if (p.kind !== 'question') return '';
  const d = dates[p.q.question_id];
  if (p.q.answer_format === 'date_intervals' && d && !!d.start !== !!d.end)
    return 'Add both dates, or leave both empty.';
  if (p.q.answer_format === 'date_intervals' && d?.start && d.end && d.end < d.start)
    return 'The second date must be on or after the first.';
  if (
    p.q.answer_format === 'number' &&
    values[p.q.question_id] !== '' &&
    !Number.isFinite(Number(values[p.q.question_id]))
  )
    return 'Enter a number.';
  if (p.q.answer_format === 'date_poll' && p.q.required && pollDates(p.q).some((day) => !pollOf(p.q.question_id, day)))
    return 'Answer every date to continue.';
  if (
    p.q.answer_format === 'option_rating' &&
    p.q.required &&
    props.snapshot.options.some((o) => ratingOf(p.q.question_id, o.option_id) === undefined)
  )
    return 'Rate every option to continue.';
  if (p.q.required && !answered(p.q)) return 'Answer this question to continue.';
  return '';
}
// Each step saves the draft, so nothing is lost if the member leaves part way.
async function next() {
  const issue = problem();
  if (issue) {
    error.value = issue;
    return;
  }
  if (!closed.value && state() !== savedState && !(await action('save', () => save()))) return;
  go(at.value + 1);
}
function focusHeading() {
  heading.value?.focus({ preventScroll: true });
}
watch(at, async () => {
  await nextTick();
  const top = document.querySelector('.response-flow');
  if (top && top.getBoundingClientRect().top < 0) top.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

async function submit() {
  const ok = await action('submit', async () => {
    if (state() !== savedState || !draft.value!.revision) await save();
    draft.value = await apiService.submit(props.roundId, draft.value!.revision);
  });
  if (ok) {
    direction.value = 1;
    submitted.value = true;
  }
}
async function copyEarlier() {
  const ok = await action('copy', async () => {
    await apiService.copyResponse(props.roundId, props.snapshot.previous_round_id!);
  });
  if (ok) {
    await load();
    recoveryNotice.value = 'Earlier answers copied as a draft. Check each answer before submitting.';
  }
}
async function load() {
  await action('load', async () => {
    const own = await apiService.draft(props.roundId);
    draft.value = own;
    privateNote.value = own.privateNote || '';
    if (
      own.availability.length > 1 ||
      own.answers.some(
        (answer) =>
          props.snapshot.questions.find((q) => q.question_id === answer.question_id)?.answer_format ===
            'date_intervals' &&
          Array.isArray(answer.value) &&
          answer.value.length > 1,
      )
    ) {
      unsupportedEditor.value = true;
      throw new Error('This response has multiple availability windows. The form is read-only here to preserve them.');
    }
    for (const q of props.snapshot.questions) {
      values[q.question_id] =
        q.answer_format === 'multi_choice'
          ? []
          : ['option_rating', 'date_poll'].includes(q.answer_format || '')
            ? {}
            : '';
      dates[q.question_id] = { start: '', end: '' };
      delete importances[q.question_id];
    }
    for (const answer of own.answers) {
      if (
        props.snapshot.questions.find((q) => q.question_id === answer.question_id)?.answer_format === 'date_intervals'
      ) {
        const ranges = answer.value as { start_date: string; end_date: string }[];
        dates[answer.question_id] = { start: ranges[0]?.start_date || '', end: ranges[0]?.end_date || '' };
      } else values[answer.question_id] = answer.value as AnswerValue;
      if (answer.importance) importances[answer.question_id] = answer.importance;
    }
    for (const option of props.snapshot.options)
      flags[option.option_id] = own.activityAnswers.find((row) => row.activityId === option.option_id)?.kind || '';
    function local(instant?: string) {
      if (!instant) return '';
      const d = new Date(instant);
      return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    }
    availableStart.value = local(own.availability[0]?.startAt);
    availableEnd.value = local(own.availability[0]?.endAt);
    savedState = state();
    if (closed.value) {
      at.value = pages.value.length - 1;
      removeCheckpoint(recoveryKey);
    } else {
      if (own.status === 'SUBMITTED') submitted.value = true;
      if (recovered && recovered.definition === definition && recovered.revision === own.revision) {
        if (recovered.dirty) {
          Object.assign(values, recovered.values);
          Object.assign(dates, recovered.dates);
          Object.assign(flags, recovered.flags);
          Object.assign(importances, recovered.importances || {});
          privateNote.value = recovered.note;
          availableStart.value = recovered.start;
          availableEnd.value = recovered.end;
          submitted.value = false;
        }
        at.value = Math.max(0, Math.min(pages.value.length - 1, recovered.at));
        // Only mention recovery when unsaved edits were actually brought back.
        if (recovered.dirty) recoveryNotice.value = 'We brought back the answers you hadn’t saved yet.';
      } else if (recovered) {
        removeCheckpoint(recoveryKey);
        recoveryNotice.value =
          'A newer response or form version was found. Loaded the saved server response instead of older browser edits.';
      }
    }
    loaded = true;
  });
}
onMounted(() => {
  void load();
});
</script>
<style scoped>
.response-flow {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 20px;
  padding: clamp(22px, 3vw, 36px);
  margin: 24px 0;
  overflow: hidden;
  scroll-margin-top: 24px;
  box-shadow: var(--shadow-sm);
}
.response-flow.guided {
  margin: 0;
  padding: 0;
  background: transparent;
  border: 0;
  box-shadow: none;
  overflow: visible;
}
.response-flow .tall {
  height: 140px;
}
.guided .flow-page:not(.intro),
.guided .flow-progress,
.guided > .callout,
.guided > .helper-text {
  max-width: 820px;
  margin-left: auto;
  margin-right: auto;
}
.guided form.flow-page,
.guided .flow-page.done {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 20px;
  padding: clamp(24px, 4vw, 48px);
  box-shadow: var(--shadow-sm);
}
.flow-progress {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 28px;
}
.flow-progress .meter {
  flex: 1;
  height: 4px;
}
.progress-text {
  color: var(--muted);
  font-size: 0.875rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.flow-page {
  min-width: 0;
}
.flow-page > fieldset {
  min-width: 0;
}
.intro-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 32px;
  padding-bottom: 28px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--line);
}
.intro-head > div:first-child {
  min-width: 0;
}
.flow-page h1 {
  font-size: clamp(2.125rem, 1.4rem + 2.2vw, 3.5rem);
  color: var(--night);
  margin-bottom: 12px;
  overflow-wrap: anywhere;
}
.flow-page h1:focus,
.flow-page h2:focus {
  outline: none;
}
.plan-context {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px 5px 10px;
  border-radius: 999px;
  background: var(--sky-50);
  border: 1px solid var(--sky-100);
  font-size: 0.875rem;
  color: var(--muted);
  margin-bottom: 14px;
}
.plan-context .ui-icon {
  width: 16px;
  height: 16px;
  color: var(--blue);
}
.plan-context strong {
  color: var(--blue-ink);
  font-weight: 600;
}
.intro-start {
  display: grid;
  justify-items: end;
  gap: 8px;
  flex-shrink: 0;
}
.intro-start .helper-text {
  margin: 0;
}
.due {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--blue-ink);
  text-align: right;
  max-width: 30ch;
}
.due.overdue {
  color: var(--warn);
}
.lede {
  color: var(--muted);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 1.0625rem;
}
.options-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 4px 24px;
  margin: 32px 0 16px;
}
.options-head .section-label {
  margin: 0;
}
.options-head .helper-text {
  margin: 0;
}
.section-label {
  font-size: 1.125rem;
  margin: 28px 0 14px;
  display: flex;
  gap: 10px;
  align-items: baseline;
}
.section-label .muted {
  font-weight: 400;
  color: var(--faint);
}
.privacy-note {
  display: flex;
  gap: 8px;
  color: var(--ink-2);
  font-size: 0.9375rem;
  margin: 24px 0 0;
}
.privacy-note .ui-icon {
  width: 18px;
  height: 18px;
  margin-top: 2px;
  color: var(--blue);
}
.question-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}
.role-tag,
.required-tag {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 0.8125rem;
  font-weight: 600;
}
.role-tag {
  background: var(--sky-50);
  color: var(--blue-ink);
}
.role-tag.hard {
  background: var(--warn-soft);
  color: var(--warn);
}
.role-tag.informational {
  background: #eef2f7;
  color: var(--muted);
}
.required-tag {
  padding: 1px 9px;
  border: 1px solid var(--line-strong);
  color: var(--muted);
}
.question-title {
  font-size: clamp(1.5rem, 1.25rem + 0.8vw, 2rem);
  font-weight: 600;
  line-height: 1.25;
  letter-spacing: -0.015em;
  color: var(--night);
  margin-bottom: 8px;
  max-width: 36ch;
  overflow-wrap: anywhere;
}
.question-help {
  display: block;
  margin: 0 0 24px;
  font-size: 1rem;
  font-weight: 400;
  color: var(--muted);
}
.question-title label {
  margin: 0;
  font-size: inherit;
  font-weight: inherit;
}
.answer-group > legend {
  width: 100%;
}
.answer-group > legend .question-title {
  margin-bottom: 8px;
}
.choice-list.stacked {
  grid-template-columns: minmax(0, 1fr);
}
.choice-list.stacked .choice-option,
.choice-list.binary .choice-option {
  min-height: 58px;
  font-size: 1.0625rem;
}
.choice-list .choice-option {
  animation: rise 420ms var(--ease-out) both;
}
.choice-list .choice-option:nth-child(2) {
  animation-delay: 40ms;
}
.choice-list .choice-option:nth-child(3) {
  animation-delay: 80ms;
}
.choice-list .choice-option:nth-child(n + 4) {
  animation-delay: 120ms;
}
.choice-list.binary {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  max-width: 460px;
}
.choice-option input[type='radio'],
.choice-option input[type='checkbox'] {
  margin-right: 14px;
}
/* Written answers: a roomy box that grows with the text. */
.text-answer textarea {
  display: block;
  min-height: 148px;
  max-height: 420px;
  padding: 14px 16px;
  font-size: 1.0625rem;
  line-height: 1.55;
  border-radius: 12px;
  resize: vertical;
  field-sizing: content;
}
.text-answer-foot {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
  font-size: 0.8125rem;
  color: var(--muted);
}
.shortcut kbd {
  padding: 1px 6px;
  border: 1px solid var(--line-strong);
  border-bottom-width: 2px;
  border-radius: 5px;
  background: var(--surface);
  font: inherit;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--ink-2);
}
.char-count.near {
  color: var(--warn);
  font-weight: 600;
}
@media (hover: none) {
  .shortcut {
    visibility: hidden;
  }
}
/* Numbers: the unit sits inside the field. */
.number-field {
  display: flex;
  align-items: center;
  max-width: 320px;
  border: 1px solid var(--control-line);
  border-radius: 12px;
  background: var(--surface);
  transition:
    border-color var(--fast) ease-out,
    box-shadow var(--fast) ease-out;
}
.number-field:hover:not(:focus-within) {
  border-color: var(--ink-2);
}
.number-field:focus-within {
  border-color: var(--blue);
  box-shadow: 0 0 0 3px rgba(21, 87, 192, 0.2);
}
.number-field input {
  border: 0;
  min-height: 56px;
  font-size: 1.1875rem;
  font-variant-numeric: tabular-nums;
  background: transparent;
}
.number-field input:focus-visible {
  box-shadow: none;
}
.unit {
  padding: 0 16px 0 4px;
  color: var(--muted);
  font-weight: 600;
}
.date-pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 240px));
  gap: 0 16px;
}
.date-pair label {
  margin: 0;
}
.flow-page .error {
  margin: 20px 0 0;
}
.flow-actions {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 32px;
  flex-wrap: wrap;
}
.flow-actions.split {
  justify-content: space-between;
  padding-top: 24px;
  border-top: 1px solid var(--line);
}
.flow-actions .helper-text {
  margin: 0;
}
.btn-large {
  min-height: 52px;
  padding: 12px 28px;
  font-size: 1.0625rem;
  min-width: 160px;
}
.rating-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}
.rating-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px 20px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 14px;
  animation: rise 420ms var(--ease-out) both;
  animation-delay: calc(min(var(--i), 8) * 50ms);
}
.rating-option {
  font-weight: 600;
  font-size: 1.0625rem;
  overflow-wrap: anywhere;
}
.rating-detail {
  display: block;
  margin-top: 2px;
  font-size: 0.875rem;
  font-weight: 400;
  color: var(--muted);
}
.rating-scale,
.importance-scale {
  display: inline-grid;
  grid-auto-flow: column;
  grid-auto-columns: 1fr;
  padding: 3px;
  border-radius: 999px;
  background: var(--sky-50);
  border: 1px solid var(--line);
}
.rating-step,
.importance-step {
  position: relative;
  margin: 0;
  cursor: pointer;
}
.rating-step input,
.importance-step input {
  position: absolute;
  opacity: 0;
  width: 1px;
  height: 1px;
}
.rating-step span,
.importance-step span {
  display: block;
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--ink-2);
  text-align: center;
  white-space: nowrap;
  transition:
    background-color 200ms var(--ease-out),
    color 200ms var(--ease-out),
    box-shadow 200ms var(--ease-out);
}
.rating-step:hover span,
.importance-step:hover span {
  color: var(--blue-ink);
}
.rating-step.on span,
.importance-step.on span {
  background: var(--blue);
  color: #fff;
  box-shadow: var(--shadow-sm);
}
.rating-step:has(:focus-visible) span,
.importance-step:has(:focus-visible) span {
  outline: 2px solid var(--blue);
  outline-offset: 2px;
}
.poll-scale .poll-yes.on span {
  background: #1f7a4d;
}
.poll-scale .poll-no.on span {
  background: #8a3340;
}
/* Importance is a small panel of its own, not a line through the form. */
.importance {
  margin-top: 28px;
  padding: 18px 20px 20px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--surface-2);
}
.importance > legend {
  float: left;
  width: 100%;
  margin: 0;
  font-size: 1rem;
}
.importance > .helper-text {
  clear: both;
  margin: 2px 0 14px;
}
.importance-scale {
  display: grid;
  width: 100%;
  max-width: 440px;
  background: var(--surface);
}
.restrictions {
  margin-top: 8px;
}
.restrictions > legend {
  margin-bottom: 4px;
}
.restriction-hint {
  margin: 0 0 12px;
}
.restriction-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 260px);
  gap: 12px;
  align-items: center;
  padding: 10px 0;
  border-top: 1px solid var(--line);
  font-size: 1rem;
  overflow-wrap: anywhere;
}
.note-field {
  position: relative;
  margin-top: 28px;
}
.note-field .char-count {
  position: absolute;
  right: 0;
  top: 0;
  font-size: 0.8125rem;
  font-weight: 400;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.answer-summary {
  margin: 8px 0 0;
  border: 1px solid var(--line);
  border-radius: 14px;
  overflow: hidden;
}
.answer-summary > div {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 16px;
  padding: 14px 18px;
  font-size: 0.9375rem;
}
.answer-summary > div + div {
  border-top: 1px solid var(--line);
}
.answer-summary dt {
  color: var(--muted);
  overflow-wrap: anywhere;
}
.answer-summary dd {
  margin: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.answer-summary dd .muted {
  font-weight: 400;
}
.answer-summary dd button {
  flex-shrink: 0;
}
.flow-notice {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 auto 16px;
  padding: 6px 6px 6px 14px;
  border: 1px solid var(--sky-200);
  border-radius: 12px;
  background: var(--sky-50);
  color: var(--blue-ink);
  font-size: 0.9375rem;
}
.flow-notice > span {
  flex: 1;
}
.flow-notice > .ui-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}
.flow-notice button {
  width: 36px;
  min-height: 36px;
  padding: 0;
  justify-content: center;
  color: var(--blue-ink);
}
.guided > .flow-notice {
  max-width: 820px;
}
.done-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 10px;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--ok);
}
.done-status .ui-icon {
  width: 16px;
  height: 16px;
  stroke-width: 2.4;
}
.done .lede {
  max-width: 60ch;
  white-space: normal;
}
.done-due {
  margin: 4px 0 0;
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--ink-2);
}
.done-answers {
  margin-top: 28px;
}
.done-answers h3 {
  margin: 0 0 8px;
  font-size: 0.8125rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--faint);
}
.done-answers dl {
  margin: 0;
  border-top: 1px solid var(--line);
}
.done-answers dl > div {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);
  gap: 4px 24px;
  padding: 12px 0;
  border-bottom: 1px solid var(--line);
  font-size: 0.9375rem;
}
.done-answers dt {
  color: var(--muted);
  overflow-wrap: anywhere;
}
.done-answers dd {
  margin: 0;
  color: var(--ink);
  white-space: pre-line;
  overflow-wrap: anywhere;
}
.done-answers dd.muted {
  color: var(--faint);
}
.return-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px 6px;
  margin: 16px 0 0;
  font-size: 0.875rem;
  color: var(--muted);
}
.return-line button {
  min-height: 32px;
  padding: 4px 8px;
}
.done-options {
  margin-top: 32px;
  text-align: left;
}
.done-options[open] summary {
  margin-bottom: 12px;
}
@media (max-width: 760px) {
  .response-flow {
    padding: 20px 18px;
    margin: 16px 0;
  }
  .guided form.flow-page,
  .guided .flow-page.done {
    padding: 22px 18px;
    border-radius: 16px;
  }
  .intro-head {
    flex-direction: column;
    align-items: stretch;
    gap: 20px;
  }
  .intro-start {
    justify-items: stretch;
  }
  .flow-actions.split {
    flex-direction: column-reverse;
    align-items: stretch;
  }
  .flow-actions.split button,
  .flow-actions .btn-large {
    width: 100%;
  }
  .done-answers dl > div {
    grid-template-columns: minmax(0, 1fr);
  }
  .done .flow-actions {
    flex-direction: column;
    align-items: stretch;
  }
  .date-pair {
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;
  }
  .rating-row {
    grid-template-columns: minmax(0, 1fr);
  }
  .rating-scale,
  .importance-scale {
    display: grid;
    width: 100%;
  }
  .rating-step span,
  .importance-step span {
    padding: 8px 4px;
    font-size: 0.8125rem;
    white-space: normal;
    line-height: 1.2;
  }
  .restriction-row,
  .answer-summary > div {
    grid-template-columns: minmax(0, 1fr);
    gap: 4px;
  }
}
</style>
