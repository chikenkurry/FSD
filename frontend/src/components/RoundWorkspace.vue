<template>
  <main class="workspace">
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="busy" role="status">Working…</p>
    <template v-if="snapshot && plan">
      <header class="round-header"><div><h1>{{ plan.title }}</h1><p>{{ plan.state }} · {{ snapshot.currency }} · {{ snapshot.execution_mode }}</p></div><button :disabled="busy" @click="refresh">Refresh status</button></header>
      <section class="panel" v-if="organiser && ['COLLECTING','REVIEWING'].includes(plan.state)">
        <h2>Organiser controls</h2>
        <p v-if="progress">{{ progress }}</p>
        <div class="actions">
          <button v-if="plan.state === 'COLLECTING'" :disabled="busy" @click="makeInvite">Create invitation link</button>
          <button v-if="plan.state === 'COLLECTING'" :disabled="busy" @click="close">Close collection</button>
          <button v-if="plan.state === 'REVIEWING'" :disabled="busy" @click="recommend">{{ run?.status === 'failed' ? 'Retry recommendation' : 'Calculate recommendation' }}</button>
        </div>
        <label v-if="shareUrl && plan.state === 'COLLECTING'">Invitation link<input readonly :value="shareUrl" @focus="($event.target as HTMLInputElement).select()" /></label>
        <button v-if="shareUrl && plan.state === 'COLLECTING'" @click="copyInvite">{{ copied ? 'Copied' : 'Copy invitation' }}</button>
      </section>
      <section class="panel"><h2>Options</h2><ul><li v-for="option in snapshot.options" :key="option.option_id">{{ option.title }}</li></ul></section>
      <FormParticipantView v-if="plan.state === 'COLLECTING'" :round-id="roundId" :snapshot="snapshot" @saved="updateProgress" />
      <section class="panel" v-if="run">
        <h2>Group recommendation</h2><p>Status: {{ run.status }}</p>
        <p v-if="run.status === 'pending'">Your recommendation is still running. Refresh status to check it.</p>
        <p v-if="run.recommendation_view.next_action">{{ nextAction }}</p>
        <ul v-if="run.issues.length"><li v-for="(issue,index) in run.issues" :key="index">{{ issue.code }}</li></ul>
        <div class="candidate-grid">
          <article v-for="candidate in candidates" :key="candidate.candidate_id" class="candidate-card">
            <h3>{{ candidate.rank === 1 ? 'Recommended: ' : '' }}{{ candidate.title }}</h3>
            <p v-if="candidate.primary_objective_tie_size > 1">Equally suitable with {{ candidate.primary_objective_tie_size - 1 }} other option(s). Cost, time, then ID determine display order.</p>
            <dl v-if="hasPreferences"><dt>Least-satisfied member fit</dt><dd>{{ percent(candidate.minimum_member_score) }}</dd><dt>Average group fit</dt><dd>{{ percent(candidate.average_member_score) }}</dd></dl>
            <p v-else>Meets the requirements. No scored preferences were collected.</p>
            <p v-if="candidate.estimated_cost_minor != null">Cost: {{ money(candidate) }}</p>
            <p v-if="candidate.start_at">{{ new Date(candidate.start_at).toLocaleString() }} – {{ candidate.end_at ? new Date(candidate.end_at).toLocaleString() : '' }}</p>
            <p v-if="paretoIds.has(candidate.candidate_id)">Other strong trade-off: {{ tradeoffs(candidate.candidate_id) }}</p>
            <button v-if="organiser && !selection && plan.state === 'REVIEWING'" :disabled="busy" @click="confirm(candidate.candidate_id)">Confirm {{ candidate.title }}</button>
          </article>
        </div>
        <ul v-if="run.recommendation_view.unavailable_candidates.length"><li v-for="candidate in run.recommendation_view.unavailable_candidates" :key="candidate.candidate_id">{{ candidate.title }}: {{ candidate.status }}</li></ul>
      </section>
      <section v-if="selection" class="panel">
        <h2>Confirmed selection</h2><p>{{ selectedTitle }} · version {{ selection.selection_version }}</p>
        <label>Your RSVP<select v-model="rsvpStatus" :disabled="busy"><option value="">Choose…</option><option>GOING</option><option>MAYBE</option><option>DECLINED</option></select></label>
        <button :disabled="busy || !rsvpStatus" @click="saveRsvp">Save RSVP</button><p role="status">{{ notice }}</p>
      </section>
    </template>
  </main>
