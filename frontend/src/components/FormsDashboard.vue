<template>
  <main id="main-content" tabindex="-1" class="dashboard">
    <header class="page-heading dash-head">
      <div>
        <h1>Your plans, in one place.</h1>
        <p>Create a form, gather your group’s input, and keep the decision moving.</p>
      </div>
      <div class="head-actions">
        <button @click="emit('navigate', 'join')"><UiIcon name="link" />Join with a link</button>
        <button class="btn-primary" @click="emit('navigate', 'creator')"><UiIcon name="plus" />Create form</button>
      </div>
    </header>
    <section class="plans-section" aria-labelledby="plans-heading">
      <div class="list-heading">
        <h2 id="plans-heading">My forms</h2>
        <button
          :class="['btn-quiet', 'btn-icon', { spinning: isLoading }]"
          aria-label="Refresh forms"
          :disabled="isLoading"
          @click="fetchForms"
        >
          <UiIcon name="refresh" />
        </button>
      </div>
      <div v-if="isLoading" role="status" class="loading-state">
        <p class="sr-only">Loading your forms…</p>
        <div
          v-for="n in 4"
          :key="n"
          class="skeleton"
          aria-hidden="true"
          :style="{ animationDelay: `${n * 90}ms` }"
        ></div>
      </div>
      <div v-else-if="errorMessage" class="state-card">
        <h3>We couldn’t load your forms.</h3>
        <p role="alert">{{ errorMessage }}</p>
        <button @click="fetchForms"><UiIcon name="refresh" />Try again</button>
      </div>
      <div v-else-if="!forms.length" class="empty-state rise">
        <div class="empty-copy">
          <h3>What would you like to decide?</h3>
          <p>
            Start with a plan. Add the choices you’re considering, then invite your group to share what matters to them.
          </p>
          <div class="actions">
            <button class="btn-primary" @click="emit('navigate', 'creator')">Create form<UiIcon name="arrow" /></button
            ><button class="btn-quiet" @click="emit('navigate', 'join')">I have an invitation link</button>
          </div>
        </div>
        <ol class="empty-route" aria-label="How it works">
          <li>
            <span class="stop" aria-hidden="true"></span>
            <div>
              <strong>Add the options</strong><span>A team activity, an upcoming event, your next shared plan.</span>
            </div>
          </li>
          <li>
            <span class="stop" aria-hidden="true"></span>
            <div><strong>Invite your group</strong><span>They answer privately on any device.</span></div>
          </li>
          <li>
            <span class="stop" aria-hidden="true"></span>
            <div><strong>Confirm the result</strong><span>Compare the ranking and collect RSVPs.</span></div>
          </li>
        </ol>
      </div>
      <template v-else>
        <div class="list-tools">
          <label class="search-field"
            ><span class="sr-only">Search forms</span><UiIcon name="search" /><input
              v-model="query"
              type="search"
              placeholder="Search by title"
          /></label>
          <label class="filter-field"
            ><span class="sr-only">Filter by status</span
            ><select v-model="status">
              <option v-for="option in statusOptions" :key="option.value" :value="option.value">
                {{ option.value ? option.label : 'All statuses' }} ({{ option.count }})
              </option>
            </select></label
          >
        </div>
        <p v-if="!filteredForms.length" class="no-results" role="status">
          No forms match your search.
          <button
            class="btn-quiet btn-small"
            @click="
              query = '';
              status = '';
            "
          >
            Clear filters
          </button>
        </p>
        <div v-else class="table-container">
          <table class="forms-table">
            <caption class="sr-only">
              Your forms and their current status
            </caption>
            <thead>
              <tr>
                <th scope="col">Plan</th>
                <th scope="col">Status</th>
                <th scope="col" class="numeric-head">Members</th>
                <th scope="col">Created by</th>
                <th scope="col">Category</th>
                <th scope="col"><span class="sr-only">Open plan</span></th>
              </tr>
            </thead>
            <TransitionGroup tag="tbody" name="list"
              ><tr
                v-for="(form, index) in filteredForms"
                :key="form.id"
                class="rise"
                :style="{ '--i': index }"
                @click="rowClick($event, form.id)"
              >
                <td class="plan-cell">
                  <button class="plan-title" @click="emit('open-plan', form.id)">{{ form.title }}</button>
                </td>
                <td data-label="Status">
                  <span :class="['badge', form.state?.toLowerCase()]">{{ form.state }}</span>
                </td>
                <td data-label="Members" class="numeric">{{ form.membersCount ?? '—' }}</td>
                <td data-label="Created by" class="person">{{ form.createdBy }}</td>
                <td data-label="Category">{{ form.category }}</td>
                <td class="open-cell">
                  <div class="row-actions">
                    <button
                      v-if="canDeleteDraft(form)"
                      class="btn-quiet btn-danger btn-icon"
                      :disabled="deletingId === form.id"
                      :aria-label="`Delete draft ${form.title}`"
                      @click.stop="deleteDraft(form)"
                    >
                      <UiIcon name="close" /></button
                    ><button
                      class="btn-quiet btn-icon open-button"
                      :aria-label="`Open ${form.title}`"
                      @click="emit('open-plan', form.id)"
                    >
                      <UiIcon name="arrow" />
                    </button>
                  </div>
                </td></tr
            ></TransitionGroup>
          </table>
        </div>
        <p class="list-note">
          {{
            filteredForms.length === forms.length
              ? `${forms.length} ${forms.length === 1 ? 'form' : 'forms'}`
              : `Showing ${filteredForms.length} of ${forms.length} forms`
          }}
          you organise or have joined. Open a saved draft to continue setting it up.
        </p>
      </template>
    </section>
  </main>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import type { Form } from '@/types/form';
