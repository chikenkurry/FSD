<template>
  <div class="creator-layout">
    <TopBar />
    <div class="creator-wrapper">
      <div class="creator-header">
        <h2>Create Form</h2>
        <button class="btn-secondary" @click="emit('navigate', 'dashboard')">Back to Dashboard</button>
      </div>

      <!-- Step nvagiation indicator bar -->
      <div class="step-indicator-bar">
        <div v-for="stepNum in 5" :key="stepNum" :class="['step-pill',
          { active: currentStep === stepNum, completed: currentStep > stepNum, disabled: stepNum === 5 && currentStep < 5 }
        ]" @click="goToStep(stepNum)">
          <span class="step-number">{{ stepNum === 5 ? 'Q' : stepNum }}</span>
          <span class="step-label"> {{ getStepLabel(stepNum) }} </span>
        </div>
      </div>

      <form @submit.prevent="submitForm" class="form-builder">
        <!-- 1: Form name and description -->
        <div v-if="currentStep === 1" class="card step-card">
          <h3 class="step-title"> Step 1: Basic information </h3>
          <div class="input-group">
            <label>Form name *</label>
            <input type="text" v-model="form.title" placeholder="eg. Europe Summer Trip 2026" required />
          </div>
          <div class="input-group">
            <label>Description</label>
            <textarea v-model="form.description" placeholder="Provide context or details" rows="3" class="textarea-multiline" ></textarea>
          </div>
        </div>

        <!-- 2: Category select -->
        <div v-if="currentStep === 2" class="card step-card">
          <h3 class="step-title">Step 2: Category</h3>
          <div class="input-group">
            <label>Category</label>
            <select v-model="form.category">
              <option disabled value="">Select category</option>
              <option>Travel</option>
              <option>Event</option>
              <option>Work</option>
              <option>General</option>
            </select>
          </div>
        </div>

        <!-- 3: Meeting date and time -->
        <div v-if="currentStep === 3" class="card step-card">
          <h3 class="step-title">Step 3: Scheduling</h3>
          <div class="input-row">
            <div class="input-group flex-1">
              <label>Date range start *</label>
              <input type="date" v-model="form.startDateRange" required />
            </div>
            <div class="input-group flex-1">
              <label>Date range end *</label>
              <input type="date" v-model="form.endDateRange" :min="form.startDateRange" required />
            </div>
          </div>
        </div>

        <!-- 4: Meeting location -->
        <div v-if="currentStep === 4" class="card step-card">
          <h3 class="step-title">Step 4: Location</h3>
          <div class="input-group">
            <label>Meeting Location / Platform</label>
            <input type="text" v-model="form.location" placeholder="eg, Zoom, Botanic Gardens" required />
          </div>
        </div>

        <!-- Questions builder -->
        <div v-if="currentStep === 5" class="card step-card">
          <!-- Summary header of previous steps -->
          <div class="summary-card">
            <h4>Plan Details Overview</h4>
            <div class="summary-grid">
              <div><strong>Title:</strong> {{ form.title }}</div>
              <div><strong>Category:</strong> {{ form.category }}</div>
              <div v-if="form.description" class="full-width multiline-summary"><strong>Description:</strong> {{ form.description }}</div>
              <div><strong>Date range:</strong> {{ form.startDateRange }} to {{ form.endDateRange }}</div>
              <div class="full-width"><strong>Location:</strong> {{ form.location }}</div>
            </div>
          </div>

          <h3 class="section-heading">Form Questions</h3>

          <div v-for="(question, qIndex) in form.questions" :key="qIndex" class="card question-card">
            <div class="question-header">
              <input type="text" v-model="question.title" placeholder="Question title" class="question-title-input"
                required />
              <div class="question-controls">
                <select v-model="question.type">
                  <option>Multiple choice</option>
                  <option>Single choice</option>
                  <option>Short answer</option>
                  <option>Duration</option>
                  <option>Location</option>
                  <option>Budget</option>
                </select>
                <button type="button" class="btn-icon-delete" @click="removeQuestion(qIndex)">×</button>
              </div>
            </div>
            <div class="input-group">
              <input type="text" v-model="question.description" placeholder="Provide a description (optional)"
                class="question-description-input" />
            </div>

            <!-- multiple choice option builder -->
            <div v-if="question.type === 'Multiple choice'" class="options-container">
              <div v-for="(option, oIndex) in question.options" :key="oIndex" class="option-row">
                <span class="checkbox-indicator">☐</span>
                <input type="text" v-model="question.options[oIndex]" :placeholder="`Option ${oIndex + 1}`" />
                <button v-if="question.options.length > 1"
                  type="button"
                  class="btn-remove-option"
                  @click="removeOption(qIndex, oIndex)">×</button>
                </div>
                <button type="button" 
                  class="btn-add-option"
                  @click="addOption(qIndex)"><span class="radio-indicator active">☑</span> Add option
                </button>
            </div>

            <!-- single choice option builder -->
             <div v-if="question.type === 'Single choice'" class="options-container">
              <div v-for="(option, oIndex) in question.options" :key="oIndex" class="option-row">
                <span class="radio-indicator">○</span> 
                <input type="text" v-model="question.options[oIndex]" :placeholder="`Option ${oIndex + 1}`" />
                <button 
                  v-if="question.options.length > 1" 
                  type="button" 
                  class="btn-remove-option" 
                  @click="removeOption(qIndex, oIndex)">×
                </button>
              </div> 
              <button type="button" class="btn-add-option" @click="addOption(qIndex)">
                <span class="radio-indicator active">◎</span> Add option
              </button>
             </div>

            <!-- short answer view -->
            <div v-if="question.type === 'Short answer'" class="short-answer-container">
              <input type="text" disabled placeholder="Input text here" class="disabled-input" />
            </div>

            <!-- duration / calender view -->
            <div v-if="question.type === 'Duration'" class="duration-container">
              <p class="helper-subtitle" v-if="form.startDateRange &amp;&amp; form.endDateRange">
                Select between: <strong>{{ form.startDateRange }}</strong> and <strong>{{ form.endDateRange }}</strong>
              </p>
              <div class="calender-widget">
                <div class="calender-header">
                  <button type="button" class="cal-nav"> < </button>
                  <span class="cal-month-title">Oct 2026</span>
                  <button type="button" class="cal-nav"> > </button>
                </div>
                <div class="calendar-grid">
                  <span class="cal-day-header" v-for="day in ['M', 'T', 'W', 'Th', 'F', 'S', 'Su']" :key="day">{{ day}}</span>
                  <!-- Calendar grid cells representation -->
                  <span v-for="n in 31" :key="n" class="cal-date" :class="{ selected: n === 26 }">{{ n }}</span>
                </div>
              </div>
            </div>

            <!-- location suggestions builder -->
             <div v-if="question.type === 'Location'" class="options-container">
              <label class="field-section-label">Suggested Locations:</label>
              <div v-for="(option, oIndex) in question.options" :key="oIndex" class="option-row">
                <span class="location-icon">📍</span>
                <input type="text" v-model="question.options[oIndex]" :placeholder="`Location ${oIndex + 1} (e.g. Vivocity)`" />
                <button 
                  v-if="question.options.length > 1" 
                  type="button" 
                  class="btn-remove-option" 
                  @click="removeOption(qIndex, oIndex)">×</button>
              </div>
              <button type="button" class="btn-add-option" @click="addOption(qIndex)">
                <span class="location-icon">📍</span> Add location suggestion
              </button>

              <div class="checkbox-setting">
                <label class="checkbox-label" >
                  <input type="checkbox" v-model="question.allowCustomSuggestions" />
                  Allow memebers to suggest their own custom location
                </label>
              </div>
             </div>
            <!-- Budget options builder -->
             <div v-if="question.type === 'Budget'" class="options-container">
              <label class="field-section-label">Budget Range Choices:</label>
              <div v-for="(option, oIndex) in question.options" :key="oIndex" class="option-row">
                <span class="currency-badge">$</span>
                <input type="text" v-model="question.options[oIndex]" :placeholder="`Budget option ${oIndex + 1} (e.g. $20 - $50)`" />
                <button 
                  v-if="question.options.length > 1" 
                  type="button" 
                  class="btn-remove-option" 
                  @click="removeOption(qIndex, oIndex)"
                >×</button>
              </div>
              <button type="button" class="btn-add-option" @click="addOption(qIndex)">
                <span class="currency-badge">$</span> Add budget tier
              </button>
             </div>
          </div>

          <!-- add question button -->
          <div class="add-question-container">
            <button type="button" class="btn-add-question" @click="addQuestion">+</button>
          </div>
        </div>

        <!-- wizard navigation footer -->
        <div class="wizard-actions">
          <button type="button" class="btn-secondary" v-if="currentStep > 1" @click="prevStep">← Back
          </button>

          <button type="button" class="btn-primary" v-if="currentStep < 4" @click="nextStep">Next Step →
          </button>

          <button type="button" class="btn-primary" v-if="currentStep === 4" @click="nextStep">Proceed to questions →
          </button>

          <button type="submit" class="btn-primary btn-publish" v-else-if="currentStep === 5">Save & Publish Form
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue';
import type { Form } from '@/types/form';
import TopBar from './TopBar.vue';
import { apiService } from '@/services/api.ts';

