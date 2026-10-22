<template>
  <main class="workspace" id="main-content" tabindex="-1" :aria-busy="busy">
    <Transition name="reveal"><p v-if="error" role="alert" class="error">{{ error }}</p></Transition>
    <div v-if="busy && !snapshot" role="status" class="loading"><p class="muted">Loading your plan…</p><div class="skeleton tall" aria-hidden="true"></div><div class="skeleton" aria-hidden="true"></div><div class="skeleton" aria-hidden="true"></div></div>
    <FormParticipantView v-if="snapshot && plan && memberCollecting" guided :round-id="roundId" :snapshot="snapshot" :title="plan.title" :description="plan.description" @refresh="refresh" />
    <template v-else-if="snapshot && plan">
      <header class="round-header page-heading">
        <div>
          <div class="round-meta"><Transition name="swap" mode="out-in"><span :key="displayState" :class="['badge', displayState.toLowerCase()]">{{ stateLabel(displayState) }}</span></Transition><span>{{ organiser ? 'You’re organising' : 'You’re a member' }}</span><span aria-hidden="true">·</span><span>Costs in {{ snapshot.currency }}</span><template v-if="roundList.length > 1"><span aria-hidden="true">·</span><span>Round {{ currentRoundNumber }} of {{ roundList.length }}</span></template><button v-if="!historical && snapshot.previous_round_id" type="button" class="btn-quiet btn-small round-switch" @click="emit('open-round', snapshot.previous_round_id)">View earlier round</button></div>
          <h1>{{ plan.title }}</h1>
          <p v-if="snapshot.decision_question && snapshot.decision_question !== plan.title" class="decision-question">{{ snapshot.decision_question }}</p>
          <p v-if="plan.description" class="plan-description">{{ plan.description }}</p>
        </div>
        <button :disabled="busy" @click="refresh" :class="['refresh', { spinning: busy }]"><UiIcon name="refresh" />{{ busy ? 'Refreshing…' : 'Refresh status' }}</button>
      </header>
      <ol class="round-progress" aria-label="Decision progress" :style="{ '--phase': phase }">
        <li v-for="(label, index) in ['Collect responses', 'Review options', 'Confirm choice']" :key="label" :class="{ current: index === phase, complete: index < phase }" :aria-current="index === phase ? 'step' : undefined">
          <span class="phase-dot"><Transition name="swap" mode="out-in"><UiIcon v-if="index < phase" name="check" /><span v-else>{{ index + 1 }}</span></Transition></span><span>{{ label }}</span>
        </li>
      </ol>

      <Transition name="reveal" mode="out-in">
        <section class="panel organiser-panel" v-if="organiser && !historical && ['COLLECTING','REVIEWING'].includes(plan.state)" :key="plan.state" aria-labelledby="organiser-heading">
          <div class="panel-heading"><div><h2 id="organiser-heading">Organiser controls</h2><p>{{ plan.state === 'COLLECTING' ? 'Share the invitation, then close collection once every member has submitted.' : 'Collection is closed. Calculate the recommendation to compare eligible options.' }}</p></div></div>
          <div v-if="plan.state === 'COLLECTING'" class="collect-progress">
            <template v-if="readiness">
              <div class="collect-figure"><strong>{{ readiness.submitted }}</strong><span>of {{ readiness.members }} {{ readiness.members === 1 ? 'member has' : 'members have' }} submitted</span></div>
              <span class="meter" aria-hidden="true"><span :style="{ '--value': readiness.members ? readiness.submitted / readiness.members : 0 }"></span></span>
              <p class="helper-text">Closing collection freezes the roster and submitted responses.</p>
            </template>
            <p v-else-if="progressError" class="helper-text">{{ progressError }}</p>
          </div>
          <div class="actions">
            <button class="btn-primary" v-if="plan.state === 'COLLECTING' && !shareUrl" :disabled="busy" @click="makeInvite"><UiIcon name="people" />Create invitation link</button>
            <button type="button" v-if="plan.state === 'COLLECTING' && ownIncomplete" @click="scrollToOwnResponse">Answer your response</button>
            <button v-if="plan.state === 'COLLECTING'" :disabled="busy || !readiness?.can_close" @click="close">Close collection</button>
            <button class="btn-primary" v-if="plan.state === 'REVIEWING'" :disabled="busy || run?.status === 'pending'" @click="recommend">{{ calculating || run?.status === 'pending' ? 'Calculating…' : run?.status === 'failed' ? 'Retry recommendation' : run ? 'Recalculate' : 'Calculate recommendation' }}<UiIcon v-if="!calculating && run?.status !== 'pending'" name="arrow" /></button>
          </div>
          <div v-if="plan.state === 'COLLECTING' && readiness && !readiness.can_close" class="callout warning">
            <p>Collection stays open until every member has submitted a complete, current response.</p>
            <ul class="incomplete-list"><li v-for="(member,index) in readiness.members_status.filter(m=>m.status!=='complete')" :key="member.id || index"><span>{{ member.name }}<template v-if="member.user_id === auth.userID"> (you)</template>: {{ member.status === 'stale' ? 'Needs to review the current form' : 'Awaiting complete submission' }}</span><button v-if="member.id && member.role !== 'ORGANISER' && member.user_id !== auth.userID" type="button" class="btn-quiet btn-danger btn-small" :disabled="busy" @click="removeRosterMember(member)">Remove</button></li></ul>
          </div>
          <Transition name="reveal">
            <div v-if="shareUrl && plan.state === 'COLLECTING'" class="invitation-field">
              <label for="invite-link">Invitation link</label>
              <div class="invite-row"><input id="invite-link" readonly :value="shareUrl" @focus="($event.target as HTMLInputElement).select()" /><button :class="{ 'btn-primary': !copied }" @click="copyInvite"><Transition name="swap" mode="out-in"><span :key="String(copied)" class="copy-label"><UiIcon v-if="copied" name="check" />{{ copied ? 'Copied' : 'Copy invitation' }}</span></Transition></button></div>
              <p class="helper-text">Anyone with this link can join and respond. Share it with the people involved in this decision.</p>
            </div>
          </Transition>
        </section>
      </Transition>

      <Transition name="reveal"><p v-if="!organiser && plan.state === 'REVIEWING' && !run" class="callout waiting">Collection has closed. The organiser is reviewing the options. Refresh status to check for the result.</p></Transition>
      <p v-if="backgroundError" role="status" class="helper-text">{{ backgroundError }} <button @click="refresh">Retry status</button></p>
      <section v-if="organiser && !historical && ['REVIEWING','CONFIRMED'].includes(plan.state)" class="panel">
        <h2>Need to change the decision?</h2><p>Revise the options, facts or questions in a new round. This round and any confirmed choice remain in the history. Members review their answers again.</p>
        <button :disabled="busy" @click="reopen">Revise in a new round</button>
      </section>
      <div v-if="historical" class="callout historical-callout"><p>You’re viewing an earlier round. Its result is preserved; RSVPs for it are read-only.</p><button v-if="latestRoundId && latestRoundId !== roundId" type="button" class="btn-small" @click="openLatestRound">Open latest round<UiIcon name="arrow" /></button></div>

      <section class="options-section" aria-labelledby="options-heading">
        <h2 id="options-heading">Options being considered <span class="muted">{{ snapshot.options.length }}</span></h2>
        <OptionCards :options="snapshot.options" :currency="snapshot.currency" :round-id="roundId" :chosen="selection?.candidate_id" compact />
      </section>

      <div v-if="plan.state === 'COLLECTING' && !historical" ref="ownResponseBox">
        <FormParticipantView :round-id="roundId" :snapshot="snapshot" @saved="updateProgress" />
      </div>

      <Transition name="reveal">
        <section class="recommendation-section" v-if="run" aria-labelledby="recommendation-heading">
          <div class="panel-heading"><div><h2 id="recommendation-heading">Group recommendation</h2><p>Options ranked against the group’s confirmed responses.</p></div><span :class="['badge', run.status.toLowerCase()]">{{ stateLabel(run.status) }}</span></div>
          <div v-if="run.status === 'pending'" class="pending" role="status"><span class="pulse" aria-hidden="true"></span>Interpreting responses, checking any missing evidence and calculating the recommendation. You can return later; progress is saved.</div>
          <p v-if="run.recommendation_view.next_action && nextAction" class="callout warning">{{ nextAction }}</p>
          <ul v-if="run.issues.length" class="issue-list"><li v-for="(issue,index) in run.issues" :key="index">{{ stateLabel(issue.code) }}</li></ul>
          <details v-if="run.supplemented_facts?.length" class="supplemented-facts"><summary>Evidence added during calculation</summary>
            <p class="helper-text">These sourced details supplemented the published options for this result. They are saved with the calculation.</p>
            <div v-for="fact in run.supplemented_facts" :key="`${fact.option_id}:${fact.attribute_id}`">
              <p><strong>{{ snapshot.options.find(o=>o.option_id===fact.option_id)?.title }} · {{ factLabel(fact.attribute_id) }}</strong>: {{ Array.isArray(fact.value) ? fact.value.join(', ') : fact.value }} {{ fact.unit || '' }}</p>
              <p class="helper-text">{{ fact.source_text }}</p>
              <ul><li v-for="source in fact.sources" :key="source.url"><a v-if="safeSource(source.url)" :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.title || source.url }}</a></li></ul>
            </div>
          </details>
          <div class="candidate-grid">
            <article v-for="(candidate, index) in candidates" :key="candidate.candidate_id" :class="['candidate-card', 'rise', { recommended: candidate.rank === 1, chosen: selection?.candidate_id === candidate.candidate_id }]" :style="{ '--i': index }">
              <p class="rank">{{ selection?.candidate_id === candidate.candidate_id ? 'Confirmed' : candidate.rank === 1 ? 'Recommended' : `Ranked ${ordinal(candidate.rank)}` }}</p>
              <h3><span class="sr-only">{{ candidate.rank === 1 ? 'Recommended: ' : '' }}</span>{{ candidate.title }}</h3>
              <p v-if="candidate.primary_objective_tie_size > 1" class="tie">Equally suitable with {{ candidate.primary_objective_tie_size - 1 }} other {{ candidate.primary_objective_tie_size === 2 ? 'option' : 'options' }}. Cost, time, then ID set the display order.</p>
              <dl v-if="hasPreferences" class="scores">
                <div><dt>Average group fit</dt><dd>{{ percent(candidate.average_member_score) }}</dd><span class="meter" aria-hidden="true"><span :style="{ '--value': candidate.average_member_score }"></span></span></div>
                <div><dt>Least-satisfied member</dt><dd>{{ percent(candidate.minimum_member_score) }}</dd><span class="meter" aria-hidden="true"><span :style="{ '--value': candidate.minimum_member_score }"></span></span></div>
              </dl>
              <p v-else>Meets the requirements. No scored preferences were collected.</p>
              <dl class="facts" v-if="candidate.estimated_cost_minor != null || candidate.start_at">
                <div v-if="candidate.estimated_cost_minor != null"><dt>Cost per person</dt><dd>{{ money(candidate) }}</dd></div>
                <div v-if="candidate.start_at"><dt>When</dt><dd>{{ new Date(candidate.start_at).toLocaleString() }}<template v-if="candidate.end_at"> – {{ new Date(candidate.end_at).toLocaleString() }}</template></dd></div>
              </dl>
              <p v-if="paretoIds.has(candidate.candidate_id)" class="tradeoff">Trade-off: {{ tradeoffs(candidate.candidate_id) }}</p>
              <button :class="{ 'btn-primary': candidate.rank === 1 }" v-if="organiser && !selection && plan.state === 'REVIEWING'" :disabled="busy" @click="confirm(candidate)">Confirm {{ candidate.title }}<UiIcon name="check" /></button>
            </article>
          </div>
          <div v-if="run.recommendation_view.unavailable_candidates.length" class="unavailable">
            <h3>Ruled out</h3>
            <ul><li v-for="candidate in run.recommendation_view.unavailable_candidates" :key="candidate.candidate_id"><span>{{ candidate.title }}</span><span class="muted">{{ unavailableReason(candidate) }}</span></li></ul>
          </div>
        </section>
      </Transition>

      <Transition name="settle">
        <section v-if="selection" class="panel selection-panel" aria-labelledby="selection-heading">
          <div class="selection-head">
            <span class="seal" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m6 12.5 4 4L18 8" /></svg></span>
            <div><h2 id="selection-heading">Confirmed selection</h2><p class="selected-title">{{ selectedTitle }}</p></div>
          </div>
          <p v-if="selectedSummary" class="selected-summary">{{ selectedSummary }}</p>
          <p class="muted">The choice is confirmed. Let your group know whether you’ll be joining.</p>
          <div v-if="rsvpSummary && rsvpSummary.total > 0" class="rsvp-summary" aria-label="Group attendance">
            <span><strong>{{ rsvpSummary.going }}</strong> going</span>
            <span aria-hidden="true">·</span>
            <span><strong>{{ rsvpSummary.maybe }}</strong> maybe</span>
            <span aria-hidden="true">·</span>
            <span><strong>{{ rsvpSummary.declined }}</strong> not joining</span>
          </div>
          <p v-if="organiser && !historical && rsvpSummary && rsvpSummary.declined > 0" class="callout warning rsvp-decline-note">
            {{ rsvpSummary.declined === 1 ? '1 member can’t join' : `${rsvpSummary.declined} members can’t join` }} this confirmed choice. Revise in a new round above if the group needs to choose another option.
          </p>
          <fieldset class="rsvp" :disabled="busy || historical">
            <legend>Your RSVP</legend>
            <div class="choice-list rsvp-options">
              <label v-for="o in rsvpOptions" :key="o.value" class="choice-option"><input type="radio" name="rsvp" :value="o.value" v-model="rsvpStatus" />{{ o.label }}</label>
            </div>
            <div class="rsvp-actions"><button class="btn-primary" :disabled="busy || !rsvpStatus || rsvpStatus === savedRsvp" @click="saveRsvp">{{ savedRsvp ? 'Update RSVP' : 'Save RSVP' }}</button>
              <button type="button" @click="downloadCalendar"><UiIcon name="document" />Calendar (.ics)</button>
              <Transition name="reveal"><p v-if="notice" role="status" class="saved-note"><UiIcon name="check" />{{ notice }}</p></Transition></div>
          </fieldset>
          <p class="helper-text">Selection version {{ selection.selection_version }}</p>
        </section>
      </Transition>
    </template>
  </main>
