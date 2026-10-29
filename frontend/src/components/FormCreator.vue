<template>
  <div class="creator-layout">
    <main class="creator-wrapper" id="main-content" tabindex="-1">
      <div class="creator-header page-heading">
        <div><h1>Create a form</h1><p>Set up a clear decision before you invite your group.</p></div>
        <button class="btn-secondary" @click="leave"><UiIcon name="back" />Back to forms</button>
      </div>

      <p v-if="draftLoadError" role="alert">{{ draftLoadError }} <button @click="loadServerDraft">Retry loading draft</button></p>
      <p v-if="serverSaveError" role="alert">{{ serverSaveError }} <button @click="saveServerDraft">Retry saving draft</button></p>
      <nav class="step-indicator-bar" aria-label="Form setup steps">
        <div class="step-list" :style="{ '--steps': steps.length }">
        <div class="step-track" aria-hidden="true"><span :style="{ '--value': (currentStep - 1) / (steps.length - 1) }"></span></div>
        <button type="button" v-for="(label, i) in steps" :key="label" :disabled="isSaving"
          :aria-current="currentStep === i + 1 ? 'step' : undefined"
          :class="['step-pill', { active: currentStep === i + 1, completed: currentStep !== i + 1 && reachable(i + 2) && visited >= i + 1, locked: !reachable(i + 1) }]"
          @click="goToStep(i + 1)">
          <span class="step-number"><Transition name="swap" mode="out-in"><UiIcon v-if="currentStep !== i + 1 && reachable(i + 2) && visited >= i + 1" name="check" /><span v-else>{{ i + 1 }}</span></Transition></span>
          <span class="step-label">{{ label }}</span>
        </button>
        </div>
      </nav>
      <div class="builder-layout">
        <form @submit.prevent="submitForm" class="form-builder" novalidate>
          <div ref="stepTop" class="step-top"></div>
          <Transition name="reveal"><p v-if="saveError" role="alert">{{ saveError }}</p></Transition>
          <fieldset :disabled="isSaving || loadingDraft || !!draftLoadError">
            <Transition :name="direction > 0 ? 'step-forward' : 'step-back'" mode="out-in">
              <!-- 1: Basics -->
              <div v-if="currentStep === 1" key="1" class="step-card">
                <h2 ref="stepHeading" tabindex="-1" class="step-title">What are you deciding?</h2>
                <label for="form-title">Plan name<span class="required-mark" aria-hidden="true">*</span></label>
                <input id="form-title" type="text" v-model="form.title" placeholder="e.g. Team offsite, Saturday dinner" maxlength="255" required :aria-invalid="flag(1, !form.title.trim())" aria-describedby="title-help" />
                <p id="title-help" :class="['helper-text', { 'field-error': flag(1, !form.title.trim()) }]">{{ flag(1, !form.title.trim()) ? 'Give the plan a name your group will recognise.' : 'Your group sees this name on the invitation.' }}</p>
                <label for="form-description">Description <span class="optional">(optional)</span></label>
                <textarea id="form-description" v-model="form.description" placeholder="Context that helps people answer, such as the occasion or constraints" rows="3"></textarea>
                <fieldset class="category-field" :aria-invalid="flag(1, !form.category)">
                  <legend>Category<span class="required-mark" aria-hidden="true">*</span></legend>
                  <div class="choice-list">
                    <label v-for="c in categories" :key="c.value" class="choice-option category-option">
                      <input type="radio" name="category" :value="c.value" v-model="form.category" />
                      <span><strong>{{ c.value }}</strong><small>{{ c.hint }}</small></span>
                    </label>
                  </div>
                  <p v-if="flag(1, !form.category)" class="helper-text field-error">Choose the category closest to this plan.</p>
                </fieldset>
                <h3 class="sub-heading">When and where</h3>
                <p class="step-lede">Context for your group. It doesn’t create time slots or limit anyone’s availability.</p>
                <div class="input-row">
                  <label>Earliest date<span class="required-mark" aria-hidden="true">*</span><input id="date-start" type="date" v-model="form.startDateRange" required :aria-invalid="flag(1, !form.startDateRange)" /></label>
                  <label>Latest date<span class="required-mark" aria-hidden="true">*</span><input id="date-end" type="date" v-model="form.endDateRange" :min="form.startDateRange" required :aria-invalid="flag(1, !form.endDateRange || datesReversed)" /></label>
                </div>
                <p v-if="datesReversed" class="helper-text field-error">The latest date must be on or after the earliest date.</p>
                <p v-else-if="dayCount" class="helper-text">{{ dayCount === 1 ? 'A single day.' : `A ${dayCount}-day window.` }}</p>
                <label>Location or platform<span class="required-mark" aria-hidden="true">*</span><input id="meeting-location" type="text" v-model="form.location" placeholder="e.g. Zoom, Botanic Gardens, the office" required :aria-invalid="flag(1, !form.location.trim())" /></label>
              </div>

              <!-- 2: Decision and options -->
              <div v-else-if="currentStep === 2" key="2" class="step-card">
                <h2 ref="stepHeading" tabindex="-1" class="step-title">What are you choosing between?</h2>
                <label for="form-question">The question your group is answering</label>
                <input id="form-question" type="text" v-model="form.decisionQuestion" :placeholder="questionPlaceholder" maxlength="300" />
                <p class="helper-text">Shown to everyone as the main question. Leave it blank to use “{{ questionPlaceholder }}”.</p>
                <fieldset class="options-field">
                  <legend>Options <span class="optional">{{ form.decisionOptions?.length }} of 8</span></legend>
                  <TransitionGroup name="list" tag="ol" class="option-inputs">
                    <li v-for="(option, index) in form.decisionOptions" :key="keyOf(option)" class="option-input">
                      <span class="option-index" aria-hidden="true">{{ index + 1 }}</span>
                      <div class="option-fields">
                        <input v-model="option.title" :aria-label="`Option ${index + 1} name`" :placeholder="index ? 'Another option' : optionPlaceholder" @keydown.enter.prevent="enterOption(index)" :aria-invalid="flag(2, !option.title.trim())" />
                        <input v-model="identity(option).source_url" type="url" inputmode="url" :aria-label="`Option ${index + 1} website (optional)`" placeholder="Website (optional, helps AI find facts)" class="link-input" />
                      </div>
                      <button v-if="(form.decisionOptions?.length || 0) > 1" type="button" class="btn-icon btn-quiet btn-danger" :aria-label="`Remove option ${index + 1}`" @click="removeDecisionOption(index)"><UiIcon name="close" /></button>
                    </li>
                  </TransitionGroup>
                  <button v-if="(form.decisionOptions?.length || 0) < 8" type="button" class="btn-add-option" @click="addDecisionOption"><UiIcon name="plus" />Add option</button>
                </fieldset>
                <label class="currency-field">Currency for costs<select v-model="form.currency"><option>SGD</option><option>USD</option><option>EUR</option><option>GBP</option></select></label>
              </div>

              <!-- 3: Overview -->
              <div v-else-if="currentStep === 3" key="3" class="step-card">
                <h2 ref="stepHeading" tabindex="-1" class="step-title">Your options at a glance</h2>
                <p class="step-lede">Review your options here once. Check their identity and overview, and correct anything inaccurate. This is what your group will see.</p>
                <details><summary>What does research do?</summary><p class="helper-text">Web research looks up option details and supporting sources{{ placesHint }}. It can help draft questions. Decision interprets members’ answers, and the algorithm calculates the ranking.</p></details>
                <Transition name="reveal"><p v-if="research.state.message" class="callout warning" role="status">{{ research.state.message }}</p></Transition>
                <div class="overview-grid">
                  <OverviewCard v-for="(option, index) in form.decisionOptions" :key="keyOf(option)" class="rise" :style="{ '--i': index }"
                    :title="option.title" :overview="option.overview" :brief="option.brief" :kind="option.identity?.kind" :round-id="form.roundId" :place-id="option.identity?.place_id"
                    :position="index + 1" :photo-key="research.revision.value" :loading="research.state.options[optionKey(option)]?.status === 'loading'">
                    <div class="card-tools">
                      <label class="kind-field">Type<select :value="option.identity?.kind || 'other'" @change="changeKind(option, ($event.target as HTMLSelectElement).value as OptionKind)">
                        <option value="place">Place</option><option value="destination">Destination</option><option value="event">Event</option><option value="activity">Activity</option><option value="other">Other</option>
                      </select></label>
                      <button type="button" class="btn-quiet btn-small" :disabled="research.state.options[optionKey(option)]?.status === 'loading'" @click="retryOverview(option)">Research again</button>
                    </div>
                    <details class="overview-correction"><summary>Correct this overview</summary><label>Option overview<textarea :value="option.summary || option.brief?.summary || ''" maxlength="4000" @input="correctOverview(option,($event.target as HTMLTextAreaElement).value)"></textarea></label></details>
                  </OverviewCard>
                </div>
                <p v-if="research.state.facts === 'loading'" class="drafting" role="status">Looking up supporting facts… You can continue while this runs.</p>
                <details v-if="reviewDefinitions.length" class="option-evidence"><summary>View or correct supporting facts</summary>
                  <FactReview :form="form" :options="form.decisionOptions || []" :definitions="reviewDefinitions" :researching="research.state.facts === 'loading'" @research="research.researchAgain" />
                </details>
                <p class="helper-text overview-note">Missing facts don’t block publishing. Decision looks for additional evidence when processing answers; unresolved evidence will be shown with the result.</p>
              </div>

              <!-- 4: Questions -->
              <div v-else-if="currentStep === 4" key="4" class="step-card">
                <h2 ref="stepHeading" tabindex="-1" class="step-title">Questions for your group</h2>
                <p class="step-lede">AI drafted these from your options. Edit, remove or add questions for your group.</p>
                <div v-if="research.state.questions === 'loading'" class="drafting" role="status"><span class="pulse" aria-hidden="true"></span>Drafting questions from your options…</div>
                <Transition name="reveal"><p v-if="research.state.message && currentStep === 4" class="callout warning" role="status">{{ research.state.message }}</p></Transition>
                <TransitionGroup name="list" tag="div" class="question-list">
                  <article v-for="(question, qIndex) in form.questions" :key="keyOf(question)" class="question-card">
                    <div class="question-top">
                      <h3>Question {{ qIndex + 1 }}</h3>
                      <button v-if="form.questions.length > 1" type="button" class="btn-quiet btn-danger btn-small" @click="removeQuestion(qIndex)"><span class="sr-only">Remove question {{ qIndex + 1 }}</span><span aria-hidden="true">Remove</span></button>
                    </div>
                    <div class="question-header">
                      <label class="question-title-field">Question<input type="text" v-model="question.title" @change="ensureCriterion(question, qIndex)" placeholder="e.g. Which cuisine do you prefer?" required :aria-invalid="flag(4, !question.title.trim())" /></label>
                      <label class="question-type-field">Answer type<select v-model="question.type" @change="typeChanged(question)">
                        <option>Single choice</option><option>Multiple choice</option><option value="Boolean">Yes or no</option><option>Number</option>
                        <option>Short answer</option><option>Duration</option>
                        <option value="Option rating" :disabled="question.type !== 'Option rating' && hasRating">Rate each option</option>
                        <option value="Date poll" :disabled="question.type !== 'Date poll' && hasDatePoll">Which dates work?</option>
                      </select></label>
                    </div>
                    <label>Help text <span class="optional">(optional)</span><input type="text" v-model="question.description" placeholder="Anything that helps people answer" /></label>

                    <div v-if="hasChoices(question)" class="choices">
                      <p class="choices-label">{{ question.type === 'Budget' ? 'Budget ranges' : question.type === 'Location' ? 'Suggested locations' : 'Choices' }}</p>
                      <TransitionGroup name="list" tag="div">
                        <div v-for="(_, oIndex) in question.options" :key="`${keyOf(question)}-${oIndex}`" class="option-row">
                          <span :class="['choice-marker', { square: question.type === 'Multiple choice' }]" aria-hidden="true"></span>
                          <input type="text" v-model="question.options[oIndex]" :aria-label="`Question ${qIndex + 1} choice ${oIndex + 1}`" :placeholder="choicePlaceholder(oIndex)" />
                          <button v-if="question.options.length > 1" type="button" class="btn-icon btn-quiet btn-danger" :aria-label="`Remove choice ${oIndex + 1}`" @click="removeOption(qIndex, oIndex)"><UiIcon name="close" /></button>
                        </div>
                      </TransitionGroup>
                      <button type="button" class="btn-add-option" @click="addOption(qIndex)"><UiIcon name="plus" />Add choice</button>
                    </div>
                    <div v-else-if="question.type === 'Date poll'" class="date-poll-edit">
                      <p class="callout">Members say whether each date works, works if needed, or can’t work. This picks <strong>when</strong>; it doesn’t change which option wins. You choose the final date when you confirm.</p>
                      <p class="choices-label">Dates to offer</p>
                      <TransitionGroup name="list" tag="div">
                        <div v-for="(_, dIndex) in question.options" :key="`${keyOf(question)}-d${dIndex}`" class="option-row">
                          <input type="date" v-model="question.options[dIndex]" :aria-label="`Date option ${dIndex + 1}`" :aria-invalid="flag(4, !question.options[dIndex])" />
                          <span class="date-day" aria-hidden="true">{{ weekday(question.options[dIndex] || "") }}</span>
                          <button v-if="question.options.length > 1" type="button" class="btn-icon btn-quiet btn-danger" :aria-label="`Remove date ${dIndex + 1}`" @click="question.options.splice(dIndex, 1)"><UiIcon name="close" /></button>
                        </div>
                      </TransitionGroup>
                      <button v-if="question.options.length < 14" type="button" class="btn-add-option" @click="addPollDate(question)"><UiIcon name="plus" />Add date</button>
                    </div>
                    <p v-else-if="question.type === 'Option rating'" class="callout">Members rate every option from “Not for me” to “Love it”. Their ratings count as a preference alongside your other questions, and options they love rank higher.</p>
                    <p v-else-if="question.type === 'Duration'" class="callout">Members enter a start and end date. Dates are collected as context only and don’t generate scheduled options.</p>
                    <p v-else-if="question.type === 'Boolean'" class="callout">Members answer yes or no.</p>
                    <p v-else-if="question.type === 'Short answer'" class="callout">Members describe their preferences or requirements in their own words. They review the interpretation and confirm requirements before submitting.</p>
                    <div v-else-if="question.type === 'Number'" class="input-row">
                      <label>Unit <span class="optional">(optional)</span><input v-model="question.unit" placeholder="e.g. km, hours" /></label>
                      <label v-if="question.role !== 'hard'">Tolerance around the preferred value<input v-model.number="question.scale" type="number" min="0.000001" step="any" :aria-invalid="flag(4, question.role === 'soft' && !(Number(question.scale) > 0))" /></label>
                    </div>

                    <details v-if="question.role !== 'informational' && question.type !== 'Option rating'" class="comparison-settings"><summary>What this question compares</summary>
                      <label>Option detail to compare<input :value="question.criterion === 'preferences' ? 'All researched attributes' : factLabel(question.criterion || '')" placeholder="e.g. cuisine, atmosphere" @change="detailChanged(question,($event.target as HTMLInputElement).value)" /></label>
                      <p class="helper-text">Reuse a detail across questions. For a broad written answer, enter “All researched attributes”.</p>
                      <template v-if="question.criterion !== 'preferences'">
                        <label>Fact format<select v-model="question.valueType"><option value="category">Text</option><option value="tag_set">List of attributes</option><option value="boolean">Yes or no</option><option value="number">Number</option><option value="decimal">Currency amount</option></select></label>
                        <label v-if="['number','decimal'].includes(factType(question)) && question.type !== 'Number'">Unit<input v-model="question.unit" placeholder="e.g. km, hours, SGD" /></label>
                      </template>
                    </details>
                    <fieldset v-if="question.type !== 'Option rating' && question.type !== 'Date poll'" class="role-field">
                      <legend>How this answer is used</legend>
                      <div class="role-options">
                        <label v-for="r in roles" :key="r.value" class="choice-option role-option" :class="{ unavailable: lockedToContext(question) && r.value !== 'informational' }">
                          <input type="radio" :name="`role-${keyOf(question)}`" :value="r.value" v-model="question.role" :disabled="lockedToContext(question) && r.value !== 'informational'" />
                          <span><strong>{{ r.label }}</strong><small>{{ r.hint }}</small></span>
                        </label>
                      </div>
                      <p v-if="lockedToContext(question)" class="helper-text">Date answers are collected as context in this kind of form.</p>
                    </fieldset>
                    <fieldset v-if="(question.role || 'soft') === 'soft'" class="weight-field">
                      <legend>How much should this count?</legend>
                      <div class="weight-scale">
                        <label v-for="level in weightLevels" :key="level.value" :class="['weight-step', { on: (question.weightLevel || 'normal') === level.value }]">
                          <input type="radio" :name="`weight-${keyOf(question)}`" :value="level.value" :checked="(question.weightLevel || 'normal') === level.value" @change="question.weightLevel = level.value" />
                          <span>{{ level.label }}</span>
                        </label>
                      </div>
                      <p class="helper-text">{{ question.suggestedWeight ? `AI suggested “${weightName(question.suggestedWeight)}” for this decision.` : 'Applies to everyone.' }} Members can still say how much it matters to them.</p>
                    </fieldset>
                  </article>
                </TransitionGroup>
                <div class="question-actions">
                  <button type="button" class="add-question" @click="addQuestion"><UiIcon name="plus" />Add question</button>
                  <button v-if="!hasRating" type="button" class="btn-quiet" @click="addRatingQuestion">Ask them to rate each option</button>
                  <button v-if="!hasDatePoll" type="button" class="btn-quiet" @click="addDatePoll">Ask which dates work</button>
                  <button v-if="!form.questions.some(q => q.criterion === 'max_cost')" type="button" class="btn-quiet" @click="addBudgetQuestion">Add spending limit</button>
                  <button v-if="!form.questions.some(q => q.criterion === 'preferences')" type="button" class="btn-quiet" @click="addWrittenPreferences">Add general written preferences</button>
                </div>
              </div>

              <!-- 5: Review -->
              <div v-else key="5" class="step-card">
                <h2 ref="stepHeading" tabindex="-1" class="step-title">Review and publish</h2>
                <p class="step-lede">Check the plan, then publish it. You’ll get an invitation link to share on the next screen.</p>
                <section class="review-block">
                  <div class="review-heading"><h3>Plan</h3><button type="button" class="btn-quiet btn-small" @click="goToStep(1)">Edit<span class="sr-only"> plan details</span></button></div>
                  <dl class="summary-grid">
                    <div class="full-width"><dt>Name</dt><dd>{{ form.title }}</dd></div>
                    <div class="full-width"><dt>Main question</dt><dd>{{ form.decisionQuestion?.trim() || questionPlaceholder }}</dd></div>
                    <div v-if="form.description" class="full-width"><dt>Description</dt><dd class="multiline-summary">{{ form.description }}</dd></div>
                    <div><dt>Category</dt><dd>{{ form.category }}</dd></div>
                    <div><dt>Dates</dt><dd>{{ formatDate(form.startDateRange) }} – {{ formatDate(form.endDateRange) }}</dd></div>
                    <div class="full-width"><dt>Location</dt><dd>{{ form.location }}</dd></div>
                  </dl>
                </section>
                <section class="review-block">
                  <div class="review-heading"><h3>Options <span class="muted">{{ form.decisionOptions?.length || 0 }}</span></h3><button type="button" class="btn-quiet btn-small" @click="goToStep(2)">Edit<span class="sr-only"> options</span></button></div>
                  <ol class="review-list">
                    <li v-for="(option, index) in form.decisionOptions" :key="index"><span>{{ option.title }}</span><span class="muted">{{ kindName(option.identity?.kind) }}</span></li>
                  </ol>
                </section>
                <section class="review-block">
                  <div class="review-heading"><h3>Questions <span class="muted">{{ form.questions.length }}</span></h3><button type="button" class="btn-quiet btn-small" @click="goToStep(4)">Edit<span class="sr-only"> questions</span></button></div>
                  <ol class="review-list">
                    <li v-for="(question, index) in form.questions" :key="index"><span>{{ question.title }}</span><span class="muted">{{ roleLabel(question.role, question.type) }}<template v-if="(question.role || 'soft') === 'soft' && question.weightLevel && question.weightLevel !== 'normal'"> · counts {{ question.weightLevel }}</template></span></li>
                  </ol>
                </section>
                <section class="review-block deadline-block">
                  <div class="review-heading"><h3>Response deadline <span class="optional">(optional)</span></h3></div>
                  <label class="deadline-field">Collect answers until<input type="datetime-local" v-model="form.deadline" :min="nowLocal" /></label>
                  <p class="helper-text">Members see it as a countdown. You can change it, remind people or close early with the answers you have.</p>
                </section>
                <p class="helper-text">Option details were reviewed in Overview. You can publish while background research is still running; Decision supplements missing facts during processing.</p>
                <div v-if="warnings.length" class="callout warning">
                  <p><strong>Worth checking before you publish</strong></p>
                  <ul><li v-for="w in warnings" :key="w">{{ w }}</li></ul>
                </div>
              </div>
            </Transition>

            <div class="wizard-actions">
              <button type="button" class="btn-secondary" v-if="currentStep > 1" @click="prevStep"><UiIcon name="back" />Back</button>
              <button type="button" class="btn-primary" v-if="currentStep < 5" @click="nextStep">{{ currentStep === 2 ? 'Look them up' : currentStep === 3 ? 'Draft questions' : currentStep === 4 ? 'Review form' : 'Next step' }}<UiIcon name="arrow" /></button>
              <button type="submit" class="btn-primary btn-publish" v-else :aria-busy="isSaving">{{ isSaving ? 'Publishing…' : 'Publish form' }}<UiIcon v-if="!isSaving" name="arrow" /></button>
            </div>
          </fieldset>
        </form>
        <aside class="plan-summary" aria-label="Plan so far">
          <h2 class="summary-title">Plan so far</h2>
          <dl>
            <div><dt>Name</dt><dd :class="{ empty: !form.title?.trim() }">{{ form.title?.trim() || 'Not named yet' }}</dd></div>
            <div><dt>Category</dt><dd :class="{ empty: !form.category }">{{ form.category || 'Not chosen' }}</dd></div>
            <div><dt>Dates</dt><dd :class="{ empty: !form.startDateRange }">{{ form.startDateRange ? `${formatDate(form.startDateRange)}${form.endDateRange && form.endDateRange !== form.startDateRange ? ` – ${formatDate(form.endDateRange)}` : ''}` : 'Not set' }}</dd></div>
            <div><dt>Where</dt><dd :class="{ empty: !form.location?.trim() }">{{ form.location?.trim() || 'Not set' }}</dd></div>
            <div><dt>Options</dt><dd>{{ namedOptions }}</dd></div>
            <div><dt>Questions</dt><dd>{{ form.questions?.length || 0 }}</dd></div>
            <div v-if="form.deadline"><dt>Answers by</dt><dd>{{ formatDeadline(form.deadline) }}</dd></div>
          </dl>
          <p class="summary-note"><UiIcon name="lock" />Nothing is shared until you publish on the last step.</p>
          <p class="helper-text save-state" :role="storageFailed ? 'alert' : undefined">{{ storageFailed ? 'Browser storage is unavailable. Keep this page open; unsaved edits cannot survive refresh.' : recoveryMessage }}</p>
        </aside>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch, onMounted, onScopeDispose } from 'vue';
