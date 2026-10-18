<template>
  <div class="results-layout">
    <TopBar />

    <div class="results-wrapper">
      <!-- Loading -->
      <div v-if="isLoading" class="card state-card">Loading results…</div>

      <!-- Error -->
      <div v-else-if="loadError || !activeForm" class="card state-card error">
        <h3>We couldn't load the results</h3>
        <p>{{ loadError || 'The form may have been removed or the link is incorrect.' }}</p>
        <button type="button" class="btn-secondary" @click="loadResults">Try again</button>
      </div>

      <template v-else>
        <!-- Header -->
        <div class="results-header">
          <div>
            <h2>{{ activeForm.title }}</h2>
            <p class="subtitle">Results</p>
          </div>
          <div class="header-actions">
            <button type="button" class="btn-secondary" :disabled="isRefreshing" @click="loadResults">
              {{ isRefreshing ? 'Refreshing…' : '↻ Refresh' }}
            </button>
            <button v-if="showNavigation" type="button" class="btn-secondary" @click="emit('navigate', 'dashboard')">
              Back to Dashboard
            </button>
          </div>
        </div>

        <!-- Participation progress -->
        <div class="card progress-card">
          <div class="progress-top">
            <div>
              <span class="stat-number">{{ responses.length }}</span>
              <span class="stat-label">
                {{ expectedParticipants ? `of ${expectedParticipants} participants responded` : (responses.length === 1 ? 'response' : 'responses') }}
              </span>
            </div>
            <span v-if="allResponded" class="status-badge complete">✓ Everyone has responded</span>
            <span v-else-if="expectedParticipants" class="status-badge pending">
              Waiting on {{ expectedParticipants - responses.length }} more
            </span>
          </div>
          <div v-if="expectedParticipants" class="progress-track">
            <div class="progress-fill" :style="{ width: participationPercent + '%' }"></div>
          </div>
          <p v-if="expectedParticipants && !allResponded" class="hint">
            Results below are based on the responses received so far and may change.
          </p>
        </div>

        <!-- Empty state -->
        <div v-if="responses.length === 0" class="card state-card">
          <h3>No responses yet</h3>
          <p>Share your form link and results will appear here as people respond.</p>
        </div>

        <template v-else>
          <!-- Top picks overview -->
          <div class="card summary-card">
            <h3 class="section-title">🏆 Top picks</h3>
            <div class="summary-list">
              <div v-for="r in questionResults" :key="r.index" class="summary-row">
                <span class="question-number">Q{{ r.index + 1 }}</span>
                <div class="summary-text">
                  <span class="summary-question">{{ r.question.title }}</span>
                  <span v-if="r.topLabels.length" class="summary-answer">
                    {{ r.topLabels.join(', ') }}
                    <span v-if="r.topLabels.length > 1" class="tie-tag">tie</span>
                    <span v-if="r.topCount" class="summary-count">· {{ r.topCount }} {{ r.topCount === 1 ? 'vote' : 'votes' }}</span>
                  </span>
                  <span v-else-if="r.type === 'Short answer'" class="summary-answer muted">
                    {{ r.textAnswers.length }} written {{ r.textAnswers.length === 1 ? 'reply' : 'replies' }}
                  </span>
                  <span v-else class="summary-answer muted">No answers yet</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Per-question breakdown -->
          <h3 class="section-title">Breakdown by question</h3>

          <div v-for="r in questionResults" :key="r.index" class="card question-card">
            <div class="question-header">
              <span class="question-number">Q{{ r.index + 1 }}</span>
              <div class="question-title-group">
                <h4>{{ r.question.title }}</h4>
                <p v-if="r.question.description" class="question-subtext">{{ r.question.description }}</p>
              </div>
              <span class="type-badge">{{ r.type }}</span>
            </div>

            <!-- Short answer: list the replies -->
            <div v-if="r.type === 'Short answer'">
              <p v-if="r.textAnswers.length === 0" class="hint">No replies yet.</p>
              <ul v-else class="text-answers">
                <li v-for="(t, i) in r.textAnswers" :key="i">
                  <span class="text-body">{{ t.text }}</span>
                  <span class="text-author">— {{ t.name }}</span>
                </li>
              </ul>
            </div>

            <!-- Everything else: bar chart -->
            <div v-else>
              <p v-if="r.tallies.length === 0" class="hint">No answers yet.</p>
              <div v-else class="bar-list">
                <div v-for="t in r.tallies" :key="t.label" class="bar-row" :class="{ top: t.isTop }">
                  <div class="bar-label">
                    <span>{{ r.type === 'Duration' ? t.displayLabel : t.label }}</span>
                    <span v-if="t.isTop" class="top-tag">Most popular</span>
                  </div>
                  <div class="bar-track">
                    <div class="bar-fill" :style="{ width: t.percent + '%' }"></div>
                  </div>
                  <span class="bar-value">{{ t.count }} · {{ Math.round(t.percent) }}%</span>
                </div>
              </div>
              <p v-if="r.tallies.length" class="hint">
                Based on {{ r.respondentCount }} {{ r.respondentCount === 1 ? 'response' : 'responses' }}.
                <template v-if="r.type === 'Multiple choice' || r.type === 'Duration'">
                  Participants could pick more than one, so percentages can add up to more than 100%.
                </template>
              </p>
            </div>
          </div>

          <!-- Individual responses -->
          <div class="card">
            <h3 class="section-title">Who responded</h3>
            <div class="respondent-list">
              <div v-for="(resp, i) in responses" :key="i" class="respondent">
                <span class="avatar">{{ initials(resp.participantName) }}</span>
                <div>
                  <span class="respondent-name">{{ resp.participantName }}</span>
                  <span class="respondent-time">{{ formatSubmitted(resp.submittedAt) }}</span>
                </div>
              </div>
            </div>
          </div>
        </template>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import TopBar from './TopBar.vue';
