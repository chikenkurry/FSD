<template>
  <main class="workspace" id="main-content" tabindex="-1" :aria-busy="busy">
    <Transition name="reveal"
      ><p v-if="error" role="alert" class="error">{{ error }}</p></Transition
    >
    <div v-if="busy && !snapshot" role="status" class="loading">
      <p class="sr-only">Loading your plan…</p>
      <div class="skeleton title" aria-hidden="true"></div>
      <div class="skeleton tall" aria-hidden="true"></div>
      <div class="skeleton" aria-hidden="true"></div>
    </div>
    <FormParticipantView
      v-if="snapshot && plan && memberCollecting"
      guided
      :round-id="roundId"
      :snapshot="snapshot"
      :title="plan.title"
      :description="plan.description"
      :deadline="deadline"
      @refresh="refresh"
    />
    <template v-else-if="snapshot && plan">
      <header class="round-header page-heading">
        <div>
          <div class="round-meta">
            <Transition name="swap" mode="out-in"
              ><span :key="displayState" :class="['badge', displayState.toLowerCase()]">{{
                stateLabel(displayState)
              }}</span></Transition
            ><span>{{ organiser ? 'You’re organising' : 'You’re a member' }}</span
            ><span aria-hidden="true">·</span><span>Costs in {{ snapshot.currency }}</span
            ><template v-if="roundList.length > 1"
              ><span aria-hidden="true">·</span
              ><span>Round {{ currentRoundNumber }} of {{ roundList.length }}</span></template
            ><template v-if="deadline && plan.state === 'COLLECTING' && !historical"
              ><span aria-hidden="true">·</span
              ><span :class="{ overdue: deadlinePassed }">{{
                deadlinePassed ? 'Deadline passed' : `Answers due ${formatWhen(deadline)}`
              }}</span></template
            ><button
              v-if="!historical && snapshot.previous_round_id"
              type="button"
              class="btn-quiet btn-small round-switch"
              @click="emit('open-round', snapshot.previous_round_id)"
            >
              View earlier round
            </button>
          </div>
          <h1>{{ plan.title }}</h1>
          <p v-if="snapshot.decision_question && snapshot.decision_question !== plan.title" class="decision-question">
            {{ snapshot.decision_question }}
          </p>
          <p v-if="plan.description" class="plan-description">{{ plan.description }}</p>
        </div>
        <button :disabled="busy" @click="refresh" :class="['refresh', { spinning: busy }]">
          <UiIcon name="refresh" />{{ busy ? 'Refreshing…' : 'Refresh status' }}
        </button>
      </header>
      <ol class="round-progress" aria-label="Decision progress" :style="{ '--phase': phase }">
        <li
          v-for="(label, index) in ['Collect responses', 'Review options', 'Confirm choice']"
          :key="label"
          :class="{ current: index === phase, complete: index < phase }"
          :aria-current="index === phase ? 'step' : undefined"
        >
          <span class="phase-dot"
            ><Transition name="swap" mode="out-in"
              ><UiIcon v-if="index < phase" name="check" /><span v-else>{{ index + 1 }}</span></Transition
            ></span
          ><span class="phase-label">{{ label }}</span>
        </li>
      </ol>

      <div :class="['round-body', { 'has-aside': showAside }]">
        <div class="round-main">
          <Transition name="reveal"
            ><p v-if="!organiser && plan.state === 'REVIEWING' && !run" class="callout waiting">
              Collection has closed. The organiser is reviewing the options. Refresh status to check for the result.
            </p></Transition
          >
          <p v-if="backgroundError" role="status" class="helper-text">
            {{ backgroundError }} <button class="btn-small" @click="refresh">Retry status</button>
          </p>
          <div v-if="historical" class="callout historical-callout">
            <p>You’re viewing an earlier round. Its result is preserved; RSVPs for it are read-only.</p>
            <button
              v-if="latestRoundId && latestRoundId !== roundId"
              type="button"
              class="btn-small"
              @click="openLatestRound"
            >
              Open latest round<UiIcon name="arrow" />
            </button>
          </div>

          <Transition name="settle">
            <section v-if="selection" class="selection-panel" aria-labelledby="selection-heading">
              <div class="selection-head">
                <span class="seal" aria-hidden="true"
                  ><svg viewBox="0 0 24 24"><path d="m6 12.5 4 4L18 8" /></svg
                ></span>
                <div>
                  <h2 id="selection-heading">Confirmed selection</h2>
                  <p class="selected-title">{{ selectedTitle }}</p>
                </div>
              </div>
              <p v-if="eventWhen" class="event-when">{{ eventWhen }}</p>
              <p v-if="selectedSummary" class="selected-summary">{{ selectedSummary }}</p>
              <p class="selection-lede">The choice is confirmed. Let your group know whether you’ll be joining.</p>
              <dl v-if="rsvpSummary && rsvpSummary.total > 0" class="rsvp-summary" aria-label="Group attendance">
                <div>
                  <dt>Going</dt>
                  <dd>{{ rsvpSummary.going }}</dd>
                </div>
                <div>
                  <dt>Maybe</dt>
                  <dd>{{ rsvpSummary.maybe }}</dd>
                </div>
                <div>
                  <dt>Not joining</dt>
                  <dd>{{ rsvpSummary.declined }}</dd>
                </div>
              </dl>
              <p
                v-if="organiser && !historical && rsvpSummary && rsvpSummary.declined > 0"
                class="callout warning rsvp-decline-note"
              >
                {{ rsvpSummary.declined === 1 ? '1 member can’t join' : `${rsvpSummary.declined} members can’t join` }}
                this confirmed choice. Revise in a new round if the group needs to choose another option.
              </p>
              <fieldset class="rsvp" :disabled="busy || historical">
                <legend>Your RSVP</legend>
                <div class="choice-list rsvp-options">
                  <label v-for="o in rsvpOptions" :key="o.value" class="choice-option"
                    ><input type="radio" name="rsvp" :value="o.value" v-model="rsvpStatus" />{{ o.label }}</label
                  >
                </div>
                <div class="rsvp-actions">
                  <button
                    class="btn-primary"
                    :disabled="busy || !rsvpStatus || rsvpStatus === savedRsvp"
                    @click="saveRsvp"
                  >
                    {{ savedRsvp ? 'Update RSVP' : 'Save RSVP' }}
                  </button>
                  <button type="button" @click="downloadCalendar"><UiIcon name="document" />Calendar (.ics)</button>
                  <Transition name="reveal"
                    ><p v-if="notice" role="status" class="saved-note">
                      <UiIcon name="check" />{{ notice }}
                    </p></Transition
                  >
                </div>
              </fieldset>
              <p class="helper-text">Selection version {{ selection.selection_version }}</p>
            </section>
          </Transition>

          <section v-if="!candidates.length" class="options-section" aria-labelledby="options-heading">
            <h2 id="options-heading">
              Options being considered <span class="count">{{ snapshot.options.length }}</span>
            </h2>
            <OptionCards
              :options="snapshot.options"
              :currency="snapshot.currency"
              :round-id="roundId"
              :chosen="selection?.candidate_id"
              compact
            />
          </section>

          <div v-if="plan.state === 'COLLECTING' && !historical" ref="ownResponseBox" class="own-response">
            <h2 class="own-heading">Your response</h2>
            <FormParticipantView :round-id="roundId" :snapshot="snapshot" @saved="updateProgress" />
          </div>

          <Transition name="reveal">
            <RecommendationResults
              v-if="run"
              :round-id="roundId"
              :run="run"
              :snapshot="snapshot"
              :candidates="candidates"
              :selection="selection"
              :selected-title="selectedTitle"
              :can-confirm="organiser && !selection && plan.state === 'REVIEWING'"
              :busy="busy"
              :podium-key="podiumKey"
              @confirm="confirm"
            />
          </Transition>
        </div>

        <aside v-if="showAside" class="round-aside">
          <Transition name="reveal" mode="out-in">
            <section
              class="panel organiser-panel"
              v-if="['COLLECTING', 'REVIEWING'].includes(plan.state)"
              :key="plan.state"
              aria-labelledby="organiser-heading"
            >
              <h2 id="organiser-heading">Organiser controls</h2>
              <p class="aside-lede">
                {{
                  plan.state === 'COLLECTING'
                    ? 'Share the invitation, then close collection once every member has submitted.'
                    : 'Collection is closed. Calculate the recommendation to compare eligible options.'
                }}
              </p>
              <div v-if="plan.state === 'COLLECTING'" class="collect-progress">
                <template v-if="readiness">
                  <div class="collect-figure">
                    <strong
                      >{{ readiness.submitted }}<span class="of">/{{ readiness.members }}</span></strong
                    ><span>{{ readiness.members === 1 ? 'member has' : 'members have' }} submitted</span>
                  </div>
                  <span class="meter" aria-hidden="true"
                    ><span
                      :style="{ '--value': readiness.members ? readiness.submitted / readiness.members : 0 }"
                    ></span
                  ></span>
                  <p class="helper-text">Closing collection freezes the roster and submitted responses.</p>
                </template>
                <p v-else-if="progressError" class="helper-text">{{ progressError }}</p>
              </div>
              <div v-if="plan.state === 'COLLECTING'" class="deadline-field">
                <div class="deadline-head">
                  <span class="field-label">Response deadline</span>
                  <button v-if="!editingDeadline" type="button" class="btn-quiet btn-small" @click="startDeadlineEdit">
                    {{ deadline ? 'Change' : 'Set a deadline' }}
                  </button>
                </div>
                <p v-if="!editingDeadline" :class="['deadline-value', { overdue: deadlinePassed }]">
                  {{
                    deadline
                      ? `${formatWhen(deadline)} · ${deadlinePassed ? 'passed' : relative(deadline)}`
                      : 'None. Members can answer until you close collection.'
                  }}
                </p>
                <form v-else class="deadline-edit" @submit.prevent="saveDeadline">
                  <label class="sr-only" for="deadline-input">Collect answers until</label>
                  <input id="deadline-input" v-model="deadlineDraft" type="datetime-local" :min="nowLocal()" required />
                  <div class="deadline-actions">
                    <button class="btn-primary btn-small" :disabled="busy || !deadlineDraft">Save</button
                    ><button
                      v-if="deadline"
                      type="button"
                      class="btn-quiet btn-small"
                      :disabled="busy"
                      @click="clearDeadline"
                    >
                      Remove</button
                    ><button type="button" class="btn-quiet btn-small" @click="editingDeadline = false">Cancel</button>
                  </div>
                </form>
              </div>
              <Transition name="reveal">
                <div v-if="shareUrl && plan.state === 'COLLECTING'" class="invitation-field">
                  <label for="invite-link">Invitation link</label>
                  <input
                    id="invite-link"
                    readonly
                    :value="shareUrl"
                    @focus="($event.target as HTMLInputElement).select()"
                  />
                  <button :class="['copy-button', { 'btn-primary': !copied }]" @click="copyInvite">
                    <Transition name="swap" mode="out-in"
                      ><span :key="String(copied)" class="copy-label"
                        ><UiIcon :name="copied ? 'check' : 'link'" />{{ copied ? 'Copied' : 'Copy invitation' }}</span
                      ></Transition
                    >
                  </button>
                  <p class="helper-text">
                    Anyone with this link can join and respond. Share it with the people involved in this decision.
                  </p>
                </div>
              </Transition>
              <div class="aside-actions">
                <button
                  class="btn-primary"
                  v-if="plan.state === 'COLLECTING' && !shareUrl"
                  :disabled="busy"
                  @click="makeInvite"
                >
                  <UiIcon name="people" />Create invitation link
                </button>
                <button type="button" v-if="plan.state === 'COLLECTING' && ownIncomplete" @click="scrollToOwnResponse">
                  Answer your response
                </button>
                <button
                  v-if="plan.state === 'COLLECTING' && waitingOn.length"
                  type="button"
                  :disabled="busy"
                  @click="remind"
                >
                  <UiIcon :name="reminded ? 'check' : 'people'" />{{
                    reminded
                      ? 'Reminder copied'
                      : `Remind ${waitingOn.length === 1 ? waitingOn[0] : `${waitingOn.length} people`}`
                  }}
                </button>
                <button
                  v-if="plan.state === 'COLLECTING' && !readiness?.can_close && readiness?.can_close_early"
                  type="button"
                  :disabled="busy"
                  @click="closeEarly"
                >
                  Close with {{ readiness.submitted }} of {{ readiness.members }} responses
                </button>
                <button v-if="plan.state === 'COLLECTING'" :disabled="busy || !readiness?.can_close" @click="close">
                  Close collection
                </button>
                <button
                  class="btn-primary"
                  v-if="plan.state === 'REVIEWING'"
                  :disabled="busy || run?.status === 'pending'"
                  @click="recommend"
                >
                  {{
                    calculating || run?.status === 'pending'
                      ? 'Calculating…'
                      : run?.status === 'failed'
                        ? 'Retry recommendation'
                        : run
                          ? 'Recalculate'
                          : 'Calculate recommendation'
                  }}<UiIcon v-if="!calculating && run?.status !== 'pending'" name="arrow" />
                </button>
              </div>
              <div v-if="plan.state === 'COLLECTING' && readiness && !readiness.can_close" class="waiting-list">
                <p>Collection stays open until every member has submitted a complete, current response.</p>
                <ul class="incomplete-list">
                  <li
                    v-for="(member, index) in readiness.members_status.filter((m) => m.status !== 'complete')"
                    :key="member.id || index"
                  >
                    <span
                      ><strong
                        >{{ member.name }}<template v-if="member.user_id === auth.userID"> (you)</template></strong
                      >{{
                        member.status === 'stale' ? 'Needs to review the current form' : 'Awaiting complete submission'
                      }}</span
                    ><button
                      v-if="member.id && member.role !== 'ORGANISER' && member.user_id !== auth.userID"
                      type="button"
                      class="btn-quiet btn-danger btn-small"
                      :disabled="busy"
                      @click="removeRosterMember(member)"
                    >
                      Remove
                    </button>
                  </li>
                </ul>
              </div>
            </section>
          </Transition>
          <FactRecheckPanel
            v-if="plan.state === 'REVIEWING' && candidates.length && !selection"
            :round-id="roundId"
            :snapshot="snapshot"
            :candidates="candidates"
            :plan-dates="planDates"
          />
          <section v-if="['REVIEWING', 'CONFIRMED'].includes(plan.state)" class="panel revise-panel">
            <h2>Need to change the decision?</h2>
            <p>
              Revise the options, facts or questions in a new round. This round and any confirmed choice remain in the
              history. Members review their answers again.
            </p>
            <button :disabled="busy" @click="reopen">Revise in a new round</button>
          </section>
        </aside>
      </div>
    </template>
  </main>
