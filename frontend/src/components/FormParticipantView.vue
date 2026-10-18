<template>
  <div class="participant-layout">
    <TopBar />

    <div class="participant-wrapper">
      <!-- Loading state -->
      <div v-if="isLoading" class="card state-card">Loading form…</div>

      <!-- Error state -->
      <div v-else-if="loadError || !activeForm" class="card state-card error">
        <h3>We couldn't load this form</h3>
        <p>{{ loadError || 'The form may have been removed or the link is incorrect.' }}</p>
        <button type="button" class="btn-secondary" @click="loadForm">Try again</button>
      </div>

      <!-- Thank you state -->
      <div v-else-if="isSubmitted" class="card state-card success">
        <span class="success-badge">✓ Response submitted</span>
        <h2>Thanks, {{ participantName }}!</h2>
        <p>Your answers for <strong>{{ activeForm.title }}</strong> have been recorded.</p>
        <div class="state-actions">
          <button type="button" class="btn-secondary" @click="resetResponse">Submit another response</button>
          <button v-if="showNavigation" type="button" class="btn-secondary" @click="emit('navigate', 'dashboard')">
            Back to Dashboard
          </button>
        </div>
      </div>

      <!-- Participant form -->
      <form v-else @submit.prevent="submitResponse" novalidate>
        <!-- Form header -->
        <div class="card header-card">
          <span v-if="activeForm.category" class="category-tag">{{ activeForm.category }}</span>
          <h2 class="form-title">{{ activeForm.title }}</h2>
          <p v-if="activeForm.description" class="description-text">{{ activeForm.description }}</p>

          <div class="details-grid">
            <div class="detail-item">
              <span class="detail-icon">📅</span>
              <div>
                <label>Date range</label>
                <p v-if="activeForm.startDateRange && activeForm.endDateRange">
                  {{ activeForm.startDateRange }} to {{ activeForm.endDateRange }}
                </p>
                <p v-else>Flexible / Not specified</p>
              </div>
            </div>
            <div class="detail-item">
              <span class="detail-icon">📍</span>
              <div>
                <label>Location / Platform</label>
                <p>{{ activeForm.location || 'To be decided' }}</p>
              </div>
            </div>
          </div>
        </div>

        <!-- Participant identity -->
        <div class="card">
          <div class="input-group">
            <label for="participant-name">Your name <span class="required">*</span></label>
            <input
              id="participant-name"
              type="text"
              v-model="participantName"
              placeholder="Enter your name"
              :class="{ invalid: showErrors && !participantName.trim() }"
            />
            <span v-if="showErrors && !participantName.trim()" class="error-text">Please enter your name.</span>
          </div>
        </div>

        <!-- Questions -->
        <div
          v-for="(question, qIndex) in activeForm.questions"
          :key="qIndex"
          class="card question-card"
          :class="{ 'has-error': showErrors && !isAnswered(qIndex) }"
        >
          <div class="question-header">
            <span class="question-number">Q{{ qIndex + 1 }}</span>
            <div class="question-title-group">
              <h4>{{ question.title }}</h4>
              <p v-if="question.description" class="question-subtext">{{ question.description }}</p>
            </div>
            <span class="type-badge">{{ question.type }}</span>
          </div>

          <!-- Multiple choice (checkboxes) -->
          <div v-if="question.type === 'Multiple choice'" class="options-list">
            <label v-for="(opt, oIdx) in question.options" :key="oIdx" class="option-label">
              <input type="checkbox" :value="opt" v-model="(answers[qIndex] as string[])" />
              <span>{{ opt }}</span>
            </label>
            <p class="hint">Select all that apply.</p>
          </div>

          <!-- Single choice (radio) -->
          <div v-else-if="question.type === 'Single choice'" class="options-list">
            <label v-for="(opt, oIdx) in question.options" :key="oIdx" class="option-label">
              <input type="radio" :name="`q-${qIndex}`" :value="opt" v-model="answers[qIndex]" />
              <span>{{ opt }}</span>
            </label>
          </div>

          <!-- Short answer -->
          <div v-else-if="question.type === 'Short answer'">
            <input
              type="text"
              v-model="(answers[qIndex] as string)"
              placeholder="Type your answer"
              class="text-input"
            />
          </div>

          <!-- Duration: pick available dates within the form's date range -->
          <div v-else-if="question.type === 'Duration'">
            <p v-if="availableDates.length" class="hint">
              Tap every date you're available between
              <strong>{{ activeForm.startDateRange }}</strong> and <strong>{{ activeForm.endDateRange }}</strong>.
            </p>
            <p v-else class="hint">The organiser hasn't set a date range for this form.</p>

            <div class="date-grid">
              <button
                v-for="d in availableDates"
                :key="d.value"
                type="button"
                class="date-chip"
                :class="{ selected: (answers[qIndex] as string[]).includes(d.value) }"
                @click="toggleDate(qIndex, d.value)"
              >
                <span class="date-weekday">{{ d.weekday }}</span>
                <span class="date-day">{{ d.label }}</span>
              </button>
            </div>
            <p v-if="availableDatesTruncated" class="hint">Showing the first {{ MAX_DATE_CHIPS }} days of the range.</p>
          </div>

          <!-- Location: pick from suggestions, optionally add a custom one -->
          <div v-else-if="question.type === 'Location'" class="options-list">
            <label v-for="(opt, oIdx) in question.options" :key="oIdx" class="option-label">
              <input type="radio" :name="`q-${qIndex}`" :value="opt" v-model="answers[qIndex]" />
              <span>📍 {{ opt }}</span>
            </label>

            <template v-if="question.allowCustomSuggestions">
              <label class="option-label">
                <input type="radio" :name="`q-${qIndex}`" :value="CUSTOM_VALUE" v-model="answers[qIndex]" />
                <span>💡 Suggest my own</span>
              </label>
              <input
                v-if="answers[qIndex] === CUSTOM_VALUE"
                type="text"
                v-model="customLocations[qIndex]"
                placeholder="Enter your suggested location"
                class="text-input custom-input"
              />
            </template>
          </div>

          <!-- Budget -->
          <div v-else-if="question.type === 'Budget'" class="options-list">
            <label v-for="(opt, oIdx) in question.options" :key="oIdx" class="option-label">
              <input type="radio" :name="`q-${qIndex}`" :value="opt" v-model="answers[qIndex]" />
              <span>💲 {{ opt }}</span>
            </label>
          </div>

          <span v-if="showErrors && !isAnswered(qIndex)" class="error-text">Please answer this question.</span>
        </div>

        <!-- Submit -->
        <div v-if="submitError" class="banner-error">{{ submitError }}</div>

        <div class="wizard-actions">
          <button v-if="showNavigation" type="button" class="btn-secondary" @click="emit('navigate', 'dashboard')">
            ← Back
          </button>
          <button type="submit" class="btn-primary btn-publish" :disabled="isSubmitting">
            {{ isSubmitting ? 'Submitting…' : 'Submit Response' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted, watch } from 'vue';
import TopBar from './TopBar.vue';
import type { Form } from '@/types/form';
// import { apiService } from '@/services/api.ts';   // TODO: uncomment when backend is connected

/* ----------------------------- props / emits ----------------------------- */

const props = withDefaults(
  defineProps<{
    /** Pass a form directly (e.g. preview from the creator), or leave empty to fetch by formId. */
    form?: Form | null;
    /** ID taken from the share URL: /forms/view/:formId */
    formId?: string;
    /** Hide navigation buttons when this is shown on a public share link. */
    showNavigation?: boolean;
  }>(),
  { form: null, formId: '', showNavigation: true }
);

const emit = defineEmits<{
  (e: 'navigate', view: string): void;
  (e: 'submitted', payload: ResponsePayload): void;
}>();

/* --------------------------------- types --------------------------------- */

// TODO: move to '@/types/form' once the backend contract is fixed.
type AnswerValue = string | string[];

interface ResponsePayload {
  formId: string;
  participantName: string;
  submittedAt: string;
  answers: {
    questionIndex: number;
    questionTitle: string;
    type: string;
    value: AnswerValue;
  }[];
}

/* --------------------------------- state --------------------------------- */

const CUSTOM_VALUE = '__custom__';
const MAX_DATE_CHIPS = 62;

const activeForm = ref<Form | null>(props.form ?? null);
const isLoading = ref(false);
const loadError = ref('');

const participantName = ref('');
const answers = reactive<Record<number, AnswerValue>>({});
const customLocations = reactive<Record<number, string>>({});

const showErrors = ref(false);
const isSubmitting = ref(false);
const isSubmitted = ref(false);
const submitError = ref('');

/* ------------------------------ load the form ----------------------------- */

// Placeholder data so the page works before the backend exists.
const mockForm: Form = {
  id: 'mock-form-id',
  title: 'Europe Summer Trip 2026',
  description: 'Help us pick the dates, places and budget for the trip!',
  startDateRange: '2026-07-01',
  endDateRange: '2026-07-14',
  location: 'Zoom',
  category: 'Travel',
  state: 'Collecting',
  questions: [
    { title: 'Which activities interest you?', description: '', type: 'Multiple choice', options: ['Museums', 'Hiking', 'Food tours'] },
    { title: 'Preferred travel style?', description: '', type: 'Single choice', options: ['Relaxed', 'Packed itinerary'] },
    { title: 'When are you available?', description: 'Pick all dates that work', type: 'Duration', options: [] },
    { title: 'Where should we meet?', description: '', type: 'Location', options: ['Vivocity', 'Botanic Gardens'], allowCustomSuggestions: true },
    { title: 'Budget per person', description: '', type: 'Budget', options: ['$1000 - $2000', '$2000 - $3500'] },
    { title: 'Anything else?', description: '', type: 'Short answer', options: [] },
  ],
} as Form;

const loadForm = async (): Promise<void> => {
  // If a form was passed in directly, no fetch is needed.
  if (props.form) {
    activeForm.value = props.form;
    return;
  }

  isLoading.value = true;
  loadError.value = '';
  try {
    // TODO: replace with real backend call once available.
    // activeForm.value = await apiService.getFormById(props.formId);

    await new Promise((resolve) => setTimeout(resolve, 300)); // simulate latency
    activeForm.value = { ...mockForm, id: props.formId || mockForm.id };
  } catch (err) {
    console.error('Failed to load form:', err);
    loadError.value = 'Something went wrong while loading the form.';
    activeForm.value = null;
  } finally {
    isLoading.value = false;
  }
};

/** Give every question an empty answer of the right shape. */
const initAnswers = (): void => {
  Object.keys(answers).forEach((k) => delete answers[Number(k)]);
  Object.keys(customLocations).forEach((k) => delete customLocations[Number(k)]);
  activeForm.value?.questions.forEach((q, i) => {
    answers[i] = q.type === 'Multiple choice' || q.type === 'Duration' ? [] : '';
  });
};

watch(activeForm, initAnswers, { immediate: true });
watch(() => props.form, (f) => { if (f) activeForm.value = f; });
onMounted(loadForm);

/* ---------------------------- date range helpers --------------------------- */

interface DateOption { value: string; label: string; weekday: string }

// Parse "YYYY-MM-DD" as a local date to avoid timezone off-by-one errors.
const parseLocalDate = (s: string): Date => {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
};

const toISODate = (d: Date): string =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

const allDates = computed<DateOption[]>(() => {
  const f = activeForm.value;
  if (!f?.startDateRange || !f?.endDateRange) return [];
  const start = parseLocalDate(f.startDateRange);
  const end = parseLocalDate(f.endDateRange);
  const out: DateOption[] = [];
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    out.push({
      value: toISODate(d),
      label: d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }),
      weekday: d.toLocaleDateString(undefined, { weekday: 'short' }),
    });
  }
  return out;
});

