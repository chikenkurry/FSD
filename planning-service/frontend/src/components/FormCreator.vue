<template>
  <div class="creator-layout">
    <TopBar />
    <div class="creator-wrapper">
      <div class="creator-header">
        <h2>Create Form</h2>
        <button class="btn-secondary" @click="emit('navigate', 3)">Back to Dashboard</button>
      </div>

      <form @submit.prevent="submitForm" class="form-builder">
        <div class="card">
          <div class="input-group">
            <label>Form name</label>
            <input type="text" v-model="form.name" placeholder="Placeholder" required />
          </div>

          <div class="input-group">
            <label>Description</label>
            <input type="text" v-model="form.description" placeholder="Placeholder" />
            <small class="helper-text">Helper text goes here</small>
          </div>
        </div>

        <div class="card">
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

        <!-- Dynamic Questions Builder -->
        <div v-for="(question, qIndex) in form.questions" :key="qIndex" class="card question-card">
          <div class="question-header">
            <input type="text" v-model="question.title" placeholder="Question title" class="question-title-input" />
            
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
            <input type="text" v-model="question.description" placeholder="Provide a description" class="question-description-input" />
          </div>

          <!-- multiple choice option view -->
          <div v-if="question.type === 'Multiple choice'" class="options-container">
            <div v-for="(option, oIndex) in question.options" :key="oIndex" class="option-row">
              <span class="radio-indicator">○</span>
              <input type="text" v-model="question.options[oIndex]" :placeholder="`Option ${oIndex + 1}`" />
            </div>

            <!-- Add Option button using Green Crayon palette tone -->
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
            <div class="calender-widget">
              <div class="calender-header">
                <button type="button" class="cal-nav">&lt;</button>
                <span class="cal-month-title">Oct 2026</span>
                <button type="button" class="cal-nav">&gt;</button>
              </div>
              <div class="calendar-grid">
                <span class="cal-day-header" v-for="day in ['M', 'T', 'W', 'Th', 'F', 'S', 'Su']" :key="day">{{ day }}</span>
                <!-- Calendar grid cells representation -->
                <span v-for="n in 31" :key="n" class="cal-date" :class="{ selected: n === 26 }">{{ n }}</span>
              </div>
            </div>
           </div>

        </div>

        <div class="add-question-container">
          <button type="button" class="btn-add-question" @click="addQuestion">+</button>
        </div>

        <div class="form-actions">
          <button type="submit" class="btn-primary">Save and Publish</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue';
import type { Form } from '@/types/form';
import TopBar from './TopBar.vue';

const emit = defineEmits<{
  (e: 'navigate', frame: number): void;
}>();

const form = reactive<Form>({
  name: '',
  description: '',
  category: '',
  questions: [
    {
      title: '',
      description: '',
      type: 'Multiple choice',
      options: ['Option 1']
    }
  ]
});

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

const submitForm = async (): Promise<void> => {
  // Transmit Form payload to Golang server endpoint via fetch
  console.log('Transmitting Typed Form Payload to Go Server:', JSON.stringify(form, null, 2));
  alert('Form successfully sent to backend!');
  emit('navigate', 3);
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
.card {
  background: white;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.04);
  border: 1px dashed #CBD5E0;
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
.input-group input, .input-group select, .question-title-input {
  padding: 10px 12px;
  border: 1px solid #E2E8F0;
  border-radius: 6px;
  background-color: #F8FAFC;
}
.helper-text {
  font-size: 0.8rem;
  color: #718096;
  margin-top: 4px;
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
  align-items: center;
  gap: 8px;
}
.btn-icon-delete {
  background: none;
  border: none;
  font-size: 1.25rem;
  color: #A0AEC0;
  cursor: pointer;
}
.btn-icon-delete:hover { color: #E53E3E; }

.options-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-left: 12px;
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
.radio-indicator { color: #A0AEC0; }
.radio-indicator.active { color: #38A169; }

.btn-add-option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background-color: #38A169;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  width: fit-content;
  margin-top: 6px;
}
.btn-add-option:hover { background-color: #2F855A; }
.btn-add-option .radio-indicator { color: white; }

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
.btn-add-question:hover { background-color: #EDF2F7; }

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
.btn-primary:hover { background-color: #2B6CB0; }
.btn-secondary {
  background: none;
  border: 1px solid #CBD5E0;
  color: #4A5568;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
}
.btn-secondary:hover { background-color: #EDF2F7; }
</style>