import type { Form } from '@/types/form';
// import { apiService } from '@/services/api.ts';   // TODO: uncomment when backend is connected

/* ----------------------------- props / emits ----------------------------- */

const props = withDefaults(
  defineProps<{
    /** Pass the form directly, or leave empty to fetch it by formId. */
    form?: Form | null;
    formId?: string;
    showNavigation?: boolean;
  }>(),
  { form: null, formId: '', showNavigation: true }
);

const emit = defineEmits<{
  (e: 'navigate', view: string): void;
}>();

/* --------------------------------- types --------------------------------- */

// TODO: move to '@/types/form' once the backend contract is fixed.
// Must match the payload produced by FormParticipantView.
type AnswerValue = string | string[];

interface ResponsePayload {
  formId: string;
  participantName: string;
  submittedAt: string;
  answers: { questionIndex: number; questionTitle: string; type: string; value: AnswerValue }[];
}

interface Tally {
  label: string;
  displayLabel: string;
  count: number;
  percent: number; // share of respondents who answered this question
  isTop: boolean;
}

interface QuestionResult {
  index: number;
  question: Form['questions'][number];
  type: string;
  respondentCount: number;
  tallies: Tally[];
  topLabels: string[];
  topCount: number;
  textAnswers: { name: string; text: string }[];
}

/* --------------------------------- state --------------------------------- */

const activeForm = ref<Form | null>(props.form ?? null);
const responses = ref<ResponsePayload[]>([]);
const expectedParticipants = ref<number | null>(null);

const isLoading = ref(false);
const isRefreshing = ref(false);
const loadError = ref('');

/* ------------------------------ placeholders ------------------------------ */

// Placeholder data so the page works before the backend exists.
const mockForm: Form = {
  id: 'mock-form-id',
  title: 'Europe Summer Trip 2026',
  description: '',
  startDateRange: '2026-07-01',
  endDateRange: '2026-07-07',
  location: 'Zoom',
  category: 'Travel',
  state: 'Collecting',
  questions: [
    { title: 'Which activities interest you?', description: '', type: 'Multiple choice', options: ['Museums', 'Hiking', 'Food tours'] },
    { title: 'Preferred travel style?', description: '', type: 'Single choice', options: ['Relaxed', 'Packed itinerary'] },
    { title: 'When are you available?', description: '', type: 'Duration', options: [] },
    { title: 'Where should we meet?', description: '', type: 'Location', options: ['Vivocity', 'Botanic Gardens'], metadata: { allowCustomSuggestions: true } },
    { title: 'Budget per person', description: '', type: 'Budget', options: ['$1000 - $2000', '$2000 - $3500'] },
    { title: 'Anything else?', description: '', type: 'Short answer', options: [] },
  ],
} as Form;

const mkResponse = (
  name: string,
  vals: [AnswerValue, AnswerValue, AnswerValue, AnswerValue, AnswerValue, AnswerValue],
  at: string
): ResponsePayload => ({
  formId: 'mock-form-id',
  participantName: name,
  submittedAt: at,
  answers: mockForm.questions.map((q, i) => ({ questionIndex: i, questionTitle: q.title, type: q.type, value: vals[i] })),
});