</template>
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import FormParticipantView from './FormParticipantView.vue';
import { apiService, ApiError, request } from '@/services/api';
import { useAuthStore } from '@/stores/auth';
import type { Snapshot, PlanRow, Run, Selection, Candidate } from '@/types/form';
const props = defineProps<{ roundId: string; inviteToken?: string }>();
const auth = useAuthStore(); const snapshot = ref<Snapshot>(); const plan = ref<PlanRow>();
const run = ref<Run>(); const selection = ref<Selection>(); const busy = ref(false); const error = ref('');
const shareUrl = ref(''); const copied = ref(false); const progress = ref(''); const notice = ref('');
const rsvpStatus = ref(''); const rsvpRevision = ref(0); let alive = true;
const organiser = computed(() => plan.value?.created_by_user_id === auth.userID);
const hasPreferences = computed(() => snapshot.value?.questions.some(question => question.role === 'soft' || !question.role));
const candidates = computed(() => run.value?.recommendation_view.recommendation ? [run.value.recommendation_view.recommendation, ...run.value.recommendation_view.alternatives] : []);
const paretoIds = computed(() => new Set(run.value?.recommendation_view.pareto_alternatives.map(row => row.candidate_id)));
const selectedTitle = computed(() => candidates.value.find(row => row.candidate_id === selection.value?.candidate_id)?.title || snapshot.value?.options.find(row => row.option_id === selection.value?.candidate_id)?.title || 'Selection confirmed');
const actionMessages: Record<string,string> = {
  OPTION_FACTS_REQUIRED: 'More confirmed option facts are needed. The organiser must revise the options in a new round.',
  RESPONSES_OR_CONFIRMATIONS_REQUIRED: 'Responses or requirement confirmations are incomplete. Review the round before requesting another calculation.',
  REVISE_OPTIONS_OR_REQUIREMENTS: 'No option meets the group requirements. Revise the choices or requirements in a new round.',
  RECOMMENDATION_IN_PROGRESS: 'The recommendation is running.', DECISION_SETUP_REVIEW_REQUIRED: 'The organiser needs to review the decision setup.', RECOMMENDATION_RETRY_REQUIRED: 'The calculation failed. The organiser can retry.',
};
const nextAction = computed(() => actionMessages[run.value?.recommendation_view.next_action || ''] || '');
function percent(value: number) { return `${Math.round(value*100)}%`; }
function money(row: Candidate) { return new Intl.NumberFormat(undefined,{style:'currency',currency:row.currency || snapshot.value!.currency}).format(row.estimated_cost_minor! / 10 ** (row.currency_minor_digits ?? snapshot.value!.currency_minor_digits)); }
function tradeoffs(id: string) { const labels: Record<string,string> = { HIGHER_MINIMUM_SATISFACTION:'higher minimum fit', LOWER_MINIMUM_SATISFACTION:'lower minimum fit', HIGHER_AVERAGE_SATISFACTION:'higher average fit', LOWER_AVERAGE_SATISFACTION:'lower average fit', EQUIVALENT_GROUP_METRICS:'similar group metrics' }; return run.value?.recommendation_view.pareto_alternatives.find(row=>row.candidate_id===id)?.tradeoffs?.map(code=>labels[code] || code).join(', '); }
async function optional<T>(get: () => Promise<T>) { try { return await get(); } catch(e) { if (e instanceof ApiError && e.status === 404) return undefined; throw e; } }
async function act(fn: () => Promise<void>) { if (busy.value) return; busy.value = true; error.value = ''; try { await fn(); } catch(e) { error.value = e instanceof Error ? e.message : 'Request failed'; } finally { busy.value = false; } }
async function load() {
  snapshot.value = await apiService.snapshot(props.roundId);
  plan.value = await apiService.plan(snapshot.value.plan_id);
  run.value = await optional(() => apiService.result(props.roundId));
  selection.value = await optional(() => apiService.selection(props.roundId));
  if (selection.value) { const own = await apiService.rsvp(props.roundId); rsvpRevision.value = own.revision; rsvpStatus.value = own.status || ''; }
  await updateProgress();
}
async function refresh() { await act(load); }
async function updateProgress() {
  if (!organiser.value || plan.value?.state !== 'COLLECTING') { progress.value=''; return; }
  try {
    const readiness = await request<{ member_count:number; progress: { submittedCount?:number } }>(`/api/planning/v1/rounds/${props.roundId}/readiness`);
    progress.value = `${readiness.progress.submittedCount || 0} submitted / ${readiness.member_count} member(s). Closing freezes incomplete responses too.`;
  } catch { progress.value = 'Progress could not be loaded. Refresh before closing.'; }
}
async function makeInvite() { await act(async () => { const invite=await apiService.invite(snapshot.value!.plan_id,auth.userID); shareUrl.value=`${location.origin}/#${new URLSearchParams({round:props.roundId,invite:invite.token})}`; }); }
async function copyInvite() { await act(async () => { await navigator.clipboard.writeText(shareUrl.value); copied.value=true; }); }
async function close() { if (!window.confirm('Close collection and freeze the current roster and responses? Members cannot edit after closing.')) return; await act(async () => { await apiService.close(props.roundId); await load(); }); }
async function recommend() { await act(async () => { run.value=await apiService.recommend(props.roundId); const until=Date.now()+30000; while(alive && run.value.status==='pending' && Date.now()<until) { await new Promise(resolve=>setTimeout(resolve,500)); if (alive) run.value=await apiService.result(props.roundId); } }); }
async function confirm(candidate: string) { await act(async () => {
  const key=`confirmation:${props.roundId}:${run.value!.run_id}:${candidate}`;
  const operation=sessionStorage.getItem(key)||crypto.randomUUID();sessionStorage.setItem(key,operation);
  selection.value=await apiService.confirm(props.roundId,run.value!.run_id,candidate,operation); await load();
}); }
async function saveRsvp() { await act(async () => { await apiService.saveRsvp(props.roundId,selection.value!.selection_version,rsvpRevision.value,rsvpStatus.value); const own=await apiService.rsvp(props.roundId);rsvpRevision.value=own.revision;notice.value='RSVP saved.'; }); }
onMounted(async () => { await act(async () => {
  if (props.inviteToken) {
    try { await apiService.snapshot(props.roundId); }
    catch (e) {
      if (e instanceof ApiError && (e.status === 403 || e.status === 404)) await apiService.join(props.inviteToken,auth.userID,auth.username);
      else throw e;
    }
  }
  await load();
  if (props.inviteToken) history.replaceState(null, '', `/#${new URLSearchParams({round:props.roundId})}`);
}); });
onUnmounted(()=>{alive=false;});
</script>
<style scoped>
.workspace { max-width: 1100px; margin: auto; padding: clamp(1rem,4vw,2rem); }.round-header,.actions { display:flex; gap:1rem; justify-content:space-between; align-items:center; flex-wrap:wrap; }.panel { background:white; padding:clamp(1rem,3vw,1.5rem); margin:1rem 0; border-radius:8px; }.candidate-grid { display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:1rem; }.candidate-card { padding:1rem;border:1px solid #cbd5e0;border-radius:8px;overflow-wrap:anywhere; }.error { padding:1rem;background:#ffe5e5;color:#8a1515; }button { padding:.7rem;min-height:44px; }dd { margin-left:0;font-weight:600; }h1 { overflow-wrap:anywhere; }@media(max-width:600px) { .actions button { width:100%; }.round-header { align-items:stretch; }.round-header button { width:100%; } }
</style>