</template>
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import UiIcon from './UiIcon.vue';
import FormParticipantView from './FormParticipantView.vue';
import OptionCards from './OptionCards.vue';
import RecommendationResults from './RecommendationResults.vue';
import FactRecheckPanel from './FactRecheckPanel.vue';
import { apiService, ApiError, request } from '@/services/api';
import { checkpointKey, readCheckpoint, writeCheckpoint } from '@/services/checkpoints';
import { operationId } from '@/services/ids';
import { stateLabel } from '@/services/labels';
import { useAuthStore } from '@/stores/auth';
import type { Snapshot, PlanRow, Round, Run, Selection, Candidate, ReadinessMember, RsvpSummary } from '@/types/form';
const props = defineProps<{ roundId: string; inviteToken?: string }>();
const emit = defineEmits<{ (event: 'open-round', id: string): void; (event: 'open-draft', id: string): void }>();
const auth = useAuthStore();
const snapshot = ref<Snapshot>();
const plan = ref<PlanRow>();
const roundList = ref<Round[]>([]);
const run = ref<Run>();
const selection = ref<Selection>();
const busy = ref(false);
const error = ref('');
const inviteCheckpointKey = computed(() => checkpointKey(auth.userID, `invite:${props.roundId}`));
const shareUrl = ref(readCheckpoint<string>(inviteCheckpointKey.value) || '');
const copied = ref(false);
const notice = ref('');
const calculating = ref(false);
const readiness = ref<{
  submitted: number;
  members: number;
  can_close: boolean;
  can_close_early: boolean;
  members_status: ReadinessMember[];
}>();
const progressError = ref('');
const backgroundError = ref('');
const historical = ref(false);
let pollTimer: ReturnType<typeof setTimeout> | undefined;
let polling = false;
const rsvpStatus = ref('');
const savedRsvp = ref('');
const rsvpRevision = ref(0);
const rsvpSummary = ref<RsvpSummary>();
let alive = true;
const ownResponseBox = ref<HTMLElement>();
const podiumKey = ref(0);
const eventDate = computed(() => selection.value?.selected_details?.event_date || '');
const eventWhen = computed(() => {
  const d = eventDate.value;
  if (!d) return '';
  const t = selection.value?.selected_details?.event_time;
  return t
    ? new Date(`${d}T${t}`).toLocaleString(undefined, {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        hour: 'numeric',
        minute: '2-digit',
      })
    : new Date(`${d}T00:00:00Z`).toLocaleDateString(undefined, {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        timeZone: 'UTC',
      });
});
const editingDeadline = ref(false);
const deadlineDraft = ref('');
const reminded = ref(false);
const rsvpOptions = [
  { value: 'GOING', label: 'Going' },
  { value: 'MAYBE', label: 'Maybe' },
  { value: 'DECLINED', label: 'Not joining' },
];
const organiser = computed(() => plan.value?.created_by_user_id === auth.userID);
const displayState = computed(() =>
  historical.value ? (selection.value ? 'CONFIRMED' : 'REVIEWING') : plan.value?.state || '',
);
// Members answer in a focused, page-by-page flow; organisers keep the full workspace.
const showAside = computed(
  () =>
    organiser.value && !historical.value && ['COLLECTING', 'REVIEWING', 'CONFIRMED'].includes(plan.value?.state || ''),
);
const memberCollecting = computed(() => !organiser.value && !historical.value && plan.value?.state === 'COLLECTING');
const candidates = computed(() =>
  run.value?.recommendation_view.recommendation
    ? [run.value.recommendation_view.recommendation, ...run.value.recommendation_view.alternatives]
    : [],
);
const selectedOption = computed(() =>
  snapshot.value?.options.find((row) => row.option_id === selection.value?.candidate_id),
);
const selectedTitle = computed(
  () =>
    candidates.value.find((row) => row.candidate_id === selection.value?.candidate_id)?.title ||
    selectedOption.value?.title ||
    'Selection confirmed',
);
const selectedSummary = computed(() => selectedOption.value?.brief?.summary || selectedOption.value?.description || '');
const ownIncomplete = computed(
  () => !!readiness.value?.members_status.some((m) => m.user_id === auth.userID && m.status !== 'complete'),
);
const currentRoundNumber = computed(() => roundList.value.find((r) => r.id === props.roundId)?.round_number || 1);
const deadline = computed(() => roundList.value.find((r) => r.id === props.roundId)?.deadline_at || null);
const now = ref(Date.now());
let clock: ReturnType<typeof setInterval> | undefined;
const deadlinePassed = computed(() => !!deadline.value && Date.parse(deadline.value) <= now.value);
const waitingOn = computed(() =>
  (readiness.value?.members_status || [])
    .filter((m) => m.status !== 'complete' && m.user_id !== auth.userID)
    .map((m) => m.name),
);
const planDates = computed(() => {
  const a = plan.value?.time_window_start,
    b = plan.value?.time_window_end;
  if (!a) return '';
  const f = (v: string) =>
    new Date(v).toLocaleDateString(undefined, { day: 'numeric', month: 'short', timeZone: 'UTC' });
  return b && f(a) !== f(b) ? `${f(a)} – ${f(b)}` : f(a);
});
const latestRoundId = computed(() => [...roundList.value].sort((a, b) => b.round_number - a.round_number)[0]?.id || '');

