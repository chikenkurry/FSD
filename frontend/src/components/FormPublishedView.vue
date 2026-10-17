
<template>
    <div class="published-layout">
        <TopBar />

        <div class="published-wrapper">
            <!-- success banner and share link header -->
             <div class="card share-card">
                <div class="success-header">
                    <span class="success-badge">✓ Form Published</span>
                    <h2>Share your form with your friends to start planning!</h2>
                    <p class="subtitle">Copy the generated link below to invite participants and collect responses.</p>
                </div>

                <div class="share-input-group">
                    <input type="text"
                        :value="shareUrl"
                        readonly
                        class="share-url-input"
                        ref="shareInput" />
                    <button type="button"
                        :class="['btn-primary', { 'btn-copied': isCopied }]" @click="copyShareLink">
                    {{ isCopied ? '✓ Copied!' : 'Copy Link' }}
                    </button>
                </div>

                <div class="quick-actions">
                    <button class="btn-secondary" @click="emit('navigate', 'dashboard')">
                        ← Back to Dashboard
                    </button>
                </div>
             </div>

             <!-- complete form overview -->
             <div class="details-grid">
                <div class="detail-item">
                    <span class="detail-icon">📅</span>
                    <div>
                        <label>Date Range</label>
                        <p v-if="form.startDateRange && form.endDateRange">
                            {{ form.startDateRange }} to {{ form.endDateRange }}
                        </p>
                        <p v-else>Flexible / Not specified</p>
                    </div>
                </div>

                <div class="detail-item">
                    <span class="detail-icon">📍</span>
                    <div>
                        <label>Location / Platform</label>
                        <p>{{ form.location || 'To be decided' }}</p>
                    </div>
                </div>
             </div>
        </div>
        <!-- participant view preview -->
        <div class="questions-sections">
            <h3 class="section-title">Form Questions ({{ form.questions?.length || 0 }})</h3>

            <div v-for="(question, index) in form.questions" 
                :key="index"
                class="card question-preview-card">
                <div class="question-header">
                    <span class="question-number">Q{{ index + 1 }}</span>
                    <div class="question-title-group">
                        <h4>{{ question.title }}</h4>
                        <p v-if="question.description" class="question-subtext"> {{ question.description }}</p>
                    </div>
                    <span class="type-badge">{{ question.type }}</span>
                </div>

                <!-- multiple / single choice preview -->
                <div v-if="question.type === 'Multiple choice' || question.type === 'Single choice'" class="options-preview">
                    <div v-for="(opt, oIdx) in question.options" :key="oIdx" class="preview-option-row">
                        <span class="choice-symbol">{{ question.type === 'Single choice' ? '○' : '☐' }}</span>
                    </div>
                </div>

                <!-- short answer preview -->
                <div v-else-if="question.type === 'Short answer'" class="options-preview">
                    <input type="text" disabled placeholder="Participant text response..." class="disabled-preview-input" />
                </div>

                <!-- duration / calendar preview -->
                <div v-else-if="question.type === 'Duration'" class="options-preview">
                    <p class="duration-helper">Participants will select dates bounded between {{ form.startDateRange }} and {{ form.endDateRange }}.</p>
                </div>

                <!-- Location suggestions preview -->
                <div v-else-if="question.type === 'Location'" class="options-preview">
                    <div v-for="(opt, oIdx) in question.options" :key="oIdx" class="preview-option-row">
                        <span class="choice-symbol">📍</span>
                        <span>{{ opt }}</span>
                    </div>
                    <p v-if="question.allowCustomSuggestions" class="custom-hint">
                        💡 Custom location suggestions enabled for participants.
                    </p>
                </div>

                <!-- bugdet range preview -->
                <div v-else-if="question.type === 'Budget'" class="options-preview">
                    <div v-for="(opt, oIdx) in question.options" :key="oIdx" class="preview-option-row">
                        <span class="choice-symbol">💲</span>
                        <span>{{ opt }}</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>


<script setup lang="ts">
import TopBar from './TopBar.vue';
import { ref, computed } from 'vue';
import type { Form } from '@/types/form.ts';


const props = defineProps<{
    form: Form;
}>();

const emit = defineEmits<{
    (e: 'navigate', view: string): void;
}>();

const isCopied = ref<boolean>(false);

const shareUrl = computed<string>(() => {
  const formId = props.form.id || 'draft-preview-id';
  return `${window.location.origin}/forms/view/${formId}`;
});

// Copy URL to clipboard 
const copyShareLink = async (): Promise<void> => {
  try {
    await navigator.clipboard.writeText(shareUrl.value);
    isCopied.value = true;
    setTimeout(() => {
      isCopied.value = false;
    }, 2500);
  } catch (err) {
    console.error('Failed to copy share link:', err);
  }
};

</script>

<style scoped>
.published-layout {
  min-height: 100vh;
  background-color: #EFECE9;
}

.published-wrapper {
  padding: 32px;
  max-width: 820px;
  margin: 0 auto;
}

.card {
  background: white;
  border-radius: 8px;
  padding: 24px;
  margin-bottom: 24px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
  border: 1px dashed #CBD5E0;
}

/* Share Card */
.share-card {
  background: #F7FAFC;
  border: 1px solid #3182CE;
}

.success-badge {
  display: inline-block;
  background-color: #C6F6D5;
  color: #22543D;
  font-weight: 700;
  font-size: 0.8rem;
  padding: 4px 10px;
  border-radius: 12px;
  margin-bottom: 8px;
}

.success-header h2 {
  color: #2D3748;
  margin-bottom: 4px;
}

.subtitle {
  color: #718096;
  font-size: 0.9rem;
  margin-bottom: 16px;
}

.share-input-group {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.share-url-input {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #CBD5E0;
  border-radius: 6px;
  background-color: white;
  font-family: monospace;
  color: #2D3748;
}

.btn-primary {
  background-color: #3182CE;
  color: white;
  border: none;
  padding: 10px 20px;
  font-weight: bold;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.btn-copied {
  background-color: #38A169 !important;
}

.btn-secondary {
  background: white;
  border: 1px solid #CBD5E0;
  color: #4A5568;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
}

/* Form Overview Card */
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
  margin-top: 8px;
}

.description-section {
  margin: 16px 0;
  padding: 12px;
  background-color: #F8FAFC;
  border-left: 3px solid #3182CE;
  border-radius: 4px;
}

.description-text {
  white-space: pre-wrap;
  color: #4A5568;
  line-height: 1.5;
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

.detail-icon {
  font-size: 1.4rem;
}

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

/* Questions Preview */
.section-title {
  color: #2D3748;
  margin-bottom: 16px;
}

.question-preview-card {
  border-style: solid;
  border-color: #E2E8F0;
}

.question-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.question-number {
  background: #3182CE;
  color: white;
  font-weight: bold;
  font-size: 0.8rem;
  padding: 2px 8px;
  border-radius: 4px;
}

.question-title-group {
  flex: 1;
}

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
}

.options-preview {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-left: 32px;
}

.preview-option-row {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #4A5568;
}

.disabled-preview-input {
  width: 100%;
  padding: 8px;
  border: 1px solid #E2E8F0;
  border-radius: 4px;
  background: #F7FAFC;
}

.custom-hint {
  font-size: 0.8rem;
  color: #718096;
  margin-top: 4px;
}
</style>