const availableDates = computed(() => allDates.value.slice(0, MAX_DATE_CHIPS));
const availableDatesTruncated = computed(() => allDates.value.length > MAX_DATE_CHIPS);

const toggleDate = (qIndex: number, value: string): void => {
  const selected = answers[qIndex] as string[];
  const idx = selected.indexOf(value);
  if (idx === -1) selected.push(value);
  else selected.splice(idx, 1);
  selected.sort();
};

/* ------------------------------- validation ------------------------------- */

const isAnswered = (qIndex: number): boolean => {
  const q = activeForm.value?.questions[qIndex];
  const a = answers[qIndex];
  if (!q) return true;
  if (Array.isArray(a)) return a.length > 0;
  if (a === CUSTOM_VALUE) return (customLocations[qIndex] ?? '').trim().length > 0;
  return typeof a === 'string' && a.trim().length > 0;
};

const isFormValid = computed(() => {
  if (!participantName.value.trim()) return false;
  return (activeForm.value?.questions ?? []).every((_, i) => isAnswered(i));
});

/* -------------------------------- submission ------------------------------- */

const buildPayload = (): ResponsePayload => ({
  formId: activeForm.value?.id || props.formId,
  participantName: participantName.value.trim(),
  submittedAt: new Date().toISOString(),
  answers: (activeForm.value?.questions ?? []).map((q, i) => {
    let value: AnswerValue = Array.isArray(answers[i]) ? [...(answers[i] as string[])] : (answers[i] as string);
    // Replace the custom-location sentinel with what the participant typed.
    if (value === CUSTOM_VALUE) value = (customLocations[i] ?? '').trim();
    return { questionIndex: i, questionTitle: q.title, type: q.type, value };
  }),
});