const mockResponses: ResponsePayload[] = [
  mkResponse('Alice', [['Museums', 'Food tours'], 'Relaxed', ['2026-07-03', '2026-07-04', '2026-07-05'], 'Vivocity', '$2000 - $3500', 'Vegetarian please'], '2026-10-17T09:12:00+08:00'),
  mkResponse('Ben', [['Hiking', 'Food tours'], 'Packed itinerary', ['2026-07-04', '2026-07-05'], 'Botanic Gardens', '$1000 - $2000', ''], '2026-10-17T11:40:00+08:00'),
  mkResponse('Chloe', [['Museums', 'Food tours'], 'Relaxed', ['2026-07-02', '2026-07-04', '2026-07-05', '2026-07-06'], 'Vivocity', '$2000 - $3500', 'Window seat!'], '2026-10-17T20:05:00+08:00'),
  mkResponse('Daniel', [['Food tours'], 'Relaxed', ['2026-07-04', '2026-07-05'], 'Marina Bay', '$2000 - $3500', ''], '2026-10-18T08:30:00+08:00'),
];

const loadResults = async (): Promise<void> => {
  const firstLoad = !activeForm.value && !responses.value.length;
  if (firstLoad) isLoading.value = true;
  else isRefreshing.value = true;
  loadError.value = '';

  try {
    // TODO: replace with real backend calls once available.
    // if (!props.form) activeForm.value = await apiService.getFormById(props.formId);
    // const data = await apiService.getFormResponses(props.formId);
    // responses.value = data.responses;
    // expectedParticipants.value = data.expectedParticipants;   // null if the backend doesn't track invitees

    await new Promise((resolve) => setTimeout(resolve, 300)); // simulate latency
    if (!props.form) activeForm.value = { ...mockForm, id: props.formId || mockForm.id };
    responses.value = mockResponses;
    expectedParticipants.value = 5;
  } catch (err) {
    console.error('Failed to load results:', err);
    loadError.value = 'Something went wrong while loading the results.';
  } finally {
    isLoading.value = false;
    isRefreshing.value = false;
  }
};

watch(() => props.form, (f) => { if (f) activeForm.value = f; });
onMounted(loadResults);

/* ----------------------------- participation ----------------------------- */

const allResponded = computed(
  () => !!expectedParticipants.value && responses.value.length >= expectedParticipants.value
);

const participationPercent = computed(() =>
  expectedParticipants.value
    ? Math.min(100, (responses.value.length / expectedParticipants.value) * 100)
    : 0
);

/* ------------------------------- aggregation ------------------------------ */

// Parse "YYYY-MM-DD" as a local date to avoid timezone off-by-one errors.
const parseLocalDate = (s: string): Date => {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
};

const formatDateLabel = (iso: string): string => {
  const d = parseLocalDate(iso);
  return isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
};

const toArray = (v: AnswerValue | undefined): string[] =>
  (Array.isArray(v) ? v : v ? [v] : []).map((s) => s.trim()).filter(Boolean);

const questionResults = computed<QuestionResult[]>(() => {
  const form = activeForm.value;
  if (!form) return [];

  return form.questions.map((question, index) => {
    const type = question.type as string;

    // Collect every response's answer to this question.
    const entries = responses.value
      .map((r) => ({ name: r.participantName, value: r.answers.find((a) => a.questionIndex === index)?.value }))
      .filter((e) => toArray(e.value).length > 0);

    const base = { index, question, type, respondentCount: entries.length };

    if (type === 'Short answer') {
      return {
        ...base,
        tallies: [],
        topLabels: [],
        topCount: 0,
        textAnswers: entries.map((e) => ({ name: e.name, text: toArray(e.value).join(' ') })),
      };
    }

    // Count votes. Keys are lower-cased so custom location suggestions like
    // "marina bay" and "Marina Bay" are merged; the first spelling is displayed.
    const counts = new Map<string, { label: string; count: number }>();
    entries.forEach((e) => {
      // A participant counts once per distinct option.
      const unique = new Map(toArray(e.value).map((v) => [v.toLowerCase(), v]));
      unique.forEach((label, key) => {
        const existing = counts.get(key);
        if (existing) existing.count++;
        else counts.set(key, { label, count: 1 });
      });
    });

    const topCount = Math.max(0, ...[...counts.values()].map((c) => c.count));

    let tallies: Tally[] = [...counts.values()].map((c) => ({
      label: c.label,
      displayLabel: type === 'Duration' ? formatDateLabel(c.label) : c.label,
      count: c.count,
      percent: entries.length ? (c.count / entries.length) * 100 : 0,
      isTop: c.count === topCount && topCount > 0,
    }));

    // Dates read best in calendar order; everything else sorts by popularity.
    tallies =
      type === 'Duration'
        ? tallies.sort((a, b) => a.label.localeCompare(b.label))
        : tallies.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));

    const topLabels = tallies.filter((t) => t.isTop).map((t) => t.displayLabel);

    return { ...base, tallies, topLabels, topCount, textAnswers: [] };
  });
});

/* -------------------------------- formatting ------------------------------- */

const initials = (name: string): string =>
  name
    .trim()
    .split(/\s+/)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .slice(0, 2)
    .join('') || '?';