import { apiService } from '@/services/api';
import { checkpointKey, readCheckpoint, removeCheckpoint } from '@/services/checkpoints';
import { useAuthStore } from '@/stores/auth';
import UiIcon from './UiIcon.vue';
const authStore = useAuthStore();
const emit = defineEmits<{ (e: 'navigate', frame: string): void; (e: 'open-plan', id: string): void }>();
const forms = ref<Form[]>([]);
const isLoading = ref(true);
const errorMessage = ref('');
const deletingId = ref('');
const query = ref('');
const status = ref('');
const order = ['Draft', 'Collecting', 'Reviewing', 'Confirmed', 'Archived'];
const statusOptions = computed(() => [
  { value: '', label: 'All', count: forms.value.length },
  ...[...new Set(forms.value.map((form) => form.state))]
    .sort((a, b) => order.indexOf(a) - order.indexOf(b))
    .map((state) => ({ value: state, label: state, count: forms.value.filter((form) => form.state === state).length })),
]);
// The whole row opens the plan; the title button stays the keyboard target.
function rowClick(event: MouseEvent, id: string) {
  if (!(event.target as HTMLElement).closest('button') && !getSelection()?.toString()) emit('open-plan', id);
}
const filteredForms = computed(() =>
  forms.value.filter(
    (form) =>
      form.title.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase()) &&
      (!status.value || form.state === status.value),
  ),
);
function canDeleteDraft(form: Form) {
  return form.state === 'Draft' && (!form.createdByUserId || form.createdByUserId === authStore.userID);
}
async function deleteDraft(form: Form) {
  if (deletingId.value || !window.confirm(`Delete draft “${form.title}”? This cannot be undone.`)) return;
  deletingId.value = form.id;
  errorMessage.value = '';
  try {
    await apiService.deletePlan(form.id);
    const key = checkpointKey(authStore.userID, 'creator');
    const saved = readCheckpoint<{ form?: { id?: string } }>(key);
    if (saved?.form?.id === form.id) removeCheckpoint(key);
    forms.value = forms.value.filter((row) => row.id !== form.id);
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : 'Could not delete the draft.';
  } finally {
    deletingId.value = '';
  }
}
async function fetchForms() {
  if (!authStore.userID) {
    errorMessage.value = 'Resume your session, then try again.';
    isLoading.value = false;
    return;
  }
  isLoading.value = true;
  errorMessage.value = '';
  try {
    forms.value = await apiService.getForms(authStore.userID);
  } catch {
    errorMessage.value = 'Check that the system is running, then try again.';
  } finally {
    isLoading.value = false;
  }
}
onMounted(fetchForms);
</script>
<style scoped>
.dashboard {
  padding: clamp(28px, 5vh, 56px) var(--gutter) 80px;
}
.dash-head h1 {
  margin-bottom: 8px;
}
.head-actions {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}
.plans-section {
  margin-top: 40px;
}
.list-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.list-heading h2 {
  margin: 0;
}
.list-tools {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.list-tools label {
  margin: 0;
}
.filter-field select {
  min-height: 46px;
  min-width: 200px;
}
.search-field {
  position: relative;
  width: min(380px, 100%);
}
.search-field .ui-icon {
  position: absolute;
  top: 14px;
  left: 14px;
  color: var(--muted);
}
.list-tools .search-field input {
  padding-left: 44px;
  margin: 0;
  min-height: 46px;
}
.table-container {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}
.forms-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  table-layout: fixed;
}
.forms-table th {
  color: var(--muted);
  font-size: 0.8125rem;
  font-weight: 600;
  padding: 14px 20px;
  background: var(--surface-2);
  border-bottom: 1px solid var(--line);
}
.forms-table th:first-child {
  width: 36%;
  padding-left: 24px;
}
.forms-table th:last-child {
  width: 112px;
}
.numeric-head,
.forms-table td.numeric {
  text-align: right;
  padding-right: 36px;
}
.row-actions {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  width: 100%;
}
.forms-table td {
  padding: 16px 20px;
  border-top: 1px solid var(--line);
  font-size: 0.9375rem;
  overflow-wrap: anywhere;
  vertical-align: middle;
}
.forms-table tbody tr:first-child td {
  border-top: 0;
}
.forms-table td.plan-cell {
  padding-left: 24px;
}
.forms-table tbody tr {
  cursor: pointer;
}
.forms-table tbody td {
  transition: background-color var(--fast) ease-out;
}
.forms-table tbody tr:hover td {
  background: var(--sky-50);
}
.forms-table tbody tr:hover .open-button .ui-icon {
  transform: translateX(3px);
  color: var(--blue);
}
.person {
  color: var(--ink-2);
}
.spinning .ui-icon {
  animation: spin 900ms linear infinite;
}
.plan-title {
  border: 0;
  border-radius: 4px;
  background: transparent;
  padding: 4px 0;
  min-height: 0;
  font-weight: 600;
  font-size: 1.0625rem;
  text-align: left;
  justify-content: flex-start;
  overflow-wrap: anywhere;
  color: var(--ink);
}
.plan-title:hover:not(:disabled) {
  background: transparent;
  color: var(--blue);
  text-decoration: underline;
  text-underline-offset: 4px;
}
.plan-title:active:not(:disabled) {
  transform: none;
}
.list-note {
  color: var(--muted);
  font-size: 0.875rem;
  margin: 16px 0 0;
}
.loading-state .skeleton {
  height: 58px;
}
.state-card {
  padding: 40px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}