</template>
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import UiIcon from './UiIcon.vue';
import FormParticipantView from './FormParticipantView.vue';
import OptionCards from './OptionCards.vue';
import { apiService, ApiError, request } from '@/services/api';
import { checkpointKey, readCheckpoint, writeCheckpoint } from '@/services/checkpoints';
import { operationId } from '@/services/ids';
import { factLabel } from '@/services/facts';
import { useAuthStore } from '@/stores/auth';
import type { Snapshot, PlanRow, Round, Run, Selection, Candidate, ReadinessMember, RsvpSummary } from '@/types/form';
const props = defineProps<{ roundId: string; inviteToken?: string }>();
const emit=defineEmits<{(event:'open-round',id:string):void;(event:'open-draft',id:string):void}>();
const auth = useAuthStore(); const snapshot = ref<Snapshot>(); const plan = ref<PlanRow>(); const roundList = ref<Round[]>([]);
const run = ref<Run>(); const selection = ref<Selection>(); const busy = ref(false); const error = ref('');
const inviteCheckpointKey = computed(() => checkpointKey(auth.userID, `invite:${props.roundId}`));
const shareUrl = ref(readCheckpoint<string>(inviteCheckpointKey.value) || ''); const copied = ref(false); const notice = ref(''); const calculating = ref(false);
const readiness = ref<{ submitted: number; members: number; can_close:boolean; members_status:ReadinessMember[] }>(); const progressError = ref('');
const backgroundError=ref('');const historical=ref(false);let pollTimer:ReturnType<typeof setTimeout> | undefined;let polling=false;
const rsvpStatus = ref(''); const savedRsvp = ref(''); const rsvpRevision = ref(0); const rsvpSummary = ref<RsvpSummary>(); let alive = true;
const ownResponseBox = ref<HTMLElement>();
const rsvpOptions = [{ value: 'GOING', label: 'Going' }, { value: 'MAYBE', label: 'Maybe' }, { value: 'DECLINED', label: 'Not joining' }];
const organiser = computed(() => plan.value?.created_by_user_id === auth.userID);
const displayState=computed(()=>historical.value ? selection.value ? 'CONFIRMED':'REVIEWING' : plan.value?.state || '');
// Members answer in a focused, page-by-page flow; organisers keep the full workspace.
const memberCollecting = computed(() => !organiser.value && !historical.value && plan.value?.state === 'COLLECTING');
const hasPreferences = computed(() => snapshot.value?.questions.some(question => question.role === 'soft' || !question.role));
const candidates = computed(() => run.value?.recommendation_view.recommendation ? [run.value.recommendation_view.recommendation, ...run.value.recommendation_view.alternatives] : []);
const paretoIds = computed(() => new Set(run.value?.recommendation_view.pareto_alternatives.map(row => row.candidate_id)));
const selectedOption = computed(() => snapshot.value?.options.find(row => row.option_id === selection.value?.candidate_id));
const selectedTitle = computed(() => candidates.value.find(row => row.candidate_id === selection.value?.candidate_id)?.title || selectedOption.value?.title || 'Selection confirmed');
const selectedSummary = computed(() => selectedOption.value?.brief?.summary || selectedOption.value?.description || '');
const ownIncomplete = computed(() => !!readiness.value?.members_status.some(m => m.user_id === auth.userID && m.status !== 'complete'));
const currentRoundNumber = computed(() => roundList.value.find(r => r.id === props.roundId)?.round_number || 1);
const latestRoundId = computed(() => [...roundList.value].sort((a, b) => b.round_number - a.round_number)[0]?.id || '');
const actionMessages: Record<string,string> = {
  OPTION_FACTS_REQUIRED: 'Some option facts remain unresolved after the evidence check. The organiser can correct them or try fresh research by revising in a new round.',
  RESPONSES_OR_CONFIRMATIONS_REQUIRED: 'Responses or requirement confirmations are incomplete. Review the round before requesting another calculation.',
  REVISE_OPTIONS_OR_REQUIREMENTS: 'No option meets the group requirements. Revise the choices or requirements in a new round.',
  RECOMMENDATION_IN_PROGRESS: '', DECISION_SETUP_REVIEW_REQUIRED: 'The organiser needs to review the decision setup.', RECOMMENDATION_RETRY_REQUIRED: 'The calculation failed. The organiser can retry.',
};
const nextAction = computed(() => actionMessages[run.value?.recommendation_view.next_action || ''] ?? '');
function stateLabel(value: string) { return value.toLowerCase().replaceAll('_', ' ').replace(/^./, c => c.toUpperCase()); }
function safeSource(value:string){try{return new URL(value).protocol==='https:';}catch{return false;}}
function unavailableLabel(status: string) { return ({ INFEASIBLE: 'Doesn’t meet the group’s requirements', UNRESOLVED: 'Needs verified option details' } as Record<string,string>)[status.toUpperCase()] || stateLabel(status); }
function unavailableReason(candidate: { candidate_id: string; status: string }) {
  if (candidate.status.toUpperCase() === 'UNRESOLVED') {
    const missing = (run.value?.fact_requests || []).filter(f => f.option_id === candidate.candidate_id).map(f => factLabel(f.attribute_id));
    if (missing.length) return `Needs verified details: ${missing.join(', ')}`;
  }
  return unavailableLabel(candidate.status);
}
function scrollToOwnResponse() { ownResponseBox.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
function openLatestRound() {
  if (plan.value?.state === 'DRAFT' && organiser.value && snapshot.value) emit('open-draft', snapshot.value.plan_id);
  else if (latestRoundId.value) emit('open-round', latestRoundId.value);
}
function ordinal(n: number) { const s = ['th','st','nd','rd'], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]!); }
const phase = computed(() => selection.value ? 2 : plan.value?.state === 'REVIEWING' ? 1 : plan.value?.state === 'CONFIRMED' ? 2 : 0);
function percent(value: number) { return `${Math.round(value*100)}%`; }
function money(row: Candidate) { return new Intl.NumberFormat(undefined,{style:'currency',currency:row.currency || snapshot.value!.currency}).format(row.estimated_cost_minor! / 10 ** (row.currency_minor_digits ?? snapshot.value!.currency_minor_digits)); }
function tradeoffs(id: string) { const labels: Record<string,string> = { HIGHER_MINIMUM_SATISFACTION:'higher minimum fit', LOWER_MINIMUM_SATISFACTION:'lower minimum fit', HIGHER_AVERAGE_SATISFACTION:'higher average fit', LOWER_AVERAGE_SATISFACTION:'lower average fit', EQUIVALENT_GROUP_METRICS:'similar group metrics' }; return run.value?.recommendation_view.pareto_alternatives.find(row=>row.candidate_id===id)?.tradeoffs?.map(code=>labels[code] || code).join(', '); }
async function optional<T>(get: () => Promise<T>) { try { return await get(); } catch(e) { if (e instanceof ApiError && e.status === 404) return undefined; throw e; } }
async function act(fn: () => Promise<void>) { if (busy.value) return; busy.value = true; error.value = ''; try { await fn(); } catch(e) { error.value = e instanceof Error ? e.message : 'Request failed'; } finally { busy.value = false; } }
async function load() {
  snapshot.value = await apiService.snapshot(props.roundId);
  plan.value = await apiService.plan(snapshot.value.plan_id);
  const rounds=await apiService.rounds(snapshot.value.plan_id);
  roundList.value = [...rounds.data].sort((a,b)=>a.round_number-b.round_number);
  historical.value=[...rounds.data].sort((a,b)=>b.round_number-a.round_number)[0]?.id!==props.roundId;
  run.value = await optional(() => apiService.result(props.roundId));
  selection.value = await optional(() => apiService.selection(props.roundId));
  if (selection.value) { const own = await apiService.rsvp(props.roundId); rsvpRevision.value = own.revision; rsvpStatus.value = savedRsvp.value = own.status || ''; rsvpSummary.value = own.summary; }
  await updateProgress();
}
async function refresh() { await act(load); }
async function updateProgress() {
  if (!organiser.value || plan.value?.state !== 'COLLECTING') { readiness.value = undefined; return; }
  try {
    const row = await request<{ member_count:number; complete_count:number; can_close:boolean; members:ReadinessMember[]; progress: { submittedCount?:number } }>(`/api/planning/v1/rounds/${props.roundId}/readiness`);
    readiness.value = { submitted: row.complete_count, members: row.member_count, can_close:row.can_close, members_status:row.members }; progressError.value = '';
  } catch { readiness.value = undefined; progressError.value = 'Progress could not be loaded. Refresh before closing.'; }
}
async function removeRosterMember(member: ReadinessMember) {
  if (!member.id || !window.confirm(`Remove ${member.name} from this plan?`)) return;
  await act(async () => { await apiService.removeMember(member.id!); await updateProgress(); });
}
async function makeInvite() { await act(async () => { const invite=await apiService.invite(snapshot.value!.plan_id,auth.userID); shareUrl.value=`${location.origin}/#${new URLSearchParams({round:props.roundId,invite:invite.token})}`; writeCheckpoint(inviteCheckpointKey.value, shareUrl.value); }); }
async function copyInvite() { await act(async () => { await navigator.clipboard.writeText(shareUrl.value); copied.value=true; setTimeout(() => { copied.value = false; }, 2400); }); }
async function close() {
  const count = readiness.value ? ` ${readiness.value.submitted} of ${readiness.value.members} members have submitted.` : '';
  if (!window.confirm(`Close collection?${count} This freezes the roster and responses; members can’t edit afterwards.`)) return;
  await act(async () => { await apiService.close(props.roundId); await load(); });
}
async function recommend() { calculating.value=true;await act(async()=>{run.value=await apiService.recommend(props.roundId);});calculating.value=false;schedulePoll(); }
async function reopen(){
  if(!window.confirm('Create a new editable round? Existing results and RSVPs stay attached to this round.'))return;
  await act(async()=>{const key=`reopen:${props.roundId}`;const operation=sessionStorage.getItem(key)||operationId();sessionStorage.setItem(key,operation);
    await apiService.reopen(props.roundId,operation);emit('open-draft',snapshot.value!.plan_id);});
}
function schedulePoll(){clearTimeout(pollTimer);if(alive && !selection.value)pollTimer=setTimeout(pollStatus,run.value?.status==='pending'?1000:5000);}
async function pollStatus(){
  if(!alive)return;
  if(document.hidden || busy.value || polling){schedulePoll();return;}
  polling=true;
  try{
    const current=await apiService.plan(snapshot.value!.plan_id);if(!alive)return;const previousState=plan.value?.state;plan.value=current;
    if(current.state!==previousState){const rounds=await apiService.rounds(snapshot.value!.plan_id);if(alive){roundList.value=[...rounds.data].sort((a,b)=>a.round_number-b.round_number);historical.value=[...rounds.data].sort((a,b)=>b.round_number-a.round_number)[0]?.id!==props.roundId;}}
    if(current.state==='COLLECTING' && !historical.value){await updateProgress();backgroundError.value='';return;}
    const latestRun=await optional(()=>apiService.result(props.roundId));if(!alive)return;run.value=latestRun;
    const chosen=await optional(()=>apiService.selection(props.roundId));if(!alive)return;
    if(chosen){const first=!selection.value;selection.value=chosen;const own=await apiService.rsvp(props.roundId);if(!alive)return;rsvpSummary.value=own.summary;if(first){rsvpRevision.value=own.revision;rsvpStatus.value=savedRsvp.value=own.status || '';}}
    await updateProgress();backgroundError.value='';
  }catch{if(alive)backgroundError.value='Status could not be updated. Your saved response and background calculation are retained; updates will retry.';}
  finally{polling=false;schedulePoll();}
}
function visible(){if(!document.hidden && alive && snapshot.value){clearTimeout(pollTimer);void pollStatus();}}
async function confirm(candidate: Candidate) {
  if (!window.confirm(`Confirm “${candidate.title}” as the group’s choice? Members will be asked to RSVP.`)) return;
  await act(async () => {
    const key=`confirmation:${props.roundId}:${run.value!.run_id}:${candidate.candidate_id}`;
    const operation=sessionStorage.getItem(key)||operationId();sessionStorage.setItem(key,operation);
    selection.value=await apiService.confirm(props.roundId,run.value!.run_id,candidate.candidate_id,operation); await load();
  });
}
async function saveRsvp() { notice.value = ''; await act(async () => { await apiService.saveRsvp(props.roundId,selection.value!.selection_version,rsvpRevision.value,rsvpStatus.value); const own=await apiService.rsvp(props.roundId);rsvpRevision.value=own.revision;savedRsvp.value=own.status || rsvpStatus.value;rsvpSummary.value=own.summary;notice.value='RSVP saved.'; }); }
function downloadCalendar() {
  if (!plan.value || !selection.value) return;
  const candidate = candidates.value.find(c => c.candidate_id === selection.value?.candidate_id);
  const stamp = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
  const now = new Date();
  const start = candidate?.start_at ? new Date(candidate.start_at) : new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 19, 0, 0);
  const end = candidate?.end_at ? new Date(candidate.end_at) : new Date(start.getTime() + 7200000);
  const clean = (v?: string) => (v || '').replace(/\r?\n/g, '\\n').replace(/[,;]/g, '\\$&');
  const lines = [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//What2Do//Confirmed Plan//EN', 'BEGIN:VEVENT',
    `UID:${props.roundId}-v${selection.value.selection_version}@what2do`,
    `DTSTAMP:${stamp(now)}`, `DTSTART:${stamp(start)}`, `DTEND:${stamp(end)}`,
    `SUMMARY:${clean(`${plan.value.title}: ${selectedTitle.value}`)}`,
    ...(selectedSummary.value ? [`DESCRIPTION:${clean(selectedSummary.value)}`] : []),
    ...(selectedOption.value?.brief?.where ? [`LOCATION:${clean(selectedOption.value.brief.where)}`] : []),
    'END:VEVENT', 'END:VCALENDAR',
  ];
  const blob = new Blob([lines.join('\r\n')], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = `${plan.value.title.toLowerCase().replace(/[^a-z0-9]+/g, '-') || 'plan'}.ics`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
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
}); if(!alive)return;if(snapshot.value)schedulePoll();document.addEventListener('visibilitychange',visible); });
onUnmounted(()=>{alive=false;clearTimeout(pollTimer);document.removeEventListener('visibilitychange',visible);});
</script>
<style scoped>
.workspace { max-width: 1200px; margin: auto; padding: 48px 32px 80px; }
.loading .tall { height: 120px; }
.round-header h1 { overflow-wrap: anywhere; }
.round-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; color: var(--muted); font-size: .75rem; margin-bottom: 16px; }
.decision-question { font-size: 1.125rem; font-weight: 600; color: var(--ink); margin: -4px 0 8px; overflow-wrap: anywhere; }
.plan-description { font-size: .875rem; white-space: pre-wrap; overflow-wrap: anywhere; }
.refresh.spinning .ui-icon { animation: spin 900ms linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.round-progress { position: relative; display: flex; list-style: none; padding: 0 0 28px; margin: 28px 0; border-bottom: 1px solid var(--line); gap: 40px; }
.round-progress li { display: flex; align-items: center; gap: 10px; color: var(--muted); font-size: .8125rem; transition: color var(--base) ease-out; }
.phase-dot { border: 1px solid #aab9ae; width: 28px; height: 28px; display: grid; place-items: center; border-radius: 50%; font-size: .75rem; flex-shrink: 0; transition: background-color var(--base) ease-out, border-color var(--base) ease-out, color var(--base) ease-out; }
.round-progress .current { color: var(--accent); font-weight: 650; } .current .phase-dot { background: var(--accent); color: #fff; border-color: var(--accent); box-shadow: 0 0 0 4px var(--accent-soft); }
.complete .phase-dot { color: var(--accent); background: var(--accent-soft); border-color: transparent; } .phase-dot .ui-icon { width: 15px; height: 15px; }
.round-progress::after { content: ''; position: absolute; left: 0; bottom: -1px; height: 2px; width: calc((var(--phase) + 1) / 3 * 100%); background: var(--accent); transition: width var(--slow) var(--ease-out); }

.collect-progress { margin: 4px 0 24px; max-width: 460px; }
.collect-figure { display: flex; align-items: baseline; gap: 10px; margin-bottom: 10px; }
.collect-figure strong { font-size: 2rem; line-height: 1; font-weight: 650; letter-spacing: -.03em; font-variant-numeric: tabular-nums; }
.collect-figure span { color: var(--muted); font-size: .875rem; }
.invitation-field { margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--line); }
.invitation-field > label { margin: 0 0 7px; }
.invite-row { display: flex; gap: 10px; max-width: 720px; }
.invite-row input { font-size: .8125rem; min-height: 44px; }
.invite-row button { flex-shrink: 0; min-width: 160px; }
.copy-label { display: inline-flex; align-items: center; gap: 8px; }

.waiting { margin: 24px 0; }
.options-section { margin: 32px 0; }
.options-section h2 { font-size: 1rem; display: flex; gap: 8px; align-items: baseline; }
.options-section h2 .muted { font-size: .8125rem; font-weight: 500; }

.recommendation-section { margin: 40px 0; }
.pending { display: flex; align-items: center; gap: 12px; padding: 16px 18px; margin-bottom: 20px; border-radius: 8px; background: #fff; border: 1px solid var(--line); color: var(--muted); font-size: .875rem; }
.pulse { width: 10px; height: 10px; border-radius: 50%; background: #c58a2e; animation: pulse 1.2s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: .35; transform: scale(.8); } }
.issue-list { font-size: .875rem; color: var(--muted); }
.candidate-grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(min(100%,300px),1fr)); gap: 16px; }
.supplemented-facts { overflow-wrap: anywhere; margin: 20px 0; }
.candidate-card { display: flex; flex-direction: column; padding: 24px; border: 1px solid var(--line); background: #fff; border-radius: 12px; overflow-wrap: anywhere; }
.candidate-card.recommended { background: #f1f7f2; border-color: #a9c5b2; box-shadow: inset 0 3px 0 var(--accent); }
.candidate-card.chosen { border-color: var(--accent); }
.rank { font-size: .75rem; font-weight: 650; color: var(--muted); margin-bottom: 4px; }
.recommended .rank { color: var(--accent); }
.candidate-card h3 { font-size: 1.25rem; margin-bottom: 12px; }
.candidate-card > p { font-size: .875rem; color: #3a5546; }
.tie { color: var(--muted) !important; }
.scores { display: grid; gap: 14px; margin: 8px 0 20px; }
.scores > div { display: grid; grid-template-columns: 1fr auto; align-items: baseline; gap: 4px 12px; }
.scores dt { font-size: .8125rem; color: #3a5546; }
.scores dd { margin: 0; font-size: 1.25rem; font-weight: 650; font-variant-numeric: tabular-nums; letter-spacing: -.02em; }
.scores .meter { grid-column: 1 / -1; }
.facts { display: grid; gap: 8px; margin: 0 0 16px; padding-top: 14px; border-top: 1px solid var(--line); font-size: .875rem; }
.facts > div { display: flex; justify-content: space-between; gap: 12px; }
.facts dt { color: var(--muted); }
.facts dd { margin: 0; font-weight: 600; font-variant-numeric: tabular-nums; text-align: right; }
.tradeoff { font-size: .8125rem !important; color: var(--muted) !important; }
.candidate-card > button { margin-top: auto; align-self: flex-start; }
.unavailable { margin-top: 24px; }
.unavailable h3 { font-size: .875rem; color: var(--muted); margin-bottom: 8px; }
.unavailable ul { list-style: none; padding: 0; margin: 0; border: 1px solid var(--line); border-radius: 10px; background: #fff; }
.unavailable li { display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; padding: 12px 16px; font-size: .875rem; }
.unavailable li + li { border-top: 1px solid var(--line); }
.unavailable li > span:first-child { text-decoration: line-through; text-decoration-color: #9aa79f; }

.round-switch { padding: 2px 8px; min-height: 28px; font-size: .75rem; color: var(--accent); }
.historical-callout { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.historical-callout p { margin: 0; }
.incomplete-list li { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.selected-summary { font-size: .875rem; color: var(--ink); margin: 0 0 10px; }
.rsvp-summary { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 8px 14px; margin-bottom: 12px; border-radius: 7px; background: #f3f6f2; border: 1px solid var(--line); font-size: .8125rem; color: var(--ink); font-variant-numeric: tabular-nums; }
.rsvp-decline-note { margin: 0 0 16px; }
.selection-panel { border-color: #a9c5b2; }
.selection-head { display: flex; align-items: center; gap: 18px; margin-bottom: 12px; }
.selection-head h2 { font-size: .875rem; color: var(--accent); margin-bottom: 2px; letter-spacing: 0; }
.seal { display: grid; place-items: center; width: 48px; height: 48px; border-radius: 50%; background: var(--accent); flex-shrink: 0; }
.seal svg { width: 26px; height: 26px; fill: none; stroke: #fff; stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; stroke-dasharray: 20; stroke-dashoffset: 0; animation: draw 520ms 180ms var(--ease-out) both; }
@keyframes draw { from { stroke-dashoffset: 20; } }
.selected-title { font-size: 1.625rem; font-weight: 650; letter-spacing: -.02em; line-height: 1.25; margin: 0; overflow-wrap: anywhere; }
.rsvp { margin: 20px 0 12px; }
.rsvp-options { grid-template-columns: repeat(3, minmax(0, 180px)); }
.rsvp-actions { display: flex; align-items: center; gap: 16px; margin-top: 16px; flex-wrap: wrap; }
.saved-note { display: flex; align-items: center; gap: 6px; margin: 0; }
.saved-note .ui-icon { width: 16px; height: 16px; }
.settle-enter-active { transition: opacity var(--slow) var(--ease-out), transform var(--slow) var(--ease-out); }
.settle-enter-from { opacity: 0; transform: translateY(12px) scale(.99); }

@media(max-width:700px) {
  .workspace { padding: 32px 20px 48px; }
  .round-progress { gap: 12px; justify-content: space-between; } .round-progress li { flex-direction: column; align-items: flex-start; font-size: .6875rem; flex: 1; }
  .round-header > button { align-self: flex-start; } .candidate-card { padding: 20px; }
  .invite-row { flex-direction: column; } .invite-row button { width: 100%; }
  .rsvp-options { grid-template-columns: minmax(0, 1fr); }
  .rsvp-actions button { width: 100%; }
  .selected-title { font-size: 1.375rem; }
}
</style>