import OverviewCard from './OverviewCard.vue';
import FactReview from './FactReview.vue';
import { OPTION_RATING, factDefinitions, factSignature, factType, overviewSignature } from '@/services/optionFacts';
import { useAuthStore } from '@/stores/auth';
import type { DecisionOption, Form, OptionKind, Question, WeightLevel } from '@/types/form';
import UiIcon from './UiIcon.vue';
import { factLabel } from '@/services/facts';
import { apiService, ApiError } from '@/services/api.ts';
import { checkpointKey, readCheckpoint, writeCheckpoint, removeCheckpoint } from '@/services/checkpoints';
import { optionKey, useResearch, type OptionResearch } from '@/services/research';

const props = defineProps<{ planId?: string }>();
const emit = defineEmits<{
  (e: 'navigate', frame: string): void;
  (e: 'published', form: Form): void;
  (e: 'draft-saved', id: string): void;
}>();

const steps = ['Basics', 'Options', 'Overview', 'Questions', 'Review'];
const categories = [
  { value: 'Work', hint: 'Meetings, offsites, team decisions' },
  { value: 'Event', hint: 'Dinners, parties, celebrations' },
  { value: 'Travel', hint: 'Trips and getaways' },
  { value: 'General', hint: 'Anything else' },
];
const roles = [
  { value: 'soft', label: 'Preference', hint: 'Options that match rank higher' },
  { value: 'hard', label: 'Requirement', hint: 'Options that don’t match are ruled out' },
  { value: 'informational', label: 'Context only', hint: 'Collected, not used to rank' },
] as const;

