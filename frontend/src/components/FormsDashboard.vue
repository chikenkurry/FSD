<template>
  <main id="main-content" tabindex="-1" class="dashboard-wrapper">
    <header class="page-heading">
      <div><h1>Your plans, in one place.</h1><p>Create a form, gather your group’s input, and keep the decision moving.</p></div>
      <button class="btn-primary" @click="emit('navigate', 'creator')"><UiIcon name="plus" />Create form</button>
    </header>
    <section class="plans-section" aria-labelledby="plans-heading">
      <div class="list-heading"><h2 id="plans-heading">My forms <span v-if="!isLoading" class="list-count">{{ forms.length }}</span></h2><button :class="['btn-quiet', 'btn-icon', { spinning: isLoading }]" aria-label="Refresh forms" :disabled="isLoading" @click="fetchForms"><UiIcon name="refresh" /></button></div>
      <div v-if="isLoading" role="status" class="loading-state"><p>Loading your forms…</p><div v-for="n in 3" :key="n" class="skeleton" aria-hidden="true"></div></div>
      <div v-else-if="errorMessage" class="state-card"><h3>We couldn’t load your forms.</h3><p role="alert">{{ errorMessage }}</p><button @click="fetchForms">Try again</button></div>
      <div v-else-if="!forms.length" class="empty-state rise">
        <h3>What would you like to decide?</h3>
        <p>Start with a plan. Add the choices you’re considering, then invite your group to share what matters to them.</p>
        <button class="btn-primary" @click="emit('navigate', 'creator')">Create form<UiIcon name="arrow" /></button>
        <p class="empty-footnote">A team activity, an upcoming event, or your next shared plan.</p>
      </div>
      <template v-else>
        <div class="list-tools">
          <label class="search-field"><span class="sr-only">Search forms</span><UiIcon name="search" /><input v-model="query" type="search" placeholder="Search by title" /></label>
          <label class="filter-field"><span class="sr-only">Filter by status</span><select v-model="status"><option value="">All statuses</option><option v-for="state in states" :key="state">{{ state }}</option></select></label>
        </div>
        <p v-if="!filteredForms.length" class="no-results" role="status">No forms match your search. <button class="btn-quiet" @click="query = ''; status = ''">Clear filters</button></p>
        <div v-else class="table-container">
          <table class="forms-table">
            <caption class="sr-only">Your forms and their current status</caption>
            <thead><tr><th scope="col">Plan</th><th scope="col">Status</th><th scope="col">Members</th><th scope="col">Created by</th><th scope="col">Category</th><th scope="col"><span class="sr-only">Open plan</span></th></tr></thead>
            <TransitionGroup tag="tbody" name="list"><tr v-for="(form, index) in filteredForms" :key="form.id" class="rise" :style="{ '--i': index }" @click="rowClick($event, form.id)">
              <td class="plan-cell"><button class="plan-title" @click="emit('open-plan', form.id)">{{ form.title }}</button></td>
              <td data-label="Status"><span :class="['badge', form.state?.toLowerCase()]">{{ form.state }}</span></td>
              <td data-label="Members" class="numeric">{{ form.membersCount ?? '—' }}</td>
              <td data-label="Created by">{{ form.createdBy }}</td>
              <td data-label="Category">{{ form.category }}</td>
              <td class="open-cell"><button class="btn-quiet btn-icon" :aria-label="`Open ${form.title}`" @click="emit('open-plan', form.id)"><UiIcon name="arrow" /></button></td>
            </tr></TransitionGroup>
          </table>
        </div>
        <p class="list-note">{{ filteredForms.length === forms.length ? `${forms.length} ${forms.length === 1 ? 'form' : 'forms'}` : `Showing ${filteredForms.length} of ${forms.length} forms` }} you organise. Plans you’ve joined as a member open from their invitation link.</p>
      </template>
    </section>
  </main>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import type { Form } from '@/types/form';