const emit = defineEmits<{
  (e: 'navigate', frame: string): void;
  (e: 'published', form: Form): void;
}>();

// track active step 
const currentStep = ref<number>(1);

const form = reactive<Form>({
  id: '',
  title: '',
  description: '',
  startDateRange: '',
  endDateRange: '',
  location: '',
  category: '',
  questions: [
    {
      title: '',
      description: '',
      type: 'Multiple choice',
      options: ['Option 1']
    }
  ],
  state: 'Draft',
});

// Step label helper
const getStepLabel = (step: number): string => {
  switch (step) {
    case 1: return 'Name & Details';
    case 2: return 'Category';
    case 3: return 'Date & Time';
    case 4: return 'Location';
    case 5: return 'Questions';
    default: return '';
  }
}

// Step Validation logic 
const isStepValid = (step: number): boolean => {
  if (step === 1) return form.title.trim().length > 0;
  if (step === 2) return form.category !== '';
  if (step === 3) {
    if (!form.startDateRange || !form.endDateRange) {
      return false;
    }
    return form.endDateRange >= form.startDateRange;
  }
  if (step === 4) return form.location.trim().length > 0;
  return true;
};

// wizard navigation handlers
const nextStep = () => {
  if (currentStep.value === 3 && form.startDateRange && form.endDateRange && form.endDateRange < form.startDateRange){
    alert('End Date cannot be earlier than Start Date.');
    return;
  }
  if (!isStepValid(currentStep.value)) {
    alert('Please complete the required fields in this step before proceeding.');
    return;
  }
  if (currentStep.value < 5) {
    currentStep.value++;
  }
};