const formatSubmitted = (iso: string): string => {
  const d = new Date(iso);
  return isNaN(d.getTime())
    ? ''
    : d.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' });
};
</script>

<style scoped>
.results-layout {
  min-height: 100vh;
  background-color: #EFECE9;
}

.results-wrapper {
  padding: 32px;
  max-width: 820px;
  margin: 0 auto;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 24px;
}

.results-header h2 { color: #2D3748; }

.subtitle {
  color: #718096;
  font-size: 0.9rem;
  margin-top: 2px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.card {
  background: white;
  border-radius: 8px;
  padding: 24px;
  margin-bottom: 20px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
  border: 1px solid #E2E8F0;
}

.section-title {
  color: #2D3748;
  margin-bottom: 14px;
}

.hint {
  font-size: 0.8rem;
  color: #718096;
  margin-top: 10px;
}

/* Progress */
.progress-card { border-top: 4px solid #3182CE; }

.progress-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.stat-number {
  font-size: 1.8rem;
  font-weight: 800;
  color: #2D3748;
  margin-right: 8px;
}

.stat-label { color: #4A5568; }

.status-badge {
  font-size: 0.8rem;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 12px;
}

.status-badge.complete { background: #C6F6D5; color: #22543D; }
.status-badge.pending { background: #FEEBC8; color: #7B341E; }

.progress-track {
  height: 8px;
  background: #EDF2F7;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #38A169;
  border-radius: 4px;
  transition: width 0.3s ease;
}

/* Top picks */
.summary-card { border-left: 4px solid #38A169; }

.summary-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.summary-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.summary-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.summary-question {
  font-size: 0.8rem;
  color: #718096;
}

.summary-answer {
  font-weight: 700;
  color: #2D3748;
}

.summary-answer.muted { font-weight: 500; color: #A0AEC0; }
.summary-count { font-weight: 500; color: #718096; font-size: 0.85rem; }

.tie-tag {
  font-size: 0.7rem;
  background: #FEEBC8;
  color: #7B341E;
  padding: 1px 6px;
  border-radius: 8px;
  margin-left: 4px;
  text-transform: uppercase;
}

/* Question cards */
.question-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.question-number {
  background: #3182CE;
  color: white;
  font-weight: bold;
  font-size: 0.8rem;
  padding: 2px 8px;
  border-radius: 4px;
  flex-shrink: 0;
}

.question-title-group { flex: 1; }
.question-title-group h4 { color: #2D3748; margin-bottom: 2px; }
.question-subtext { font-size: 0.85rem; color: #718096; }

.type-badge {
  font-size: 0.75rem;
  background: #EDF2F7;
  color: #4A5568;
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
}

/* Bars */
.bar-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.bar-row {
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-areas:
    "label value"
    "track track";
  gap: 4px 12px;
}

.bar-label {
  grid-area: label;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #2D3748;
}

.bar-value {
  grid-area: value;
  font-size: 0.85rem;
  color: #4A5568;
  font-variant-numeric: tabular-nums;
}

.bar-track {
  grid-area: track;
  height: 10px;
  background: #EDF2F7;
  border-radius: 5px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: #90CDF4;
  border-radius: 5px;
  transition: width 0.4s ease;
}

.bar-row.top .bar-label { font-weight: 700; }
.bar-row.top .bar-fill { background: #38A169; }

.top-tag {
  font-size: 0.7rem;
  font-weight: 700;
  background: #C6F6D5;
  color: #22543D;
  padding: 1px 8px;
  border-radius: 10px;
}

/* Short answers */
.text-answers {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.text-answers li {
  padding: 10px 12px;
  background: #F7FAFC;
  border-left: 3px solid #3182CE;
  border-radius: 4px;
}

.text-body { color: #2D3748; }
.text-author { margin-left: 8px; font-size: 0.8rem; color: #718096; }

/* Respondents */
.respondent-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.respondent {
  display: flex;
  align-items: center;
  gap: 10px;
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: #EBF8FF;
  color: #3182CE;
  font-weight: 700;
  font-size: 0.8rem;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.respondent-name {
  display: block;
  font-weight: 600;
  color: #2D3748;
}

.respondent-time {
  display: block;
  font-size: 0.75rem;
  color: #A0AEC0;
}

/* State cards */
.state-card { text-align: center; color: #4A5568; }
.state-card.error h3 { color: #C53030; margin-bottom: 8px; }
.state-card h3 { margin-bottom: 6px; color: #2D3748; }

.btn-secondary {
  background: white;
  border: 1px solid #CBD5E0;
  color: #4A5568;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
}

.btn-secondary:hover { background-color: #EDF2F7; }
.btn-secondary:disabled { opacity: 0.6; cursor: not-allowed; }

@media (max-width: 600px) {
  .results-wrapper { padding: 16px; }
  .results-header { flex-direction: column; }
}
</style>