const submitResponse = async (): Promise<void> => {
  submitError.value = '';
  showErrors.value = true;
  if (!isFormValid.value) {
    submitError.value = 'Please complete all required fields before submitting.';
    return;
  }

  isSubmitting.value = true;
  const payload = buildPayload();
  try {
    // TODO: replace with real backend call once available.
    // await apiService.submitResponse(payload.formId, payload);

    console.log('Submitting participant response to Go server:', JSON.stringify(payload, null, 2));
    await new Promise((resolve) => setTimeout(resolve, 400)); // simulate latency

    isSubmitted.value = true;
    emit('submitted', payload);
  } catch (err) {
    console.error('Failed to submit response:', err);
    submitError.value = 'We could not save your response. Please try again.';
  } finally {
    isSubmitting.value = false;
  }
};

const resetResponse = (): void => {
  participantName.value = '';
  showErrors.value = false;
  submitError.value = '';
  isSubmitted.value = false;
  initAnswers();
};
</script>

<style scoped>
.participant-layout {
  min-height: 100vh;
  background-color: #EFECE9;
}

.participant-wrapper {
  padding: 32px;
  max-width: 720px;
  margin: 0 auto;
}

.card {
  background: white;
  border-radius: 8px;
  padding: 24px;
  margin-bottom: 20px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
  border: 1px solid #E2E8F0;
}