function scrollToOwnResponse() {
  ownResponseBox.value?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
function openLatestRound() {
  if (plan.value?.state === 'DRAFT' && organiser.value && snapshot.value) emit('open-draft', snapshot.value.plan_id);
  else if (latestRoundId.value) emit('open-round', latestRoundId.value);
}
function nowLocal() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}
function toLocalInput(iso: string) {
  const d = new Date(iso);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}
function formatWhen(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
  });
}
function relative(iso: string) {
  const minutes = Math.round((Date.parse(iso) - now.value) / 60000);
  if (minutes < 60) return `${Math.max(1, minutes)} min left`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} ${hours === 1 ? 'hour' : 'hours'} left`;
  return `${Math.round(hours / 24)} days left`;
}
function startDeadlineEdit() {
  deadlineDraft.value = deadline.value ? toLocalInput(deadline.value) : '';
  editingDeadline.value = true;
}
async function saveDeadline() {
  await act(async () => {
    await apiService.setDeadline(props.roundId, new Date(deadlineDraft.value).toISOString());
    await refreshRounds();
    editingDeadline.value = false;
  });
}
async function clearDeadline() {
  await act(async () => {
    await apiService.setDeadline(props.roundId, null);
    await refreshRounds();
    editingDeadline.value = false;
  });
}
async function refreshRounds() {
  const rounds = await apiService.rounds(snapshot.value!.plan_id);
  roundList.value = [...rounds.data].sort((a, b) => a.round_number - b.round_number);
}
// Guests have no email on file, so reminders go out through the organiser's own channels.
async function remind() {
  await act(async () => {
    if (!shareUrl.value) await makeInvite();
    const due = deadline.value && !deadlinePassed.value ? ` by ${formatWhen(deadline.value)}` : '';
    const text = `Reminder: we’re deciding “${plan.value!.title}”. Please add your answers${due}. It takes about ${Math.max(1, Math.round(snapshot.value!.questions.length * 0.4))} min and your answers stay private.`;
    if (navigator.share && matchMedia('(pointer: coarse)').matches) {
      try {
        await navigator.share({ title: plan.value!.title, text, url: shareUrl.value });
        return;
      } catch {
        /* fall back to copying */
      }
    }
    await navigator.clipboard.writeText(`${text}\n${shareUrl.value}`);
    reminded.value = true;
    setTimeout(() => {
      reminded.value = false;
    }, 2400);
  });
}
async function closeEarly() {
  const r = readiness.value!;
  const missing = r.members - r.submitted;
  if (
    !window.confirm(
      `Close with ${r.submitted} of ${r.members} responses? ${missing === 1 ? '1 member hasn’t' : `${missing} members haven’t`} submitted. Their answers won’t be counted, but they can still see the result and RSVP.`,
    )
  )
    return;
  await act(async () => {
    await apiService.close(props.roundId, true);
    await load();
  });
}
const phase = computed(() =>
  selection.value ? 2 : plan.value?.state === 'REVIEWING' ? 1 : plan.value?.state === 'CONFIRMED' ? 2 : 0,
);
async function optional<T>(get: () => Promise<T>) {
  try {
    return await get();
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return undefined;
    throw e;
  }
}
async function act(fn: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    await fn();
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Request failed';
  } finally {
    busy.value = false;
  }
}
async function load() {
  snapshot.value = await apiService.snapshot(props.roundId);
  plan.value = await apiService.plan(snapshot.value.plan_id);
  const rounds = await apiService.rounds(snapshot.value.plan_id);
  roundList.value = [...rounds.data].sort((a, b) => a.round_number - b.round_number);
  historical.value = [...rounds.data].sort((a, b) => b.round_number - a.round_number)[0]?.id !== props.roundId;
  run.value = await optional(() => apiService.result(props.roundId));
  selection.value = await optional(() => apiService.selection(props.roundId));
  if (selection.value) {
    const own = await apiService.rsvp(props.roundId);
    rsvpRevision.value = own.revision;
    rsvpStatus.value = savedRsvp.value = own.status || '';
    rsvpSummary.value = own.summary;
  }
  await updateProgress();
}
async function refresh() {
  await act(load);
}
async function updateProgress() {
  if (!organiser.value || plan.value?.state !== 'COLLECTING') {
    readiness.value = undefined;
    return;
  }
  try {
    const row = await request<{
      member_count: number;
      complete_count: number;
      can_close: boolean;
      can_close_early?: boolean;
      members: ReadinessMember[];
      progress: { submittedCount?: number };
    }>(`/api/planning/v1/rounds/${props.roundId}/readiness`);
    readiness.value = {
      submitted: row.complete_count,
      members: row.member_count,
      can_close: row.can_close,
      can_close_early: !!row.can_close_early,
      members_status: row.members,
    };
    progressError.value = '';
  } catch {
    readiness.value = undefined;
    progressError.value = 'Progress could not be loaded. Refresh before closing.';
  }
}
async function removeRosterMember(member: ReadinessMember) {
  if (!member.id || !window.confirm(`Remove ${member.name} from this plan?`)) return;
  await act(async () => {
    await apiService.removeMember(member.id!);
    await updateProgress();
  });
}
async function makeInvite() {
  await act(async () => {
    const invite = await apiService.invite(snapshot.value!.plan_id, auth.userID);
    shareUrl.value = `${location.origin}/#${new URLSearchParams({ round: props.roundId, invite: invite.token })}`;
    writeCheckpoint(inviteCheckpointKey.value, shareUrl.value);
  });
}
async function copyInvite() {
  await act(async () => {
    await navigator.clipboard.writeText(shareUrl.value);
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 2400);
  });
}
async function close() {
  const count = readiness.value
    ? ` ${readiness.value.submitted} of ${readiness.value.members} members have submitted.`
    : '';
  if (
    !window.confirm(`Close collection?${count} This freezes the roster and responses; members can’t edit afterwards.`)
  )
    return;
  await act(async () => {
    await apiService.close(props.roundId);
    await load();
  });
}
async function recommend() {
  calculating.value = true;
  await act(async () => {
    run.value = await apiService.recommend(props.roundId);
    podiumKey.value++;
  });
  calculating.value = false;
  schedulePoll();
}
async function reopen() {
  if (!window.confirm('Create a new editable round? Existing results and RSVPs stay attached to this round.')) return;
  await act(async () => {
    const key = `reopen:${props.roundId}`;
    const operation = sessionStorage.getItem(key) || operationId();
    sessionStorage.setItem(key, operation);
    await apiService.reopen(props.roundId, operation);
    emit('open-draft', snapshot.value!.plan_id);
  });
}
function schedulePoll() {
  clearTimeout(pollTimer);
  if (alive && !selection.value) pollTimer = setTimeout(pollStatus, run.value?.status === 'pending' ? 1000 : 5000);
}
async function pollStatus() {
  if (!alive) return;
  if (document.hidden || busy.value || polling) {
    schedulePoll();
    return;
  }
  polling = true;
  try {
    const current = await apiService.plan(snapshot.value!.plan_id);
    if (!alive) return;
    const previousState = plan.value?.state;
    plan.value = current;
    if (current.state !== previousState) {
      const rounds = await apiService.rounds(snapshot.value!.plan_id);
      if (alive) {
        roundList.value = [...rounds.data].sort((a, b) => a.round_number - b.round_number);
        historical.value = [...rounds.data].sort((a, b) => b.round_number - a.round_number)[0]?.id !== props.roundId;
      }
    }
    if (current.state === 'COLLECTING' && !historical.value) {
      await updateProgress();
      backgroundError.value = '';
      return;
    }
    const previousRunStatus = run.value?.status;
    const latestRun = await optional(() => apiService.result(props.roundId));
    if (!alive) return;
    if (latestRun?.status === 'ranked' && previousRunStatus !== 'ranked') podiumKey.value++;
    run.value = latestRun;
    const chosen = await optional(() => apiService.selection(props.roundId));
    if (!alive) return;
    if (chosen) {
      const first = !selection.value;
      selection.value = chosen;
      const own = await apiService.rsvp(props.roundId);
      if (!alive) return;
      rsvpSummary.value = own.summary;
      if (first) {
        rsvpRevision.value = own.revision;
        rsvpStatus.value = savedRsvp.value = own.status || '';
      }
    }
    await updateProgress();
    backgroundError.value = '';
  } catch {
    if (alive)
      backgroundError.value =
        'Status could not be updated. Your saved response and background calculation are retained; updates will retry.';
  } finally {
    polling = false;
    schedulePoll();
  }
}
function visible() {
  if (!document.hidden && alive && snapshot.value) {
    clearTimeout(pollTimer);
    void pollStatus();
  }
}
// A date-poll confirmation arrives with its date; otherwise ask before confirming.
async function confirm(candidate: Candidate, when?: { date: string; time?: string }) {
  if (!when && !window.confirm(`Confirm “${candidate.title}” as the group’s choice? Members will be asked to RSVP.`))
    return;
  await act(async () => {
    const key = `confirmation:${props.roundId}:${run.value!.run_id}:${candidate.candidate_id}:${when?.date || ''}:${when?.time || ''}`;
    const operation = sessionStorage.getItem(key) || operationId();
    sessionStorage.setItem(key, operation);
    selection.value = await apiService.confirm(
      props.roundId,
      run.value!.run_id,
      candidate.candidate_id,
      operation,
      when,
    );
    await load();
  });
}
async function saveRsvp() {
  notice.value = '';
  await act(async () => {
    await apiService.saveRsvp(props.roundId, selection.value!.selection_version, rsvpRevision.value, rsvpStatus.value);
    const own = await apiService.rsvp(props.roundId);
    rsvpRevision.value = own.revision;
    savedRsvp.value = own.status || rsvpStatus.value;
    rsvpSummary.value = own.summary;
    notice.value = 'RSVP saved.';
  });
}
function downloadCalendar() {
  if (!plan.value || !selection.value) return;
  const candidate = candidates.value.find((c) => c.candidate_id === selection.value?.candidate_id);
  const stamp = (d: Date) =>
    d
      .toISOString()
      .replace(/[-:]/g, '')
      .replace(/\.\d{3}/, '');
  const now = new Date();
  // Prefer the date the organiser confirmed, then the option's own time, then the plan's first day.
  const chosen = selection.value.selected_details?.event_date || '';
  const chosenTime = selection.value.selected_details?.event_time || '';
  const planDay = plan.value.time_window_start?.slice(0, 10) || '';
  const allDay = (chosen && !chosenTime) || (!chosen && !candidate?.start_at && !!planDay);
  const day = chosen || planDay;
  const start =
    chosen && chosenTime
      ? new Date(`${chosen}T${chosenTime}`)
      : candidate?.start_at
        ? new Date(candidate.start_at)
        : new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 19, 0, 0);
  const end =
    chosen && chosenTime
      ? new Date(start.getTime() + 7200000)
      : candidate?.end_at
        ? new Date(candidate.end_at)
        : new Date(start.getTime() + 7200000);
  const compact = (d: string) => d.replaceAll('-', '');
  const next = (d: string) => {
    const n = new Date(`${d}T00:00:00Z`);
    n.setUTCDate(n.getUTCDate() + 1);
    return n.toISOString().slice(0, 10);
  };
  const clean = (v?: string) => (v || '').replace(/\r?\n/g, '\\n').replace(/[,;]/g, '\\$&');
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//What2Do//Confirmed Plan//EN',
    'BEGIN:VEVENT',
    `UID:${props.roundId}-v${selection.value.selection_version}@what2do`,
    `DTSTAMP:${stamp(now)}`,
    ...(allDay
      ? [`DTSTART;VALUE=DATE:${compact(day)}`, `DTEND;VALUE=DATE:${compact(next(day))}`]
      : [`DTSTART:${stamp(start)}`, `DTEND:${stamp(end)}`]),
    `SUMMARY:${clean(`${plan.value.title}: ${selectedTitle.value}`)}`,
    ...(selectedSummary.value ? [`DESCRIPTION:${clean(selectedSummary.value)}`] : []),
    ...(selectedOption.value?.brief?.where ? [`LOCATION:${clean(selectedOption.value.brief.where)}`] : []),
    'END:VEVENT',
    'END:VCALENDAR',
  ];
  const blob = new Blob([lines.join('\r\n')], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${plan.value.title.toLowerCase().replace(/[^a-z0-9]+/g, '-') || 'plan'}.ics`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
onMounted(async () => {
  await act(async () => {
    if (props.inviteToken) {
      try {
        await apiService.snapshot(props.roundId);
      } catch (e) {
        if (e instanceof ApiError && (e.status === 403 || e.status === 404))
          await apiService.join(props.inviteToken, auth.userID, auth.username);
        else throw e;
      }
    }
    await load();
    if (props.inviteToken) history.replaceState(null, '', `/#${new URLSearchParams({ round: props.roundId })}`);
  });
  if (!alive) return;
  if (snapshot.value) schedulePoll();
  document.addEventListener('visibilitychange', visible);
});
onMounted(() => {
  clock = setInterval(() => {
    now.value = Date.now();
  }, 30000);
});
onUnmounted(() => {
  clearInterval(clock);
  alive = false;
  clearTimeout(pollTimer);
  document.removeEventListener('visibilitychange', visible);
});
</script>
<style scoped>
.workspace {
  padding: clamp(28px, 5vh, 56px) var(--gutter) 80px;
}
.loading .title {
  height: 56px;
  width: 40%;
}
.loading .tall {
  height: 180px;
}
.round-header {
  margin-bottom: 28px;
}
.round-header h1 {
  overflow-wrap: anywhere;
  font-size: clamp(2.125rem, 1.5rem + 1.8vw, 3.25rem);
  color: var(--night);
  margin-bottom: 10px;
}
.round-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--muted);
  font-size: 0.875rem;
  margin-bottom: 14px;
}
.decision-question {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--ink-2);
  margin: 0 0 8px;
  overflow-wrap: anywhere;
}
.plan-description {
  font-size: 1rem;
  color: var(--muted);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.refresh {
  flex-shrink: 0;
}
.refresh.spinning .ui-icon {
  animation: spin 900ms linear infinite;
}
/* Progress: three stops on one line. */
.round-progress {
  position: relative;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  list-style: none;
  padding: 0;
  margin: 0 0 36px;
}
.round-progress::before,
.round-progress::after {
  content: '';
  position: absolute;
  top: 16px;
  left: 17px;
  width: calc(100% * 2 / 3);
  height: 3px;
  border-radius: 3px;
  background: var(--sky-100);
}
.round-progress::after {
  width: calc(100% * 2 / 3 * var(--phase) / 2);
  background: var(--blue);
  transition: width 700ms var(--ease-out);
}
.round-progress li {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 0;
  color: var(--muted);
  font-size: 0.9375rem;
  font-weight: 600;
  transition: color var(--base) ease-out;
}
.phase-label {
  padding: 0 14px 0 12px;
  background: var(--ground);
}
.phase-dot {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 2px solid var(--sky-200);
  background: var(--ground);
  font-size: 0.875rem;
  flex-shrink: 0;
  transition:
    background-color var(--base) ease-out,
    border-color var(--base) ease-out,
    color var(--base) ease-out;
}
.round-progress .current {
  color: var(--blue-ink);
}
.current .phase-dot {
  background: var(--blue);
  color: #fff;
  border-color: var(--blue);
}
.complete {
  color: var(--ink);
}
.complete .phase-dot {
  color: var(--blue);
  background: var(--surface);
  border-color: var(--blue);
}
.phase-dot .ui-icon {
  width: 16px;
  height: 16px;
}
.round-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: clamp(24px, 3vw, 48px);
  align-items: start;
}
.round-body.has-aside {
  grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
}
.round-main {
  min-width: 0;
}
.round-aside {
  position: sticky;
  top: 24px;
  display: grid;
  gap: 16px;
  min-width: 0;
}
.round-aside .panel {
  margin: 0;
  padding: 24px;
}
.round-aside h2 {
  font-size: 1.25rem;
  margin-bottom: 6px;
}
.aside-lede,
.revise-panel p {
  color: var(--muted);
  font-size: 0.9375rem;
}
.collect-progress {
  margin: 20px 0 8px;
}
.collect-figure {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.collect-figure strong {
  font-size: 3rem;
  line-height: 1;
  font-weight: 300;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
  color: var(--night);
}
.collect-figure .of {
  font-size: 1.5rem;
  color: var(--faint);
}
.collect-figure > span {
  color: var(--muted);
  font-size: 0.9375rem;
}
.invitation-field {
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
}
.invitation-field > label {
  margin: 0 0 8px;
}
.invitation-field input {
  font-size: 0.875rem;
  min-height: 44px;
}
.copy-button {
  width: 100%;
  margin-top: 10px;
}
.copy-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.aside-actions {
  display: grid;
  gap: 10px;
  margin-top: 20px;
}
.aside-actions button {
  width: 100%;
}
.overdue {
  color: var(--danger);
  font-weight: 600;
}
.deadline-field {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}
.deadline-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.field-label {
  font-size: 0.9375rem;
  font-weight: 600;
}
.deadline-value {
  margin: 4px 0 0;
  font-size: 0.9375rem;
  color: var(--ink-2);
}
.deadline-edit {
  display: grid;
  gap: 10px;
  margin-top: 8px;
}
.deadline-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.waiting-list {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
  font-size: 0.9375rem;
}
.waiting-list > p {
  color: var(--muted);
  font-size: 0.875rem;
}
.incomplete-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.incomplete-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-top: 1px solid var(--line);
}
.incomplete-list li > span {
  display: grid;
  font-size: 0.875rem;
  color: var(--muted);
  min-width: 0;
  overflow-wrap: anywhere;
}
.incomplete-list strong {
  color: var(--ink);
  font-size: 0.9375rem;
}
.waiting {
  margin: 0 0 24px;
}
.historical-callout {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 24px;
}
.historical-callout p {
  margin: 0;
}
.options-section {
  margin: 0 0 40px;
}
.options-section h2,
.own-heading {
  font-size: 1.25rem;
  display: flex;
  gap: 10px;
  align-items: baseline;
  margin-bottom: 16px;
}
.count {
  font-size: 0.9375rem;
  font-weight: 400;
  color: var(--faint);
  font-variant-numeric: tabular-nums;
}
.own-response {
  margin: 0 0 40px;
  scroll-margin-top: 24px;
}
.own-response :deep(.response-flow) {
  margin-top: 0;
}
.event-when {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--blue-ink);
  margin: 0 0 10px;
}
.round-switch {
  padding: 2px 10px;
  min-height: 28px;
  font-size: 0.8125rem;
}
/* Confirmed selection */
.selection-panel {
  margin: 0 0 40px;
  padding: clamp(24px, 3vw, 36px);
  border-radius: 20px;
  background: var(--surface);
  border: 1px solid var(--sky-300);
  box-shadow: var(--shadow-md);
}
.selection-head {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 14px;
}
.selection-head h2 {
  font-size: 0.9375rem;
  color: var(--blue-ink);
  margin-bottom: 2px;
  letter-spacing: 0;
}
.seal {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--blue);
  flex-shrink: 0;
  animation: seal-in 520ms var(--ease-out) both;
}
.seal svg {
  width: 28px;
  height: 28px;
  fill: none;
  stroke: #fff;
  stroke-width: 2.4;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 20;
  stroke-dashoffset: 0;
  animation: draw 600ms 240ms var(--ease-out) both;
}
.selected-title {
  font-size: clamp(1.75rem, 1.3rem + 1.2vw, 2.5rem);
  font-weight: 300;
  letter-spacing: -0.02em;
  line-height: 1.15;
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--night);
}
.selected-summary {
  font-size: 1rem;
  color: var(--ink-2);
  margin: 0 0 10px;
}
.selection-lede {
  color: var(--muted);
}
.rsvp-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
  margin: 4px 0 16px;
  border: 1px solid var(--line);
  border-radius: 14px;
  overflow: hidden;
  width: fit-content;
  max-width: 100%;
}
.rsvp-summary > div {
  padding: 12px 22px;
  display: grid;
}
.rsvp-summary > div + div {
  border-left: 1px solid var(--line);
}
.rsvp-summary dt {
  font-size: 0.8125rem;
  color: var(--muted);
}
.rsvp-summary dd {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 300;
  color: var(--night);
}
.rsvp-decline-note {
  margin: 0 0 16px;
}
.rsvp {
  margin: 20px 0 12px;
}
.rsvp-options {
  grid-template-columns: repeat(3, minmax(0, 200px));
}
.rsvp-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  flex-wrap: wrap;
}
.saved-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
}
.saved-note .ui-icon {
  width: 16px;
  height: 16px;
}
.settle-enter-active {
  transition:
    opacity var(--slow) var(--ease-out),
    transform var(--slow) var(--ease-out);
}
.settle-enter-from {
  opacity: 0;
  transform: translateY(12px) scale(0.99);
}
@keyframes seal-in {
  from {
    transform: scale(0.6);
    opacity: 0;
  }
}
@keyframes draw {
  from {
    stroke-dashoffset: 20;
  }
}
@media (max-width: 1180px) {
  .round-body.has-aside {
    grid-template-columns: minmax(0, 1fr);
  }
  .round-aside {
    position: static;
    order: -1;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
  }
}
@media (max-width: 760px) {
  .workspace {
    padding: 24px 16px 40px;
  }
  .round-header > button {
    align-self: flex-start;
  }
  .round-progress li {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
    font-size: 0.8125rem;
  }
  .round-progress li {
    gap: 8px;
  }
  .phase-label {
    padding: 0 4px 0 0;
  }
  .rsvp-options {
    grid-template-columns: minmax(0, 1fr);
  }
  .rsvp-actions button {
    width: 100%;
  }
  .rsvp-summary {
    width: 100%;
  }
  .rsvp-summary > div {
    flex: 1;
    padding: 10px 14px;
  }
}
</style>