const auth = useAuthStore();
const recoveryKey = checkpointKey(auth.userID, 'creator');
const saved = readCheckpoint<{ form: Form; step: number; visited: number; researchOptions?: Record<string, OptionResearch> }>(recoveryKey);
const restored = saved && (!props.planId || saved.form?.id === props.planId) && Array.isArray(saved.form?.questions) && Array.isArray(saved.form?.decisionOptions) && saved.form.state === 'Draft' ? saved : undefined;
const currentStep = ref(restored ? Math.max(1, Math.min(5, restored.step || 1)) : 1);
const visited = ref(restored?.visited || currentStep.value);
const direction = ref(1);
const attempted = reactive(new Set<number>());
const stepTop = ref<HTMLElement>();
const stepHeading = ref<HTMLElement>();

const form = reactive<Form>(restored?.form || {
  id: '', title: '', decisionQuestion: '', description: '', startDateRange: '', endDateRange: '', location: '', category: '',
  questions: [], state: 'Draft', currency: 'SGD',
  decisionOptions: [{ title: '', facts: [] }, { title: '', facts: [] }],
});

// Stable keys let list transitions follow the right item after a removal.
const keys = new WeakMap<object, number>(); let nextKey = 0;
function keyOf(item: object) { if (!keys.has(item)) keys.set(item, nextKey++); return keys.get(item)!; }
function identity(option: DecisionOption) { return option.identity ??= { source_url: '' }; }