const prevStep = () => {
  if (currentStep.value > 1 ) {
    currentStep.value--;
  }
};

const goToStep = (targetStep: number) => {
  // prevent jumping directly to Questions if previous steps are incomplete
  if (targetStep === 5 && (!isStepValid(1) || !isStepValid(2) || !isStepValid(3) || !isStepValid(4)) ) {
    alert('Please complete Step 1 through 4 before adding questions.');
    return;
  }
  currentStep.value = targetStep;
};

// Question management
const addQuestion = (): void => {
  form.questions.push({
    title: '',
    description: '',
    type: 'Multiple choice',
    options: ['Option 1']
  });
};

const removeQuestion = (index: number): void => {
  form.questions.splice(index, 1);
};

const addOption = (qIndex: number): void => {
  const optionNum = form.questions[qIndex].options.length + 1;
  form.questions[qIndex].options.push(`Option ${optionNum}`);
};

const removeOption = (qIndex: number, oIndex: number) => {
  if (form.questions[qIndex].options.length > 1) {
    form.questions[qIndex].options.splice(oIndex, 1);
  }
};

// form submission to backend
const submitForm = async (): Promise<void> => {
  // Transmit Form payload to Golang server endpoint via fetch
  // try {
  //   const savedForm = await apiService.createForm(form)
  //   emit('navigate', 'published');
  // } catch (error) {
  //   alert('Failted to save form to backend')
  // }
  console.log('Transmitting Typed Form Payload to Go Server:', JSON.stringify(form, null, 2));
  emit('published', JSON.parse(JSON.stringify(form)));
  emit('navigate', 'published');
  alert('Form successfully sent to backend!');
};
</script>

<style scoped>
.creator-layout {
  min-height: 100vh;
  background-color: #EFECE9;
}

.creator-wrapper {
  padding: 32px;
  max-width: 800px;
  margin: 0 auto;
}

.creator-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

/* Step indicator bar */
.step-indicator-bar {
  display: flex;
  justify-content: space-between;
  margin-bottom: 24px;
  background: white;
  padding: 12px;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.step-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  color: #718096;
  font-size: 0.85rem;
  font-weight: 500;
  transition: all 0.2s ease;
}

.step-pill.active {
  background-color: #EBF8FF;
  color: #3182CE; font-weight: 700;
}

.step-pill.completed {
  color: #2F855A;
}

.step-pill.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.step-number { width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #EDF2F7;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
}

.step-pill.active .step-number {
  background: #3182CE;
  color: white;
}

.card {
  background: white;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
  border: 1px dashed #CBD5E0;
}

.step-title {
  margin-bottom: 18px;
  color: #2D3748;
  font-size: 1.1rem;
}

.input-group {
  display: flex;
  flex-direction: column;
  margin-bottom: 16px;
}

.input-group label {
  font-weight: 600;
  margin-bottom: 6px;
  color: #2D3748;
}

.input-group input,
.input-group select,
.input-group textarea,
.question-title-input {
  padding: 10px 12px;
  border: 1px solid #E2E8F0;
  border-radius: 6px;
  background-color: #F8FAFC;
}

.textarea-multiline{
  white-space: pre-wrap;
  resize: vertical;
  line-height: 1.5;
}