.header-card {
  border-top: 4px solid #3182CE;
}

.category-tag {
  background: #EDF2F7;
  color: #4A5568;
  font-size: 0.8rem;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 4px;
}

.form-title {
  font-size: 1.6rem;
  color: #2D3748;
  margin: 8px 0;
}

.description-text {
  white-space: pre-wrap;
  color: #4A5568;
  line-height: 1.5;
  margin-bottom: 8px;
}

.details-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #E2E8F0;
}

.detail-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-icon { font-size: 1.4rem; }

.detail-item label {
  font-size: 0.75rem;
  text-transform: uppercase;
  color: #A0AEC0;
  font-weight: bold;
}

.detail-item p {
  color: #2D3748;
  font-weight: 600;
  margin-top: 2px;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-group label {
  font-weight: 600;
  color: #2D3748;
}

.required { color: #E53E3E; }

.input-group input,
.text-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #E2E8F0;
  border-radius: 6px;
  background-color: #F8FAFC;
  font-size: 0.95rem;
}

.input-group input:focus,
.text-input:focus {
  outline: none;
  border-color: #3182CE;
  background: white;
}

.invalid { border-color: #E53E3E !important; }

.question-card.has-error { border-color: #E53E3E; }

.question-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}

.question-number {
  background: #3182CE;
  color: white;
  font-weight: bold;
  font-size: 0.8rem;
  padding: 2px 8px;
  border-radius: 4px;
}

.question-title-group { flex: 1; }

.question-title-group h4 {
  color: #2D3748;
  margin-bottom: 2px;
}

.question-subtext {
  font-size: 0.85rem;
  color: #718096;
}

.type-badge {
  font-size: 0.75rem;
  background: #EDF2F7;
  color: #4A5568;
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
}

.options-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-left: 8px;
}

.option-label {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid #E2E8F0;
  border-radius: 6px;
  cursor: pointer;
  color: #2D3748;
}

.option-label:hover { background: #F7FAFC; }

.custom-input { margin-top: 4px; }

.hint {
  font-size: 0.8rem;
  color: #718096;
  margin: 4px 0 8px;
}

.error-text {
  display: block;
  color: #E53E3E;
  font-size: 0.8rem;
  margin-top: 8px;
}

.banner-error {
  background: #FED7D7;
  color: #742A2A;
  padding: 10px 14px;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 0.9rem;
}

/* Date chips */
.date-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(76px, 1fr));
  gap: 8px;
}

.date-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 4px;
  border: 1px solid #CBD5E0;
  border-radius: 6px;
  background: white;
  cursor: pointer;
  color: #2D3748;
}

.date-chip:hover { background: #EDF2F7; }

.date-chip.selected {
  background: #3182CE;
  border-color: #3182CE;
  color: white;
}

.date-weekday { font-size: 0.7rem; opacity: 0.8; }
.date-day { font-size: 0.85rem; font-weight: 600; }

/* State cards */
.state-card {
  text-align: center;
  color: #4A5568;
}

.state-card.error h3 { color: #C53030; margin-bottom: 8px; }
.state-card.success { border-color: #38A169; }
.state-card.success h2 { color: #2D3748; margin: 8px 0; }

.state-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 16px;
}

.success-badge {
  display: inline-block;
  background-color: #C6F6D5;
  color: #22543D;
  font-weight: 700;
  font-size: 0.8rem;
  padding: 4px 10px;
  border-radius: 12px;
}

/* Buttons */
.wizard-actions {
  display: flex;
  justify-content: space-between;
  margin-top: 24px;
}

.btn-primary {
  background-color: #3182CE;
  color: white;
  border: none;
  padding: 12px 24px;
  font-weight: bold;
  border-radius: 6px;
  cursor: pointer;
  margin-left: auto;
}

.btn-primary:hover { background-color: #2B6CB0; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-publish { background-color: #38A169; }
.btn-publish:hover { background-color: #2F855A; }

.btn-secondary {
  background: white;
  border: 1px solid #CBD5E0;
  color: #4A5568;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
}

.btn-secondary:hover { background-color: #EDF2F7; }

@media (max-width: 600px) {
  .participant-wrapper { padding: 16px; }
  .details-grid { grid-template-columns: 1fr; }
}
</style>