let alive = true;
let autoSaveTimer: ReturnType<typeof setTimeout> | undefined;
onScopeDispose(() => { alive = false; clearTimeout(autoSaveTimer); });
const loadingDraft = ref(false); const draftLoadError = ref(''); const serverSaveError = ref('');
// Fact finding needs saved options (with IDs) and a draft round to research against.
let draftSave = Promise.resolve();
function saveDraftQuietly() {
  clearTimeout(autoSaveTimer);
  const save = draftSave.catch(() => undefined).then(async () => {
    if (alive) {
      form.wizardStep=currentStep.value;form.wizardVisited=visited.value;
      await apiService.saveFormDraft(form, auth.userID, auth.username);
      serverSaveError.value=''; recoveryMessage.value='Draft saved to the server. You can resume it from My forms using this session.';
      emit('draft-saved',form.id);
    }
  });
  draftSave = save;
  return save;
}
const research = useResearch(form, saveDraftQuietly);
const recoveryMessage = ref(restored ? 'Draft restored. Your changes and current step are kept in this browser tab.' : 'Changes are saved in this browser tab as you work.');
const storageFailed = ref(false);
const definitions = computed(() => factDefinitions(form));
// This optional editor displays stored option attributes, independently of any
// subsequent question edits. It never becomes a question readiness checklist.
const reviewDefinitions = computed(() => [...new Map((form.decisionOptions || []).flatMap(o => o.facts.map(f =>
  [f.criterion,{criterion:f.criterion,valueType:f.valueType,unit:f.unit}] as const))).values()]);
// Only option identity and attribute definition changes invalidate reusable facts.
function syncFactSignatures(){
  if(loadingDraft.value)return;
  for(const o of form.decisionOptions || []) for(const definition of reviewDefinitions.value) {
    const fact=o.facts.find(f=>f.criterion===definition.criterion); if(!fact)continue;
    const signature=factSignature(form,o,definition);
    if(fact.context?.input_signature===signature)continue;
    if(fact.context?.input_signature && fact.context.input_signature!==signature) fact.status='estimated';
    fact.context={...fact.context,...(fact.context?.input_signature && fact.context.input_signature!==signature ? {stale:true} : {}),input_signature:signature};
  }
}
watch(()=>JSON.stringify([form.currency,form.location,form.decisionOptions?.map(o=>[o.title,o.summary,o.identity]),reviewDefinitions.value]),syncFactSignatures,{flush:'sync',immediate:true});
watch(()=>form.currency,()=>{for(const q of form.questions)if(q.criterion==='max_cost')q.unit=form.currency || 'SGD';});
async function loadServerDraft(){
  if(!props.planId || (restored && restored.form.roundId))return;
  loadingDraft.value=true;draftLoadError.value='';
  try{ const row=await apiService.loadFormDraft(props.planId);
    if(restored && restored.form.roundId===row.roundId)return;
    Object.assign(form,row);
    if(!form.decisionOptions?.length)form.decisionOptions=[{title:'',facts:[]},{title:'',facts:[]}];
    currentStep.value=Math.max(1,Math.min(5,row.wizardStep || 1));visited.value=Math.max(currentStep.value,row.wizardVisited || 1);
    recoveryMessage.value='Saved draft loaded from the server. Review any changes before publishing.';
  }catch(e){draftLoadError.value=e instanceof Error ? e.message:'Could not load the saved draft.';}
  finally{loadingDraft.value=false;syncFactSignatures();}
}
async function saveServerDraft(){try{await saveDraftQuietly();}catch(e){serverSaveError.value=`Server save failed. Your edits remain in this tab. ${e instanceof Error ? e.message : ''}`;}}
for (const option of form.decisionOptions || []) {
  if (option.brief) {
    if(option.brief.source!=='organiser')option.overview = { ...option.brief,source:option.brief.source };
    const status = restored?.researchOptions?.[optionKey(option)];
    if (status) research.state.options[optionKey(option)] = status;
  }
}
watch([form, currentStep, visited, research.state.options], () => {
  if (form.state !== 'Draft') return;
  // Google Places display content/photos are live-only. Keep our web brief and place ID.
  const copy = JSON.parse(JSON.stringify(form)) as Form;
  for (const option of copy.decisionOptions || []) delete option.overview;
  storageFailed.value = !writeCheckpoint(recoveryKey, { form: copy, step: currentStep.value, visited: visited.value, researchOptions: research.state.options });
  clearTimeout(autoSaveTimer);
  if(alive && !loadingDraft.value && !draftLoadError.value && !isSaving.value && form.title.trim() && form.category && !form.publishAttempted) autoSaveTimer=setTimeout(saveServerDraft,800);
}, { deep: true, flush: 'sync' });
onMounted(async () => {
  await loadServerDraft();
  if (draftLoadError.value || (!restored && !props.planId) || form.publishAttempted) return;
  // A refresh can interrupt the debounced save after a result/edit was written
  // to the tab checkpoint. Resume that server save even if no new edit occurs.
  if (restored && form.title.trim() && form.category) void saveServerDraft();
  for(const option of form.decisionOptions || []) for(const definition of definitions.value){const f=option.facts.find(f=>f.criterion===definition.criterion);if(f?.context?.research_refresh_id) await research.researchAgain(option,definition,String(f.context.research_note || ''));}
  if (currentStep.value >= 3) {
    startOverviews();
    for (const option of form.decisionOptions || []) if (option.identity?.place_id && form.roundId) {
      apiService.placeCard(form.roundId, option.identity.place_id).then(live => {
        if (alive) option.overview = { ...live, ...option.brief, source: live.source };
      }).catch(() => undefined);
    }
  }
  const pending = reviewDefinitions.value.filter(d => form.decisionOptions?.some(o=>o.facts.some(f=>f.criterion===d.criterion && f.context?.research_pending)));
  if (pending.length) void research.facts(pending);
});