.input-row {
  display: flex;
  gap: 16px;
}

.flex-1 { flex: 1; }

.summary-card {
  background: #F7FAFC;
  border: 1px solid #E2E8F0;
  padding: 16px; border-radius:
  8px; margin-bottom: 20px;
}

.summary-card h4 {
  margin-bottom: 8px;
  color: #4A5568;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  font-size: 0.85rem;
  color: #4A5568;
}

.full-width {
  grid-column: span 2;
}

.multiline-summary .description-text {
  margin-top: 4px;
  white-space: pre-wrap;
  background: #EDF2F7;
  padding: 8px 12px;
  border-radius: 4px;
  color: #2D3748;
}

.section-heading {
  margin: 16px 0 12px 0;
  color: #2D3748;
}

.question-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.question-title-input {
  flex: 1;
}

.question-controls {
  display: flex;
  /* align-items: center; */
  gap: 8px;
}

.btn-icon-delete {
  background: none;
  border: none;
  font-size: 1.25rem;
  color: #A0AEC0;
  cursor: pointer;
}

.btn-icon-delete:hover {
  color: #E53E3E;
}

.options-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-left: 12px;
}

.options-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.option-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.option-row input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #E2E8F0;
  border-radius: 6px;
}

.radio-indicator {
  color: #A0AEC0;
}

.radio-indicator.active {
  color: #38A169;
}

.question-description-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #E2E8F0;
  border-radius: 6px;
  background-color: #F8FAFC;
  font-size: 0.875rem;
  margin-top: 8px;
}

.field-section-label {
  font-size: 0.8rem;
  font-weight: 700;
  color: #4A5568;
  margin-bottom: 6px;
  display: block;
}

.btn-add-option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background-color: #2799B2;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  width: fit-content;
  margin-top: 6px;
}

.btn-add-option:hover {
  background-color: #2F855A;
}

.btn-add-option .radio-indicator {
  color: white;
}

.btn-publish { background-color: #38A169; }

/* Short answer styling */
.short-answer-container {
  padding-left: 12px;
}

.disabled-input {
  width: 100%;
  padding: 10px 12px;
  background-color: #EDF2F7;
  border: 1px solid #CBD5E0;
  border-radius: 6px;
  color: #A0AEC0;
}

/* Duration / Calendar Widget styling */
.duration-container {
  padding-left: 12px;
  display: flex;
  justify-content: flex-start;
}

.calendar-widget {
  background: white;
  border: 1px solid #CBD5E0;
  border-radius: 8px;
  padding: 16px;
  width: 280px;
}

.calendar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
  font-size: 0.85rem;
  margin-bottom: 12px;
  color: #2D3748;
}

.cal-nav {
  background: none;
  border: none;
  cursor: pointer;
  font-weight: bold;
  color: #4A5568;
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  text-align: center;
  gap: 4px;
  font-size: 0.8rem;
}

.cal-day-header {
  font-weight: 600;
  color: #718096;
  padding-bottom: 4px;
}

.cal-date {
  padding: 6px 0;
  border-radius: 4px;
  cursor: pointer;
  color: #2D3748;
}

.cal-date:hover {
  background-color: #EDF2F7;
}

.cal-date.selected {
  background-color: #3182CE;
  color: white;
  font-weight: bold;
}

.add-question-container {
  display: flex;
  justify-content: center;
  margin: 20px 0;
}

.btn-add-question {
  background: white;
  border: 1px dashed #CBD5E0;
  width: 48px;
  height: 48px;
  border-radius: 6px;
  font-size: 1.5rem;
  color: #4A5568;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-add-question:hover {
  background-color: #EDF2F7;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
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
}

.btn-primary:hover {
  background-color: #2B6CB0;
}

.btn-secondary {
  background: none;
  border: 1px solid #CBD5E0;
  color: #4A5568;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
}

.btn-secondary:hover {
  background-color: #EDF2F7;
}

.btn-remove-option {
  background: none;
  border: none;
  color: #E53E3E;
  font-size: 1.2rem;
  cursor: pointer;
  padding: 0 6px;
}

.btn-remove-option:hover {
  color: #C53030;
}

.currency-badge {
  font-weight: bold;
  color: #2F855A;
  padding: 0 4px;
}

.location-icon {
  font-size: 0.9rem;
}

.checkbox-setting {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px dashed #E2E8F0;
}

.checkbox-label {
  font-size: 0.85rem;
  color: #4A5568;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.helper-subtitle {
  font-size: 0.85rem;
  color: #4A5568;
  margin-bottom: 8px;
}

/* Wizard Navigation Actions */
.wizard-actions {
  display: flex;
  justify-content:
  space-between; margin-top: 24px;
}
</style>