import { apiService } from '@/services/api';
import { useAuthStore } from '@/stores/auth';
import UiIcon from './UiIcon.vue';
const authStore = useAuthStore();
const emit = defineEmits<{ (e: 'navigate', frame: string): void; (e: 'open-plan', id: string): void }>();
const forms = ref<Form[]>([]); const isLoading = ref(true); const errorMessage = ref('');
const query = ref(''); const status = ref('');
const states = computed(() => [...new Set(forms.value.map(form => form.state))]);
// The whole row opens the plan; the title button stays the keyboard target.
function rowClick(event: MouseEvent, id: string) { if (!(event.target as HTMLElement).closest('button') && !getSelection()?.toString()) emit('open-plan', id); }
const filteredForms = computed(() => forms.value.filter(form => form.title.toLocaleLowerCase().includes(query.value.trim().toLocaleLowerCase()) && (!status.value || form.state === status.value)));
async function fetchForms() {
  if (!authStore.userID) { errorMessage.value = 'Resume your session, then try again.'; isLoading.value = false; return; }
  isLoading.value = true; errorMessage.value = '';
  try { forms.value = await apiService.getForms(authStore.userID); }
  catch { errorMessage.value = 'Check that the system is running, then try again.'; }
  finally { isLoading.value = false; }
}
onMounted(fetchForms);
</script>
<style scoped>
.dashboard-wrapper { max-width: 1200px; margin: 0 auto; padding: 56px 32px 80px; }
.plans-section { margin-top: 48px; }
.list-heading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.list-heading h2 { display: flex; align-items: center; gap: 12px; margin: 0; }
.list-count { color: var(--muted); border: 1px solid #bdc9c0; border-radius: 5px; padding: 0 8px; font-size: .75rem; line-height: 24px; font-variant-numeric: tabular-nums; }
.list-tools { display: flex; gap: 12px; margin-bottom: 20px; }
.list-tools label { margin: 0; }
.search-field { position: relative; flex: 1; max-width: 360px; }
.search-field .ui-icon { position: absolute; top: 14px; left: 12px; color: var(--muted); }
.list-tools .search-field input { padding-left: 40px; margin: 0; }
.filter-field select { margin: 0; min-width: 160px; }
.table-container { border: 1px solid var(--line); border-radius: 12px; background: var(--surface); }
.forms-table { width: 100%; border-collapse: collapse; text-align: left; table-layout: fixed; }
.forms-table th { color: var(--muted); font-size: .75rem; font-weight: 600; padding: 14px 20px; background: #eef1ed; }
.forms-table th:first-child { border-radius: 12px 0 0 0; width: 35%; }
.forms-table th:last-child { border-radius: 0 12px 0 0; width: 64px; }
.forms-table td { padding: 14px 20px; border-top: 1px solid var(--line); font-size: .875rem; overflow-wrap: anywhere; }
.forms-table tbody tr { cursor: pointer; }
.forms-table tbody td { transition: background-color var(--fast) ease-out; }
.forms-table tbody tr:hover td { background: #f5f8f3; }
.forms-table tbody tr:hover .open-cell .ui-icon { transform: translateX(3px); color: var(--accent); }
.forms-table tbody tr:last-child td:first-child { border-bottom-left-radius: 12px; }
.forms-table tbody tr:last-child td:last-child { border-bottom-right-radius: 12px; }
.spinning .ui-icon { animation: spin 900ms linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.plan-title { border: 0; border-radius: 0; background: transparent; padding: 6px 0; font-weight: 600; text-align: left; justify-content: flex-start; overflow-wrap: anywhere; }
.plan-title:hover:not(:disabled) { background: transparent; color: var(--accent); text-decoration: underline; text-underline-offset: 4px; }
.numeric { font-variant-numeric: tabular-nums; }
.list-note, .empty-footnote { color: var(--muted); font-size: .75rem; margin: 16px 0 0; }
.state-card, .empty-state { padding: 48px 32px; background: #fff; border: 1px solid var(--line); border-radius: 12px; }
.empty-state h3 { font-size: 1.5rem; }
.empty-state > p:not(.empty-footnote) { color: var(--muted); max-width: 60ch; margin-bottom: 24px; }
.no-results { padding: 24px 0; }
@media(max-width: 800px) { .forms-table th, .forms-table td { padding: 12px; } }
@media(max-width: 700px) {
  .dashboard-wrapper { padding: 32px 20px 48px; } .plans-section { margin-top: 32px; } .empty-state, .state-card { padding: 28px 24px; }
  .list-tools { flex-direction: column; } .search-field { max-width: none; }
  .table-container { background: transparent; border: 0; }
  .forms-table, .forms-table tbody { display: block; }
  .forms-table thead { display: none; }
  .forms-table tr { display: grid; transition: border-color var(--fast) ease-out; grid-template-columns: 1fr 1fr; padding: 16px 20px; border: 1px solid var(--line); border-radius: 12px; background: #fff; margin-bottom: 12px; }
  .forms-table td { border: 0; padding: 7px 0; min-width: 0; }
  .forms-table td::before { content: attr(data-label); display: block; font-size: .6875rem; color: var(--muted); margin-bottom: 4px; }
  .forms-table .plan-cell { grid-column: 1 / -1; padding: 0 0 12px; border-bottom: 1px solid var(--line); margin-bottom: 8px; }
  .plan-title { font-size: 1rem; }
  .forms-table .open-cell { grid-column: 1 / -1; text-align: right; padding: 0; } .open-cell::before { display: none; }
  .forms-table tbody tr:hover { border-color: var(--control-line); }
  .forms-table tbody tr:hover td { background: transparent; }
}
</style>