const namedOptions = computed(() => (form.decisionOptions || []).filter(o => o.title.trim()).length);
const placesHint = computed(() => (form.decisionOptions || []).some(o => o.overview?.source === 'google_places') ? ' with Google Maps and the web' : ' on the web');
function kindName(kind?: OptionKind) { return ({ place: 'Place', destination: 'Destination', event: 'Event', activity: 'Activity' } as Record<string, string>)[kind || ''] || 'Option'; }
async function changeKind(option: DecisionOption, kind: OptionKind) {
  option.identity = { ...option.identity, kind, ...(kind === 'place' || kind === 'destination' ? {} : { place_id: undefined }) };
  await retryOverview(option);
}
async function retryOverview(option: DecisionOption) { try{await research.overviews(option);}catch(e){research.state.message=e instanceof Error ? e.message:'The draft could not be saved for research. Your current overview was kept.';} }
function correctOverview(option:DecisionOption,value:string){ option.summary=value;option.brief={source:'organiser',summary:value,highlights:[],price_note:'',when:'',where:'',sources:[],input_signature:overviewSignature(form,option)}; }

// Criteria come from the question wording, so a new question gets its own fact.
function slug(text: string) { return text.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').replace(/^(\d)/, 'q_$1').slice(0, 50) || 'preference'; }
function ensureCriterion(q: Question, index: number) {
  if (q.criterion || q.role === 'informational') return;
  const base = slug(q.title) || `preference_${index + 1}`;
  let name = base, n = 2;
  while (form.questions.some(o => o !== q && o.criterion === name)) name = `${base}_${n++}`;
  q.criterion = name;
}

const weightLevels: { value: WeightLevel; label: string }[] = [{ value: 'less', label: 'Less' }, { value: 'normal', label: 'Normal' }, { value: 'more', label: 'More' }];
function weightName(level: WeightLevel) { return weightLevels.find(l => l.value === level)?.label || 'Normal'; }
const hasRating = computed(() => form.questions.some(q => q.type === 'Option rating'));
const nowLocal = computed(() => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); });
function formatDeadline(value: string) { const d = new Date(value); return Number.isNaN(d.getTime()) ? '' : d.toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' }); }
const hasDatePoll = computed(() => form.questions.some(q => q.type === 'Date poll'));
// Offer each day of the plan's window (up to a week) as a starting point.
function windowDates() {
  if (!form.startDateRange) return [];
  const days: string[] = []; const end = form.endDateRange || form.startDateRange;
  for (let d = new Date(`${form.startDateRange}T00:00:00Z`); d.toISOString().slice(0, 10) <= end && days.length < 7; d.setUTCDate(d.getUTCDate() + 1)) days.push(d.toISOString().slice(0, 10));
  return days;
}
function addDatePoll() { form.questions.push({ title: 'Which dates work for you?', description: 'Mark every date you could make.', role: 'informational', type: 'Date poll', criterion: 'context', options: windowDates().length ? windowDates() : [''] }); }
function addPollDate(q: Question) {
  const last = [...q.options].filter(Boolean).sort().pop();
  if (!last) { q.options.push(''); return; }
  const next = new Date(`${last}T00:00:00Z`); next.setUTCDate(next.getUTCDate() + 1); q.options.push(next.toISOString().slice(0, 10));
}
function weekday(value: string) { return value ? new Date(`${value}T00:00:00Z`).toLocaleDateString(undefined, { weekday: 'short', timeZone: 'UTC' }) : ''; }
function addRatingQuestion() { form.questions.push({ title: 'How do you feel about each option?', description: 'Go with your gut. Rate every option.', role: 'soft', type: 'Option rating', criterion: OPTION_RATING, options: [] }); }
function hasChoices(q: Question) { return ['Single choice', 'Multiple choice', 'Location', 'Budget'].includes(q.type); }
function lockedToContext(q: Question) { return q.type === 'Duration'; }
function typeChanged(q: Question) {
  if (q.type === 'Option rating') { q.role = 'soft'; q.criterion = OPTION_RATING; q.options = []; q.valueType = undefined; return; }
  if (q.type === 'Date poll') { q.role = 'informational'; q.criterion = 'context'; q.options = windowDates().length ? windowDates() : ['']; q.valueType = undefined; return; }
  if (q.criterion === OPTION_RATING) q.criterion = '';
  if (lockedToContext(q)) q.role = 'informational';
  if (hasChoices(q) && !q.options.length) q.options.push('', '');
  // Answer format and fact type are separate. Existing facts survive changes
  // from choices to written answers; explicit fact-format edits require review.
  if(q.type==='Number')q.valueType=q.criterion==='max_cost'?'decimal':'number';
  else if(q.type==='Boolean')q.valueType='boolean';
  else if(q.type==='Multiple choice')q.valueType='tag_set';
  else q.valueType ??= factType(q);
  if (q.type === 'Number' && q.role === 'soft' && !q.scale) q.scale = 1;
  if (q.criterion === 'max_cost') q.unit = form.currency || 'SGD';
}
function choicePlaceholder(i: number) { return `Choice ${i + 1}`; }
function roleLabel(role?: string, type?: string) { if (type === 'Option rating') return 'Rating'; if (type === 'Date poll') return 'Dates'; return roles.find(r => r.value === (role || 'soft'))?.label; }
function formatDate(value: string) { return value ? new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : ''; }

// Category-specific wording when the organiser leaves the question blank.
const questionPlaceholder = computed(() => ({ Event: 'Where should we go?', Travel: 'Where should we travel?', Work: 'Which option should the team choose?' } as Record<string, string>)[form.category] || 'Which option should we choose?');
const optionPlaceholder = computed(() => ({ Event: 'e.g. Odette Singapore', Travel: 'e.g. Bali', Work: 'e.g. Marina Bay Sands Expo' } as Record<string, string>)[form.category] || 'e.g. First option');
const datesReversed = computed(() => !!form.startDateRange && !!form.endDateRange && form.endDateRange < form.startDateRange);
const dayCount = computed(() => form.startDateRange && form.endDateRange && !datesReversed.value
  ? Math.round((Date.parse(form.endDateRange) - Date.parse(form.startDateRange)) / 86400000) + 1 : 0);
function validLink(value?: string) { if (!value?.trim()) return true; try { return ['http:', 'https:'].includes(new URL(value.trim()).protocol); } catch { return false; } }

// Each step's first problem, or '' when it's complete.
function problem(step: number): string {
  if (step === 1) {
    if (!form.title.trim() && !form.category) return 'Add a plan name and choose a category to continue.';
    if (!form.title.trim()) return 'Add a plan name to continue.';
    if (!form.category) return 'Choose a category to continue.';
    if (!form.startDateRange || !form.endDateRange) return 'Choose the earliest and latest dates to continue.';
    if (datesReversed.value) return 'The latest date must be on or after the earliest date.';
    if (!form.location.trim()) return 'Add a location or platform to continue.';
  }
  if (step === 2) {
    const named = (form.decisionOptions || []).filter(o => o.title.trim());
    if (named.length < 2) return 'Add at least two options to choose between.';
    if ((form.decisionOptions || []).some(o => !validLink(o.identity?.source_url))) return 'Check the website links; each should start with https://.';
  }
  if (step === 4) {
    if (!form.questions.length) return 'Add at least one question.';
    if (definitions.value.length > 8) return 'Use up to eight distinct option details; reuse them across questions.';
    if (form.questions.some(q => q.role !== 'informational' && q.criterion !== 'preferences' && !/^[a-z][a-z0-9_]{0,59}$/.test(q.criterion || ''))) return 'Choose an option detail for each scored question.';
    if (form.questions.some(q => !q.title.trim())) return 'Write each question, or remove the empty ones.';
    if (form.questions.some(q => hasChoices(q) && !q.options.some(o => o.trim()))) return 'Give each choice question at least one choice.';
    const poll = form.questions.find(q => q.type === 'Date poll');
    if (poll && (!poll.options.some(Boolean) || poll.options.some(d => !d) || new Set(poll.options).size !== poll.options.length)) return 'Give the date poll one or more different dates.';
    if (form.questions.some(q => q.type === 'Number' && q.role === 'soft' && !(Number(q.scale) > 0))) return 'Numeric preferences need a positive tolerance.';
  }
  return '';
}
function reachable(step: number) { for (let s = 1; s < Math.min(step, 6); s++) if (problem(s)) return false; return true; }
function flag(step: number, invalid: boolean) { return attempted.has(step) && invalid ? 'true' : undefined; }

const warnings = computed(() => {
  const list: string[] = [];
  if (form.questions.length && !form.questions.some(q => q.role !== 'informational')) list.push('Every question is context only, so all options will rank equally.');
  return list;
});

const saveError = ref('');
async function show(step: number) {
  direction.value = step >= currentStep.value ? 1 : -1;
  currentStep.value = step; visited.value = Math.max(visited.value, step); saveError.value = '';
  await nextTick();
  if (stepTop.value && stepTop.value.getBoundingClientRect().top < 0) stepTop.value.scrollIntoView({ block: 'start' });
  // Wait for the outgoing step to leave before moving focus to the new heading.
  setTimeout(() => stepHeading.value?.focus({ preventScroll: true }), 260);
}
function nextStep() {
  attempted.add(currentStep.value);
  const issue = problem(currentStep.value);
  if (issue) { saveError.value = issue; return; }
  if (currentStep.value === 2) { tidyOptions(); startOverviews(); }
  if (currentStep.value === 3) startQuestions();
  // Research can take minutes. Open review immediately, keep edits/navigation
  // available, and show its background progress instead of blocking this click.
  if (currentStep.value === 4) { void show(5); return; }
  if (currentStep.value < 5) show(currentStep.value + 1);
}
// Overviews run in the background while the organiser reads; saving happens first.
let overviewWork: Promise<void> | undefined;
function startOverviews() {
  overviewWork ??= research.overviews().catch(error => { research.state.message = error instanceof Error ? error.message : 'The draft could not be saved for research.'; }).finally(() => {
    overviewWork = undefined;
    // Prepare optional evidence while the leader reviews the options. Question
    // editing and publishing never start or wait for a facts checklist.
    if (alive && !form.publishAttempted && form.state==='Draft') void startQuestions();
  });
  return overviewWork;
}
// Questions are drafted once; later visits keep the organiser's edits.
async function startQuestions() {
  if (form.questions.length || form.publishAttempted) return;
  if (overviewWork) await overviewWork;
  if (!alive || form.publishAttempted || form.questions.length || research.state.questions === 'loading') return;
  const drafted = await research.draftQuestions();
  if (!alive || form.questions.length) return;
  form.questions.push(...(drafted.length ? drafted : [blankQuestion()]));
  await research.facts(definitions.value);
}
function prevStep() { if (currentStep.value > 1) show(currentStep.value - 1); }
function goToStep(target: number) {
  if (target === currentStep.value) return;
  for (let s = 1; s < target; s++) {
    const issue = problem(s);
    if (issue) { attempted.add(s); saveError.value = s === currentStep.value ? issue : `Finish “${steps[s - 1]}” first. ${issue}`; return; }
  }
  if (currentStep.value === 2) { tidyOptions(); startOverviews(); }
  if (target === 4) startQuestions();
  show(target);
}

const dirty = computed(() => !!(form.title || form.description || form.category || form.location || form.startDateRange || form.decisionOptions?.some(o => o.title)));
function leave() {
  if (storageFailed.value && dirty.value && !window.confirm('Browser storage is unavailable. Leaving may lose your unsaved edits. Continue?')) return;
  if(form.title.trim() && form.category && !form.publishAttempted){saveServerDraft().then(()=>{if(!serverSaveError.value)emit('navigate','dashboard');});}
  else emit('navigate', 'dashboard');
}

function addDecisionOption() { form.decisionOptions?.push({ title: '', facts: [], identity: { source_url: '' } }); }
function removeDecisionOption(index: number) {
  const [gone] = form.decisionOptions!.splice(index, 1);
  if (gone?.id) (form.removedOptionIds ??= []).push(gone.id);
}
// Enter on an option name moves to the next one, adding a row at the end.
async function enterOption(index: number) {
  if (index === (form.decisionOptions?.length || 0) - 1 && (form.decisionOptions?.length || 0) < 8 && form.decisionOptions![index]!.title.trim()) addDecisionOption();
  await nextTick();
  (document.querySelectorAll<HTMLInputElement>('.option-input input:not(.link-input)')[index + 1])?.focus();
}
function tidyOptions() {
  form.decisionOptions = (form.decisionOptions || []).filter(o => o.title.trim() || o.id);
  for (const o of form.decisionOptions) { o.title = o.title.trim(); if (o.identity?.source_url) o.identity.source_url = o.identity.source_url.trim(); }
}

const blankQuestion = (): Question => ({ title: '', description: '', role: 'soft', type: 'Short answer', valueType: 'category', criterion: '', options: [] });
const addQuestion = () => { form.questions.push(blankQuestion()); };
function addBudgetQuestion(){form.questions.push({title:`What is your maximum budget per person (${form.currency || 'SGD'})?`,description:'Options above a confirmed budget requirement are ruled out.',role:'hard',type:'Number',valueType:'decimal',criterion:'max_cost',unit:form.currency || 'SGD',options:[]});}
function addWrittenPreferences(){form.questions.push({title:'What preferences or requirements should we consider?',description:'Describe what matters, and distinguish preferences from must-haves.',role:'soft',type:'Short answer',criterion:'preferences',options:[]});}
function detailChanged(q:Question,value:string){q.criterion=value.trim().toLowerCase()==='all researched attributes' ? 'preferences' : slug(value);if(q.criterion==='max_cost'){q.valueType='decimal';q.unit=form.currency || 'SGD';}else if(q.criterion!=='preferences'){const existing=definitions.value.find(d=>d.criterion===q.criterion);if(existing){q.valueType=existing.valueType;q.unit=existing.unit;}}}
const removeQuestion = (index: number) => { const [gone] = form.questions.splice(index, 1); if (gone?.id) (form.removedQuestionIds ??= []).push(gone.id); };
const addOption = (qIndex: number) => { form.questions[qIndex]?.options.push(''); };
const removeOption = (qIndex: number, oIndex: number) => {
  const question = form.questions[qIndex];
  if (question && question.options.length > 1) question.options.splice(oIndex, 1);
};

const isSaving = ref(false);
const submitForm = async (): Promise<void> => {
  if (isSaving.value) return;
  for (let s = 1; s < 5; s++) if (problem(s)) { goToStep(s + 1); return; }
  form.questions.forEach(ensureCriterion);
  isSaving.value = true; saveError.value = '';
  clearTimeout(autoSaveTimer);
  try {
    // Empty choice rows are a typing convenience, not answers.
    for (const q of form.questions) if (hasChoices(q)) q.options = q.options.map(o => o.trim()).filter(Boolean);
      else if (q.type === 'Date poll') q.options = [...new Set(q.options.filter(Boolean))].sort();
      else q.options = [];
    if (!form.decisionQuestion?.trim()) form.decisionQuestion = questionPlaceholder.value;
    await draftSave;
    const saved = await apiService.publishForm(form, auth.userID, auth.username);
    removeCheckpoint(recoveryKey);
    emit('published', JSON.parse(JSON.stringify(saved)));
  } catch (error) {
    const text = error instanceof ApiError && error.code === 'INVALID_DEFINITION' ? 'Some questions don’t match the details they compare. Check the question types, then publish again.'
      : error instanceof Error ? error.message : 'Unable to publish.';
    saveError.value = text + (form.id ? ' Your draft is saved.' : '');
  } finally { isSaving.value = false; }
};
</script>

<style scoped>
.creator-wrapper { padding: clamp(28px, 5vh, 56px) var(--gutter) 40px; }
.creator-header { margin-bottom: 28px; }

/* Stepper: a horizontal route across the full width. */
.step-indicator-bar { margin-bottom: 28px; }
.step-list { position: relative; display: grid; grid-template-columns: repeat(var(--steps), minmax(0, 1fr)); gap: 8px; }
.step-track { position: absolute; left: calc(100% / var(--steps) / 2); right: calc(100% / var(--steps) / 2); top: 25px; height: 3px; border-radius: 3px; background: var(--sky-100); }
.step-track > span { display: block; height: 100%; border-radius: inherit; background: var(--blue); transform-origin: left; transform: scaleX(var(--value)); transition: transform 600ms var(--ease-out); }
.step-pill { position: relative; flex-direction: column; gap: 8px; border: 0; border-radius: 12px; background: transparent; padding: 6px 4px 8px; min-width: 0; color: var(--muted); font-size: .9375rem; }
.step-pill:hover:not(:disabled) { background: transparent; color: var(--ink); }
.step-pill:active:not(:disabled) { transform: none; }
.step-pill.active, .step-pill.active:hover:not(:disabled) { color: var(--blue-ink); }
.step-pill.completed { color: var(--ink); }
.step-pill.locked { color: var(--faint); }
.step-pill:disabled { background: transparent; }
.step-number { width: 40px; height: 40px; border: 2px solid var(--sky-200); border-radius: 50%; display: grid; place-items: center; font-size: .9375rem; font-weight: 600; background: var(--ground); transition: background-color var(--base) ease-out, border-color var(--base) ease-out, color var(--base) ease-out, transform 400ms var(--ease-out); }
.step-number .ui-icon { width: 18px; height: 18px; }
.step-pill:hover:not(:disabled) .step-number { border-color: var(--blue); }
.step-pill.active .step-number { background: var(--blue); border-color: var(--blue); color: #fff; transform: scale(1.08); }
.step-pill.completed .step-number { background: var(--surface); border-color: var(--blue); color: var(--blue); }
.step-label { overflow-wrap: anywhere; font-weight: 600; }

.builder-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(260px, 320px); gap: clamp(24px, 3vw, 48px); align-items: start; }
.form-builder { min-width: 0; }
.step-top { scroll-margin-top: 24px; }
.form-builder > [role='alert'] { margin-bottom: 16px; }
.step-card { background: var(--surface); padding: clamp(24px, 3vw, 40px); border: 1px solid var(--line); border-radius: 20px; box-shadow: var(--shadow-sm); }
.step-title { font-size: clamp(1.625rem, 1.3rem + .8vw, 2.125rem); font-weight: 300; letter-spacing: -.02em; color: var(--night); margin-bottom: 8px; }
.step-title:focus { outline: none; }
.step-lede { color: var(--muted); font-size: 1rem; margin-bottom: 8px; }
.step-card > label:first-of-type { margin-top: 28px; }
.step-card > label { margin-bottom: 8px; }
.step-card > input, .step-card > textarea { max-width: 760px; }
.step-card > input + .helper-text { margin-bottom: 4px; }
.field-error { color: var(--danger); }
.field-warning { color: var(--warn); }
.input-row { display: grid; grid-template-columns: 1fr 1fr; gap: 0 20px; max-width: 760px; }
.input-row label { margin-bottom: 8px; }
.category-field { margin-top: 28px; }
.category-field .choice-list { grid-template-columns: repeat(auto-fill, minmax(min(100%, 190px), 1fr)); }
.category-option { align-items: flex-start; }
.category-option input, .role-option input { margin-top: 2px; }
.category-option > span, .role-option > span { display: flex; flex-direction: column; gap: 2px; margin-left: 4px; }
.category-option small, .role-option small { color: var(--muted); font-weight: 400; font-size: .875rem; line-height: 1.4; }
.category-field[aria-invalid='true'] .choice-option:not(:has(:checked)) { border-color: #e2a3ab; }
.step-card > label:has(#meeting-location) { max-width: 760px; }

.sub-heading { font-size: 1.125rem; margin: 36px 0 4px; padding-top: 28px; border-top: 1px solid var(--line); }
.options-field { margin-top: 28px; }
.options-field legend .optional { font-variant-numeric: tabular-nums; margin-left: 6px; }
.option-inputs { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 420px), 1fr)); gap: 12px; }
.option-input { display: flex; align-items: flex-start; gap: 14px; padding: 14px; border: 1px solid var(--line); border-radius: 14px; background: var(--surface-2); transition: border-color var(--fast) ease-out; }
.option-input:focus-within { border-color: var(--sky-300); }
.option-index { display: grid; place-items: center; width: 32px; height: 32px; margin-top: 8px; border-radius: 50%; background: var(--night); color: #fff; font-size: .875rem; font-weight: 600; flex-shrink: 0; }
.option-fields { flex: 1; min-width: 0; display: grid; gap: 8px; }
.option-fields input:first-child { font-weight: 600; }
.link-input { font-size: .9375rem; min-height: 42px; }
.option-input > button { margin-top: 2px; }
.currency-field { max-width: 240px; margin-top: 28px; }
.overview-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 300px), 1fr)); gap: 16px; margin-top: 24px; }
.card-tools { display: flex; align-items: flex-end; justify-content: space-between; gap: 10px; margin-top: auto; padding-top: 14px; }
.kind-field { margin: 0; font-size: .8125rem; }
.kind-field select { min-height: 38px; padding: 4px 36px 4px 12px; font-size: .875rem; margin-top: 4px; }
.overview-note { margin-top: 18px; }
.drafting { display: flex; align-items: center; gap: 12px; margin-top: 18px; padding: 14px 18px; border-radius: 12px; background: var(--sky-50); color: var(--ink-2); font-size: .9375rem; }
.pulse { width: 10px; height: 10px; border-radius: 50%; background: var(--blue); animation: pulse 1.2s ease-in-out infinite; }
.question-list { display: grid; gap: 16px; margin-top: 24px; }
.question-card { border: 1px solid var(--line); border-radius: 16px; padding: 20px 24px 24px; background: var(--surface-2); transition: border-color var(--fast) ease-out; }
.question-card:focus-within { border-color: var(--sky-300); }
.question-top { display: flex; align-items: center; justify-content: space-between; min-height: 36px; margin-bottom: 4px; }
.question-top h3 { margin: 0; font-size: .875rem; color: var(--muted); font-weight: 600; }
.question-header { display: grid; grid-template-columns: minmax(0, 1fr) 220px; gap: 0 16px; }
.question-header label, .question-card > label { margin: 10px 0; }
.question-title-field input { font-weight: 600; }
.choices { margin: 18px 0 8px; }
.choices-label { font-size: .9375rem; font-weight: 600; margin-bottom: 10px; }
.option-row { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; max-width: 640px; }
.choice-marker { width: 18px; height: 18px; border: 2px solid var(--sky-300); border-radius: 50%; flex-shrink: 0; }
.choice-marker.square { border-radius: 4px; }
.btn-add-option { background: transparent; border-color: transparent; color: var(--blue-ink); padding-left: 4px; }
.btn-add-option:hover:not(:disabled) { background: var(--sky-50); border-color: transparent; padding-left: 14px; }
.question-card .callout { margin: 16px 0 4px; }
.role-field { margin-top: 20px; padding-top: 18px; border-top: 1px solid var(--line); }
.role-options { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.role-option { align-items: flex-start; }
.role-option.unavailable { opacity: .55; }
.weight-field { margin-top: 18px; padding-top: 16px; border-top: 1px solid var(--line); }
.weight-field legend { margin-bottom: 10px; }
.weight-scale { display: inline-grid; grid-auto-flow: column; grid-auto-columns: minmax(84px, 1fr); padding: 3px; border-radius: 999px; background: var(--sky-50); border: 1px solid var(--line); }
.weight-step { position: relative; margin: 0; cursor: pointer; }
.weight-step input { position: absolute; opacity: 0; width: 1px; height: 1px; }
.weight-step span { display: block; padding: 7px 16px; border-radius: 999px; font-size: .875rem; font-weight: 600; color: var(--ink-2); text-align: center; transition: background-color 200ms var(--ease-out), color 200ms var(--ease-out); }
.weight-step:hover span { color: var(--blue-ink); }
.weight-step.on span { background: var(--blue); color: #fff; box-shadow: var(--shadow-sm); }
.weight-step:has(:focus-visible) span { outline: 2px solid var(--blue); outline-offset: 2px; }
.question-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 20px; }
.add-question { margin: 0; }

.review-block { padding: 22px 0; border-top: 1px solid var(--line); }
.review-block:first-of-type { margin-top: 20px; }
.review-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.review-heading h3 { margin: 0; font-size: 1.125rem; display: flex; gap: 8px; align-items: baseline; }
.review-heading h3 .muted { font-size: .875rem; font-weight: 500; font-variant-numeric: tabular-nums; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 240px), 1fr)); gap: 16px 28px; font-size: 1rem; margin: 0; }
.summary-grid div { min-width: 0; overflow-wrap: anywhere; }
.summary-grid dt { color: var(--muted); font-size: .8125rem; margin-bottom: 2px; }
.summary-grid dd { margin: 0; }
.full-width { grid-column: 1 / -1; }
.multiline-summary { white-space: pre-wrap; }
.review-list { list-style: none; margin: 0; padding: 0; counter-reset: item; }
.review-list li { counter-increment: item; display: flex; justify-content: space-between; gap: 16px; padding: 11px 0; font-size: .9375rem; border-bottom: 1px solid var(--line); overflow-wrap: anywhere; }
.review-list li:last-child { border-bottom: 0; }
.review-list li > span:first-child::before { content: counter(item); display: inline-block; min-width: 1.6em; color: var(--faint); font-variant-numeric: tabular-nums; }
.review-list .muted { flex-shrink: 0; font-size: .875rem; }
.callout.warning ul { margin: 0; padding-left: 20px; }
.deadline-field { max-width: 320px; margin: 8px 0 0; }
.date-poll-edit .option-row input { max-width: 220px; }
.date-day { min-width: 3ch; color: var(--muted); font-weight: 600; font-size: .875rem; }
.callout.warning li + li { margin-top: 4px; }