.empty-state {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
  gap: clamp(32px, 6vw, 96px);
  align-items: center;
  padding: clamp(32px, 5vw, 64px);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 20px;
}
.empty-state h3 {
  font-size: clamp(1.75rem, 1.3rem + 1.2vw, 2.5rem);
  font-weight: 300;
  letter-spacing: -0.02em;
  line-height: 1.12;
  color: var(--night);
  margin-bottom: 14px;
}
.empty-state p {
  color: var(--muted);
  font-size: 1.0625rem;
  max-width: 52ch;
  margin-bottom: 28px;
}
.empty-route {
  position: relative;
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 28px;
}
.empty-route::before {
  content: '';
  position: absolute;
  left: 9px;
  top: 12px;
  bottom: 12px;
  width: 2px;
  background: var(--sky-200);
  transform-origin: top;
  animation: draw-down 1200ms 200ms var(--ease-io) both;
}
@keyframes draw-down {
  from {
    transform: scaleY(0);
  }
}
.empty-route li {
  position: relative;
  display: flex;
  gap: 18px;
  animation: rise 600ms var(--ease-out) both;
}
.empty-route li:nth-child(2) {
  animation-delay: 300ms;
}
.empty-route li:nth-child(3) {
  animation-delay: 600ms;
}
.empty-route .stop {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  margin-top: 2px;
  border-radius: 50%;
  background: var(--surface);
  border: 3px solid var(--blue);
}
.empty-route li:last-child .stop {
  background: var(--blue);
}
.empty-route div {
  display: grid;
}
.empty-route strong {
  font-size: 1.0625rem;
}
.empty-route div span {
  color: var(--muted);
  font-size: 0.9375rem;
}
.no-results {
  padding: 24px 0;
}
@media (max-width: 1000px) {
  .forms-table th,
  .forms-table td {
    padding: 14px;
  }
  .empty-state {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 700px) {
  .dashboard {
    padding: 24px 16px 40px;
  }
  .plans-section {
    margin-top: 28px;
  }
  .head-actions {
    flex-direction: column-reverse;
  }
  .head-actions button {
    width: 100%;
  }
  .empty-state,
  .state-card {
    padding: 24px 20px;
  }
  .list-tools {
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
  }
  .search-field {
    width: 100%;
  }
  .table-container {
    background: transparent;
    border: 0;
    box-shadow: none;
    overflow: visible;
  }
  .forms-table,
  .forms-table tbody {
    display: block;
  }
  .forms-table thead {
    display: none;
  }
  .forms-table tr {
    display: grid;
    transition: border-color var(--fast) ease-out;
    grid-template-columns: 1fr 1fr;
    padding: 16px 18px;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: var(--surface);
    margin-bottom: 10px;
  }
  .forms-table td,
  .forms-table td.plan-cell,
  .forms-table td.numeric {
    border: 0;
    padding: 6px 0;
    min-width: 0;
    text-align: left;
  }
  .forms-table td::before {
    content: attr(data-label);
    display: block;
    font-size: 0.75rem;
    color: var(--muted);
    margin-bottom: 2px;
  }
  .forms-table .plan-cell {
    grid-column: 1 / -1;
    padding: 0 0 10px;
    border-bottom: 1px solid var(--line);
    margin-bottom: 6px;
  }
  .forms-table .open-cell {
    grid-column: 1 / -1;
    padding: 0;
  }
  .open-cell::before {
    display: none;
  }
  .forms-table tbody tr:hover {
    border-color: var(--blue);
  }
  .forms-table tbody tr:hover td {
    background: transparent;
  }
}
</style>