/* Actions stay in reach while long steps scroll. */
.wizard-actions { position: sticky; bottom: 0; z-index: 5; display: flex; justify-content: flex-end; gap: 12px; margin-top: 16px; padding: 14px 0 18px; background: var(--ground); }
.wizard-actions button { min-height: 48px; padding-inline: 24px; }
.btn-publish { min-width: 180px; }

.plan-summary { position: sticky; top: 24px; padding: 24px; border-radius: 20px; background: var(--surface); border: 1px solid var(--line); }
.summary-title { font-size: 1rem; margin-bottom: 14px; }
.plan-summary dl { margin: 0; display: grid; gap: 0; }
.plan-summary dl > div { display: flex; justify-content: space-between; gap: 16px; padding: 10px 0; border-top: 1px solid var(--line); font-size: .9375rem; }
.plan-summary dt { color: var(--muted); flex-shrink: 0; }
.plan-summary dd { margin: 0; font-weight: 600; text-align: right; overflow-wrap: anywhere; min-width: 0; }
.plan-summary dd.empty { color: var(--faint); font-weight: 400; }
.summary-note { display: flex; gap: 8px; font-size: .875rem; color: var(--ink-2); margin: 16px 0 0; padding: 12px 14px; border-radius: 12px; background: var(--sky-50); }
.summary-note .ui-icon { width: 17px; height: 17px; margin-top: 2px; color: var(--blue); }
.save-state { margin-top: 12px; }

/* Step changes slide in the direction of travel. */
.step-forward-enter-active, .step-back-enter-active { transition: opacity 320ms var(--ease-out), transform 320ms var(--ease-out); }
.step-forward-leave-active, .step-back-leave-active { transition: opacity 120ms var(--ease-in), transform 120ms var(--ease-in); }
.step-forward-enter-from { opacity: 0; transform: translateX(24px); }
.step-forward-leave-to { opacity: 0; transform: translateX(-12px); }
.step-back-enter-from { opacity: 0; transform: translateX(-24px); }
.step-back-leave-to { opacity: 0; transform: translateX(12px); }

@media(max-width: 1180px) { .builder-layout { grid-template-columns: minmax(0, 1fr); } .plan-summary { position: static; } .plan-summary dl { grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); column-gap: 24px; } }
@media(max-width: 900px) { .role-options { grid-template-columns: minmax(0, 1fr); } .question-header { grid-template-columns: minmax(0, 1fr); } }
@media(max-width: 860px) { .wizard-actions { bottom: calc(66px + env(safe-area-inset-bottom)); } }
@media(max-width: 700px) {
  .creator-wrapper { padding: 24px 16px 32px; }
  .step-list { gap: 2px; }
  .step-track { top: 19px; }
  .step-pill { font-size: .75rem; gap: 6px; padding: 4px 0; }
  .step-number { width: 32px; height: 32px; font-size: .8125rem; }
  .step-card { padding: 20px; border-radius: 16px; }
  .question-card { padding: 16px; }
  .option-inputs { grid-template-columns: minmax(0, 1fr); }
  .input-row { grid-template-columns: minmax(0, 1fr); gap: 0; }
  .wizard-actions { gap: 8px; padding: 10px 0 12px; } .wizard-actions button { min-height: 46px; padding-inline: 18px; }
  .wizard-actions button:last-child { flex: 1; justify-content: space-between; }
}
@media(max-width:380px) { .step-label { font-size: .6875rem; } .step-number { width: 28px; height: 28px; } .step-track { top: 17px; } }
</style>
