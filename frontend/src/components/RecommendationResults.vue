<template>
  <section class="recommendation-section" aria-labelledby="recommendation-heading">
    <div class="section-heading">
      <div>
        <h2 id="recommendation-heading">Group recommendation</h2>
        <p>Options ranked against the group’s confirmed responses.</p>
      </div>
      <span :class="['badge', run.status.toLowerCase()]">{{ stateLabel(run.status) }}</span>
    </div>
    <div v-if="run.status === 'pending'" class="pending" role="status">
      <span class="pulse" aria-hidden="true"></span>Interpreting responses, checking any missing evidence and
      calculating the recommendation. You can return later; progress is saved.
    </div>
    <p v-if="run.recommendation_view.next_action && nextAction" class="callout warning">{{ nextAction }}</p>
    <p v-if="run.recommendation_view.not_counted_members" class="callout">
      {{
        run.recommendation_view.not_counted_members === 1
          ? '1 member hadn’t responded when collection closed, so they weren’t counted.'
          : `${run.recommendation_view.not_counted_members} members hadn’t responded when collection closed, so they weren’t counted.`
      }}
      They can still see the result and RSVP.
    </p>
    <ul v-if="run.issues.length" class="issue-list">
      <li v-for="(issue, index) in run.issues" :key="index">{{ stateLabel(issue.code) }}</li>
    </ul>

    <!-- Result board: the ranking arrives row by row, like a departures display. -->
    <div v-if="candidates.length" :key="`board-${podiumKey}`" class="result-board" aria-label="Ranked options">
      <div class="board-head">
        <p class="board-headline">
          {{ selection ? 'Confirmed' : 'Top pick' }}:
          <strong>{{ selection ? selectedTitle : candidates[0]?.title }}</strong>
        </p>
        <div class="board-tools">
          <span>{{ candidates.length }} {{ candidates.length === 1 ? 'option' : 'options' }} ranked</span>
        </div>
      </div>
      <div class="board-cols" aria-hidden="true">
        <span>Rank</span><span>Option</span><span>{{ hasPreferences ? 'Average fit' : 'Requirements' }}</span
        ><span>{{ hasPreferences ? 'Lowest member' : 'Cost' }}</span>
      </div>
      <ol class="board-rows">
        <li
          v-for="(candidate, index) in candidates"
          :key="candidate.candidate_id"
          :class="{
            lead: index === 0 && !selection,
            chosen: selection?.candidate_id === candidate.candidate_id,
          }"
          :style="{ '--i': index }"
        >
          <button type="button" class="board-row" @click="focusCandidate(candidate.candidate_id)">
            <span class="board-rank">{{ candidate.rank }}</span>
            <span class="board-option">
              <span class="board-thumb" aria-hidden="true"
                ><img
                  v-if="optionLeadPhoto(candidate.candidate_id)"
                  :src="optionLeadPhoto(candidate.candidate_id)"
                  alt=""
                /><span v-else>{{ optionMonogram(candidate.title) }}</span></span
              >
              <span class="board-name"
                ><strong>{{ candidate.title }}</strong
                ><small v-if="optionMeta(candidate.candidate_id)">{{ optionMeta(candidate.candidate_id) }}</small></span
              >
            </span>
            <span class="board-fit">
              <template v-if="hasPreferences"
                ><span class="board-bar"><span :style="{ '--v': candidate.average_member_score }"></span></span
                ><b>{{ percent(candidate.average_member_score) }}</b></template
              >
              <span v-else class="met"><UiIcon name="check" />All met</span>
            </span>
            <span class="board-min">{{
              hasPreferences
                ? percent(candidate.minimum_member_score)
                : candidate.estimated_cost_minor != null
                  ? money(candidate)
                  : '—'
            }}</span>
          </button>
        </li>
      </ol>
    </div>

    <section v-if="datePoll" class="date-poll-result" aria-labelledby="dates-heading">
      <div class="date-poll-head">
        <h3 id="dates-heading">When works best</h3>
        <p>
          {{ datePoll.respondents }} {{ datePoll.respondents === 1 ? 'answer' : 'answers' }} counted<template
            v-if="datePoll.best_date"
          >
            · Best: <strong>{{ longDate(datePoll.best_date) }}</strong></template
          >
        </p>
      </div>
      <ul class="date-rows">
        <li
          v-for="(row, di) in datePoll.dates"
          :key="row.date"
          :class="{ best: row.date === datePoll.best_date, chosen: row.date === eventDate }"
          :style="{ '--i': di }"
        >
          <span class="date-label"
            >{{ longDate(row.date) }}<span v-if="row.date === eventDate" class="date-tag">Chosen</span
            ><span v-else-if="row.date === datePoll.best_date" class="date-tag">Best</span></span
          >
          <span class="date-bar" aria-hidden="true">
            <span class="works" :style="{ '--w': share(row.works) }"></span
            ><span class="maybe" :style="{ '--w': share(row.maybe) }"></span
            ><span class="cannot" :style="{ '--w': share(row.cannot) }"></span>
          </span>
          <span class="date-counts">{{ row.works }} works · {{ row.maybe }} if needed · {{ row.cannot }} can’t</span>
        </li>
      </ul>
    </section>

    <details v-if="run.supplemented_facts?.length" class="supplemented-facts">
      <summary>Evidence added during calculation</summary>
      <p class="helper-text">
        These sourced details supplemented the published options for this result. They are saved with the calculation.
      </p>
      <div v-for="fact in run.supplemented_facts" :key="`${fact.option_id}:${fact.attribute_id}`" class="supplement">
        <p>
          <strong
            >{{ snapshot.options.find((o) => o.option_id === fact.option_id)?.title }} ·
            {{ factLabel(fact.attribute_id) }}</strong
          >: {{ Array.isArray(fact.value) ? fact.value.join(', ') : fact.value }} {{ fact.unit || '' }}
        </p>
        <p class="helper-text">{{ fact.source_text }}</p>
        <ul>
          <li v-for="source in fact.sources" :key="source.url">
            <a v-if="safeSource(source.url)" :href="source.url" target="_blank" rel="noopener noreferrer">{{
              source.title || source.url
            }}</a>
          </li>
        </ul>
      </div>
    </details>

    <h3 v-if="candidates.length" class="detail-heading">Why each option ranked where it did</h3>
    <div class="candidate-grid">
      <article
        v-for="(candidate, index) in candidates"
        :key="candidate.candidate_id"
        :id="`candidate-${candidate.candidate_id}`"
        :class="[
          'candidate-card',
          'rise',
          {
            recommended: candidate.rank === 1,
            chosen: selection?.candidate_id === candidate.candidate_id,
            spotlighted: focusedCandidateId === candidate.candidate_id,
            'has-attributes': candidateAttributes(candidate).length > 0,
          },
        ]"
        :style="{ '--i': index }"
      >
        <div class="candidate-overview">
          <div v-if="optionPhotos(candidate.candidate_id).length" class="candidate-photo-strip">
            <figure
              v-for="(photo, pi) in optionPhotos(candidate.candidate_id)"
              :key="photo.name"
              :class="{ lead: pi === 0 }"
            >
              <img
                v-if="photoUrls[photo.name]"
                :src="photoUrls[photo.name]"
                :alt="pi === 0 ? candidate.title : ''"
                loading="lazy"
                @load="loadedPhotos.add(photo.name)"
                :class="{ ready: loadedPhotos.has(photo.name) }"
              />
              <span v-else class="photo-placeholder" aria-hidden="true"></span>
              <figcaption v-if="photo.attributions.length && pi === 0">
                Photo:
                <template v-for="(a, ai) in photo.attributions" :key="ai"
                  ><a v-if="a.uri" :href="a.uri" target="_blank" rel="noopener noreferrer">{{ a.name }}</a
                  ><span v-else>{{ a.name }}</span></template
                >
              </figcaption>
            </figure>
          </div>

          <div class="candidate-body">
            <p class="rank">
              <span class="rank-num">{{ candidate.rank }}</span
              >{{
                selection?.candidate_id === candidate.candidate_id
                  ? 'Confirmed'
                  : candidate.rank === 1
                    ? 'Recommended'
                    : `Ranked ${ordinal(candidate.rank)}`
              }}<template v-if="optionKindLabel(candidate.candidate_id)">
                · {{ optionKindLabel(candidate.candidate_id) }}</template
              >
            </p>
            <h3>
              <span class="sr-only">{{ candidate.rank === 1 ? 'Recommended: ' : '' }}</span
              >{{ candidate.title }}
            </h3>
            <p v-if="optionMeta(candidate.candidate_id)" class="candidate-meta">
              {{ optionMeta(candidate.candidate_id) }}
            </p>
            <p v-if="optionAddress(candidate.candidate_id)" class="candidate-meta address">
              {{ optionAddress(candidate.candidate_id) }}
            </p>
            <p v-if="optionSummary(candidate.candidate_id)" class="candidate-description">
              {{ optionSummary(candidate.candidate_id) }}
            </p>
            <ul v-if="optionHighlights(candidate.candidate_id).length" class="candidate-highlights">
              <li v-for="h in optionHighlights(candidate.candidate_id)" :key="h">{{ h }}</li>
            </ul>

            <p v-if="candidate.primary_objective_tie_size > 1" class="tie">
              Equally suitable with {{ candidate.primary_objective_tie_size - 1 }} other
              {{ candidate.primary_objective_tie_size === 2 ? 'option' : 'options' }}. Cost, time, then ID set the
              display order.
            </p>
            <dl v-if="hasPreferences" class="scores">
              <div>
                <dt>Average group fit</dt>
                <dd>{{ percent(candidate.average_member_score) }}</dd>
                <span class="meter" aria-hidden="true"
                  ><span :style="{ '--value': candidate.average_member_score }"></span
                ></span>
              </div>
              <div>
                <dt>Least-satisfied member</dt>
                <dd>{{ percent(candidate.minimum_member_score) }}</dd>
                <span class="meter" aria-hidden="true"
                  ><span :style="{ '--value': candidate.minimum_member_score }"></span
                ></span>
              </div>
            </dl>
            <p v-else class="no-pref-note">Meets the requirements. No scored preferences were collected.</p>

            <dl class="facts" v-if="candidate.estimated_cost_minor != null || candidate.start_at">
              <div v-if="candidate.estimated_cost_minor != null">
                <dt>Cost per person</dt>
                <dd>{{ money(candidate) }}</dd>
              </div>
              <div v-if="candidate.start_at">
                <dt>When</dt>
                <dd>
                  {{ new Date(candidate.start_at).toLocaleString()
                  }}<template v-if="candidate.end_at"> – {{ new Date(candidate.end_at).toLocaleString() }}</template>
                </dd>
              </div>
            </dl>
            <p v-if="paretoIds.has(candidate.candidate_id)" class="tradeoff">
              Trade-off: {{ tradeoffs(candidate.candidate_id) }}
            </p>
            <button
              :class="{ 'btn-primary': candidate.rank === 1 }"
              v-if="canConfirm && confirming !== candidate.candidate_id"
              :disabled="busy"
              @click="datePoll ? startConfirm(candidate) : emit('confirm', candidate)"
            >
              Confirm {{ candidate.title }}<UiIcon name="check" />
            </button>
            <Transition name="reveal">
              <form
                v-if="confirming === candidate.candidate_id"
                class="confirm-when"
                @submit.prevent="submitConfirm(candidate)"
              >
                <p class="confirm-when-title">When is {{ candidate.title }}?</p>
                <div class="confirm-when-fields">
                  <label
                    >Date<select v-model="confirmDate" required>
                      <option v-for="row in datePoll!.dates" :key="row.date" :value="row.date">
                        {{ longDate(row.date) }} · {{ row.works }} works{{
                          row.date === datePoll!.best_date ? ' (best)' : ''
                        }}
                      </option>
                    </select></label
                  >
                  <label
                    >Start time <span class="optional">(optional)</span><input v-model="confirmTime" type="time"
                  /></label>
                </div>
                <p class="helper-text">Members are asked to RSVP and can add it to their calendar.</p>
                <div class="confirm-when-actions">
                  <button class="btn-primary" :disabled="busy || !confirmDate">
                    Confirm for {{ confirmDate ? longDate(confirmDate) : 'this date' }}<UiIcon name="check" /></button
                  ><button type="button" class="btn-quiet" @click="confirming = ''">Cancel</button>
                </div>
              </form>
            </Transition>
          </div>
        </div>

        <div v-if="candidateAttributes(candidate).length" class="attr-breakdown">
          <div class="attr-breakdown-head">
            <h4>Scoring by criterion</h4>
            <span
              >{{ candidateAttributes(candidate).length }}
              {{ candidateAttributes(candidate).length === 1 ? 'criterion' : 'criteria' }}</span
            >
          </div>
          <ul class="attr-list">
            <li
              v-for="(attr, ai) in candidateAttributes(candidate)"
              :key="attr.attribute_id"
              class="attr-item"
              :style="{ '--ai': ai }"
            >
              <div class="attr-top">
                <strong class="attr-name">{{ factLabel(attr.attribute_id) }}</strong>
                <span v-if="attr.score != null" :class="['attr-score', attrFitClass(attr.score)]">{{
                  attr.role === 'hard'
                    ? attr.score >= 1
                      ? 'Passed'
                      : 'Not met'
                    : `${Math.round(attr.score * 100)}% fit`
                }}</span>
              </div>
              <p class="attr-role">
                {{
                  attr.role === 'hard'
                    ? 'Requirement'
                    : attr.weight != null
                      ? `Preference · ${Math.round(attr.weight * 100)}% weight`
                      : 'Option detail'
                }}<template v-if="attr.supplemented"> · Researched</template>
              </p>
              <p class="attr-value">
                <template v-if="attr.attribute_id === 'option_rating'">Members’ direct ratings</template>
                <template v-else-if="Array.isArray(attr.value) && attr.value.length">{{
                  attr.value.join(', ')
                }}</template>
                <template v-else-if="attr.value != null && String(attr.value) !== ''">{{
                  formatAttrValue(attr)
                }}</template>
                <span v-else class="muted">Not specified</span>
              </p>
              <span v-if="attr.score != null" class="meter attr-meter" aria-hidden="true"
                ><span :class="attrFitClass(attr.score)" :style="{ '--value': attr.score }"></span
              ></span>
              <p class="attr-reason">{{ attr.reason }}</p>
            </li>
          </ul>
        </div>
      </article>
    </div>
    <div v-if="run.recommendation_view.unavailable_candidates.length" class="unavailable">
      <h3>Ruled out</h3>
      <ul>
        <li v-for="candidate in run.recommendation_view.unavailable_candidates" :key="candidate.candidate_id">
          <span>{{ candidate.title }}</span
          ><span class="muted">{{ unavailableReason(candidate) }}</span>
        </li>
      </ul>
    </div>
  </section>
</template>
<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import UiIcon from './UiIcon.vue';
import { factLabel, factValue } from '@/services/facts';
import { stateLabel } from '@/services/labels';
import { useOptionDetails } from '@/composables/useOptionDetails';
import type { AttributeBreakdownItem, Candidate, Run, Selection, Snapshot } from '@/types/form';

// The shared result of a round: the ranked board, date poll, added evidence and why each
// option ranked where it did. The parent performs a confirmation this panel requests.
const props = defineProps<{
  roundId: string;
  run: Run;
  snapshot: Snapshot;
  candidates: Candidate[];
  selection?: Selection;
  selectedTitle: string;
  canConfirm: boolean;
  busy: boolean;
  podiumKey: number;
}>();
const emit = defineEmits<{ (event: 'confirm', candidate: Candidate, when?: { date: string; time?: string }): void }>();
const {
  photoUrls,
  loadedPhotos,
  optionOf,
  optionPhotos,
  optionLeadPhoto,
  optionKindLabel,
  optionSummary,
  optionHighlights,
  optionMeta,
  optionAddress,
  optionMonogram,
} = useOptionDetails(
  () => props.roundId,
  () => props.snapshot,
);
// The candidate whose date form is open, and that form's values.
const confirming = ref('');
const confirmDate = ref('');
const confirmTime = ref('');
const eventDate = computed(() => props.selection?.selected_details?.event_date || '');
const datePoll = computed(() => (props.run.date_poll?.dates.length ? props.run.date_poll : undefined));
function longDate(day: string) {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  });
}
function share(count: number) {
  return datePoll.value?.respondents ? count / datePoll.value.respondents : 0;
}
function startConfirm(candidate: Candidate) {
  confirming.value = candidate.candidate_id;
  confirmDate.value = datePoll.value?.best_date || datePoll.value?.dates[0]?.date || '';
  confirmTime.value = '';
}
const focusedCandidateId = ref('');
const hasPreferences = computed(() =>
  props.snapshot.questions.some((question) => question.role === 'soft' || !question.role),
);
const paretoIds = computed(
  () => new Set(props.run.recommendation_view.pareto_alternatives.map((row) => row.candidate_id)),
);
function focusCandidate(id: string) {
  focusedCandidateId.value = id;
  document.getElementById(`candidate-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  setTimeout(() => {
    if (focusedCandidateId.value === id) focusedCandidateId.value = '';
  }, 1600);
}
function attrFitClass(score?: number | null) {
  if (score == null) return 'fit-neutral';
  return score >= 0.75 ? 'fit-high' : score >= 0.45 ? 'fit-mid' : 'fit-low';
}
function formatAttrValue(attr: AttributeBreakdownItem) {
  return factValue(
    { criterion: attr.attribute_id, value: attr.value, value_type: attr.value_type, unit: attr.unit },
    props.snapshot.currency || 'SGD',
  );
}
function candidateAttributes(candidate: Candidate): AttributeBreakdownItem[] {
  const fromRun = props.run.attribute_breakdown?.[candidate.candidate_id];
  if (fromRun?.length) return fromRun;
  const opt = optionOf(candidate.candidate_id);
  const questions = (props.snapshot.questions || []).filter((q) => q.role !== 'informational');
  const activeQuestions = questions.filter((q) => q.criterion && q.criterion !== 'preferences');
  const suppFacts = (props.run.supplemented_facts || []).filter((f) => f.option_id === candidate.candidate_id);
  const optFacts = opt?.facts || [];
  const merged = new Map<string, AttributeBreakdownItem>();
  const softCount = Math.max(1, activeQuestions.filter((q) => (q.role || 'soft') === 'soft').length);

  for (const q of activeQuestions) {
    const cid = q.criterion!;
    const supp = suppFacts.find((f) => f.attribute_id === cid);
    const local = optFacts.find((f) => f.criterion === cid);
    const value = supp ? supp.value : local?.value;
    const status = supp ? 'confirmed' : local?.status || 'unknown';
    if (value == null && status !== 'confirmed') continue;
    const isHard = q.role === 'hard';
    const score = isHard ? 1 : candidate.average_member_score;
    merged.set(cid, {
      attribute_id: cid,
      role: isHard ? 'hard' : 'soft',
      value,
      value_type: supp?.value_type || local?.value_type || q.mapping?.value_type || 'category',
      unit: supp?.unit ?? local?.unit ?? q.mapping?.unit ?? null,
      status,
      weight: isHard ? null : 1 / softCount,
      score,
      reason: isHard
        ? 'Meets group requirement'
        : score >= 0.75
          ? 'Strong alignment with group preferences'
          : score >= 0.45
            ? 'Partial alignment with group preferences'
            : 'Lower alignment with group preferences',
      supplemented: Boolean(supp),
    });
  }
  for (const supp of suppFacts) {
    if (merged.has(supp.attribute_id)) continue;
    merged.set(supp.attribute_id, {
      attribute_id: supp.attribute_id,
      role: hasPreferences.value ? 'soft' : 'context',
      value: supp.value,
      value_type: supp.value_type,
      unit: supp.unit,
      status: 'confirmed',
      weight: null,
      score: hasPreferences.value ? candidate.average_member_score : null,
      reason: hasPreferences.value ? 'Evaluated against group preferences' : 'Verified option attribute',
      supplemented: true,
    });
  }
  for (const local of optFacts) {
    if (merged.has(local.criterion) || local.value == null || local.value === '') continue;
    merged.set(local.criterion, {
      attribute_id: local.criterion,
      role: 'context',
      value: local.value,
      value_type: local.value_type || 'category',
      unit: local.unit,
      status: local.status || 'confirmed',
      weight: null,
      score: null,
      reason: 'Supporting option detail',
      supplemented: false,
    });
  }
  return [...merged.values()];
}

const actionMessages: Record<string, string> = {
  OPTION_FACTS_REQUIRED:
    'Some option facts remain unresolved after the evidence check. The organiser can correct them or try fresh research by revising in a new round.',
  RESPONSES_OR_CONFIRMATIONS_REQUIRED:
    'Responses or requirement confirmations are incomplete. Review the round before requesting another calculation.',
  REVISE_OPTIONS_OR_REQUIREMENTS:
    'No option meets the group requirements. Revise the choices or requirements in a new round.',
  RECOMMENDATION_IN_PROGRESS: '',
  DECISION_SETUP_REVIEW_REQUIRED: 'The organiser needs to review the decision setup.',
  RECOMMENDATION_RETRY_REQUIRED: 'The calculation failed. The organiser can retry.',
};
const nextAction = computed(() => actionMessages[props.run.recommendation_view.next_action || ''] ?? '');
function safeSource(value: string) {
  try {
    return new URL(value).protocol === 'https:';
  } catch {
    return false;
  }
}
function unavailableLabel(status: string) {
  return (
    (
      { INFEASIBLE: 'Doesn’t meet the group’s requirements', UNRESOLVED: 'Needs verified option details' } as Record<
        string,
        string
      >
    )[status.toUpperCase()] || stateLabel(status)
  );
}
function unavailableReason(candidate: { candidate_id: string; status: string }) {
  if (candidate.status.toUpperCase() === 'UNRESOLVED') {
    const missing = (props.run.fact_requests || [])
      .filter((f) => f.option_id === candidate.candidate_id)
      .map((f) => factLabel(f.attribute_id));
    if (missing.length) return `Needs verified details: ${missing.join(', ')}`;
  }
  return unavailableLabel(candidate.status);
}
function ordinal(n: number) {
  const s = ['th', 'st', 'nd', 'rd'],
    v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]!);
}
function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}
function money(row: Candidate) {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: row.currency || props.snapshot.currency,
  }).format(row.estimated_cost_minor! / 10 ** (row.currency_minor_digits ?? props.snapshot.currency_minor_digits));
}
function tradeoffs(id: string) {
  const labels: Record<string, string> = {
    HIGHER_MINIMUM_SATISFACTION: 'higher minimum fit',
    LOWER_MINIMUM_SATISFACTION: 'lower minimum fit',
    HIGHER_AVERAGE_SATISFACTION: 'higher average fit',
    LOWER_AVERAGE_SATISFACTION: 'lower average fit',
    EQUIVALENT_GROUP_METRICS: 'similar group metrics',
  };
  return props.run.recommendation_view.pareto_alternatives
    .find((row) => row.candidate_id === id)
    ?.tradeoffs?.map((code) => labels[code] || code)
    .join(', ');
}
// With a date poll, the inline form supplies the confirmed date and optional start time.
function submitConfirm(candidate: Candidate) {
  emit('confirm', candidate, { date: confirmDate.value, time: confirmTime.value || undefined });
}
watch(
  () => props.selection,
  (value) => {
    if (value) confirming.value = '';
  },
);
</script>
<style scoped>
.detail-heading {
  font-size: 1.25rem;
  display: flex;
  gap: 10px;
  align-items: baseline;
  margin-bottom: 16px;
}
.recommendation-section {
  margin: 0 0 40px;
}
.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
}
.section-heading h2 {
  font-size: 1.5rem;
  margin-bottom: 4px;
}
.section-heading p {
  color: var(--muted);
  margin: 0;
}
.pending {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 18px;
  margin-bottom: 20px;
  border-radius: 12px;
  background: var(--surface);
  border: 1px solid var(--line);
  color: var(--ink-2);
  font-size: 0.9375rem;
}
.pulse {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--blue);
  flex-shrink: 0;
  animation: pulse 1.2s ease-in-out infinite;
}
.issue-list {
  font-size: 0.9375rem;
  color: var(--muted);
}
/* Result board */
.result-board {
  border-radius: 20px;
  overflow: hidden;
  background: var(--surface);
  box-shadow: var(--shadow-md);
  margin-bottom: 28px;
  font-variant-numeric: tabular-nums;
}
.board-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 20px 24px;
  background: var(--night);
  color: #fff;
}
.board-headline {
  margin: 0;
  font-size: 1.375rem;
  font-weight: 300;
  overflow-wrap: anywhere;
}
.board-headline strong {
  font-weight: 600;
}
.board-tools {
  display: flex;
  align-items: center;
  gap: 14px;
  color: #b9cdf0;
  font-size: 0.875rem;
}
.board-replay {
  background: transparent;
  border-color: rgba(255, 255, 255, 0.3);
  color: #fff;
}
.board-replay:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  border-color: #fff;
  color: #fff;
}
.board-cols,
.board-row {
  display: grid;
  grid-template-columns: 56px minmax(0, 2fr) minmax(140px, 1.2fr) minmax(90px, 0.6fr);
  align-items: center;
  gap: 16px;
  padding: 0 24px;
}
.board-cols {
  padding-top: 12px;
  padding-bottom: 10px;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--muted);
  background: var(--surface-2);
  border-bottom: 1px solid var(--line);
}
.board-cols > span:last-child,
.board-min {
  text-align: right;
}
.board-rows {
  list-style: none;
  margin: 0;
  padding: 0;
}
.board-rows li {
  border-bottom: 1px solid var(--line);
  animation: row-in 700ms var(--ease-out) both;
  animation-delay: calc(min(var(--i), 8) * 110ms + 150ms);
}
.board-rows li:last-child {
  border-bottom: 0;
}
.board-row {
  width: 100%;
  min-height: 76px;
  border: 0;
  border-radius: 0;
  background: transparent;
  text-align: left;
  font-weight: 400;
  color: var(--ink);
}
.board-row:hover:not(:disabled) {
  background: var(--sky-50);
  color: var(--ink);
}
.board-row:active:not(:disabled) {
  transform: none;
}
.board-rank {
  font-size: 1.75rem;
  font-weight: 300;
  color: var(--muted);
}
.board-option {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}
.board-thumb {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  border-radius: 10px;
  overflow: hidden;
  display: grid;
  place-items: center;
  background: var(--sky-100);
  color: var(--blue-ink);
  font-weight: 700;
  font-size: 0.875rem;
}
.board-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.board-name {
  display: grid;
  min-width: 0;
  line-height: 1.3;
}
.board-name strong {
  font-size: 1.0625rem;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.board-name small {
  font-size: 0.875rem;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.board-fit {
  display: flex;
  align-items: center;
  gap: 12px;
}
.board-fit b {
  width: 4ch;
  text-align: right;
  font-weight: 600;
}
.board-bar {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: var(--sky-100);
  overflow: hidden;
}
.board-bar > span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--blue);
  transform-origin: left;
  transform: scaleX(var(--v));
  animation: bar-in 1200ms var(--ease-out) both;
  animation-delay: calc(min(var(--i), 8) * 110ms + 500ms);
}
.met {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ok);
  font-weight: 600;
}
.met .ui-icon {
  width: 18px;
  height: 18px;
}
.board-min {
  font-weight: 600;
  color: var(--ink-2);
}
.board-rows li.lead .board-row,
.board-rows li.chosen .board-row {
  background: var(--blue);
  color: #fff;
}
.board-rows li.lead .board-row:hover:not(:disabled),
.board-rows li.chosen .board-row:hover:not(:disabled) {
  background: var(--blue-hover);
}
:is(.lead, .chosen) .board-rank,
:is(.lead, .chosen) .board-min,
:is(.lead, .chosen) .met {
  color: #fff;
}
:is(.lead, .chosen) .board-name small {
  color: #d4e2fa;
}
:is(.lead, .chosen) .board-bar {
  background: rgba(255, 255, 255, 0.25);
}
:is(.lead, .chosen) .board-bar > span {
  background: #fff;
}
:is(.lead, .chosen) .board-thumb {
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
}
.date-poll-result {
  margin: 0 0 28px;
  padding: 22px 24px;
  border-radius: 20px;
  background: var(--surface);
  border: 1px solid var(--line);
}
.date-poll-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.date-poll-head h3 {
  margin: 0;
}
.date-poll-head p {
  margin: 0;
  color: var(--muted);
  font-size: 0.9375rem;
}
.date-rows {
  list-style: none;
  margin: 0;
  padding: 0;
}
.date-rows li {
  display: grid;
  grid-template-columns: minmax(130px, 180px) minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  padding: 10px 12px;
  border-radius: 12px;
  animation: rise 420ms var(--ease-out) both;
  animation-delay: calc(min(var(--i), 8) * 50ms);
}
.date-rows li.best {
  background: var(--sky-50);
}
.date-rows li.chosen {
  background: var(--sky-100);
}
.date-label {
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}
.date-tag {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--blue-ink);
}
.date-bar {
  display: flex;
  height: 8px;
  border-radius: 4px;
  overflow: hidden;
  background: var(--sky-100);
}
.date-bar > span {
  width: calc(var(--w) * 100%);
  transform-origin: left;
  animation: meter-fill 900ms var(--ease-out) both;
}
.date-bar .works {
  background: #1f9d5c;
}
.date-bar .maybe {
  background: #e2a93b;
}
.date-bar .cannot {
  background: #c4515f;
}
.date-counts {
  font-size: 0.875rem;
  color: var(--muted);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.confirm-when {
  margin-top: 8px;
  padding: 16px;
  border-radius: 14px;
  background: var(--sky-50);
  border: 1px solid var(--line);
}
.confirm-when-title {
  font-weight: 600;
  margin: 0 0 4px;
}
.confirm-when-fields {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
  gap: 0 12px;
}
.confirm-when-fields label {
  margin: 10px 0 0;
}
.confirm-when-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
}
.supplemented-facts {
  overflow-wrap: anywhere;
  margin: 0 0 28px;
}
.supplement {
  padding: 12px 0;
  border-top: 1px solid var(--line);
}
.detail-heading {
  margin-top: 8px;
}
.candidate-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
  container-type: inline-size;
}
.candidate-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: 20px;
  overflow: hidden;
  overflow-wrap: anywhere;
  scroll-margin-top: 24px;
  transition:
    box-shadow var(--base) var(--ease-out),
    border-color var(--base) var(--ease-out);
}
.candidate-card.has-attributes {
  grid-template-columns: minmax(280px, 380px) minmax(0, 1fr);
}
.candidate-card:not(.has-attributes) .candidate-overview:has(.candidate-photo-strip) {
  display: grid;
  grid-template-columns: minmax(200px, 300px) minmax(0, 1fr);
}
.candidate-card:not(.has-attributes) .candidate-photo-strip {
  height: 100%;
  min-height: 200px;
}
.candidate-card.recommended {
  border-color: var(--sky-300);
}
.candidate-card.chosen {
  border-color: var(--blue);
  box-shadow: 0 0 0 1px var(--blue);
}
.candidate-card.spotlighted {
  box-shadow:
    0 0 0 3px var(--sky-200),
    var(--shadow-md);
  border-color: var(--blue);
}
.candidate-overview {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.candidate-card.has-attributes .candidate-overview {
  border-right: 1px solid var(--line);
}
.candidate-photo-strip {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 2px;
  height: 168px;
  background: var(--sky-100);
}
.candidate-photo-strip:has(figure:only-child) {
  grid-template-columns: 1fr;
}
.candidate-photo-strip figure {
  position: relative;
  margin: 0;
  overflow: hidden;
  background: var(--sky-100);
}
.candidate-photo-strip img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  opacity: 0;
  transform: scale(1.03);
  transition:
    opacity 500ms var(--ease-out),
    transform 900ms var(--ease-out);
}
.candidate-photo-strip img.ready {
  opacity: 1;
  transform: none;
}
.photo-placeholder {
  position: absolute;
  inset: 0;
  background: var(--sky-100);
  animation: pulse 1.6s ease-in-out infinite;
}
.candidate-photo-strip figcaption {
  position: absolute;
  left: 8px;
  bottom: 8px;
  max-width: calc(100% - 16px);
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 0.6875rem;
  color: #fff;
  background: rgba(10, 33, 80, 0.72);
}
.candidate-photo-strip figcaption a {
  color: #fff;
}
.candidate-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  padding: 22px 24px 24px;
  min-width: 0;
}
.rank {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--muted);
  margin: 0 0 6px;
}
.rank-num {
  display: grid;
  place-items: center;
  min-width: 28px;
  height: 28px;
  padding: 0 6px;
  border-radius: 8px;
  background: var(--sky-100);
  color: var(--blue-ink);
  font-variant-numeric: tabular-nums;
}
.recommended .rank {
  color: var(--blue-ink);
}
.recommended .rank-num,
.chosen .rank-num {
  background: var(--blue);
  color: #fff;
}
.candidate-card h3 {
  font-size: 1.375rem;
  margin-bottom: 4px;
}
.candidate-meta {
  font-size: 0.9375rem;
  color: var(--muted);
  margin: 0 0 2px;
  overflow-wrap: anywhere;
}
.candidate-meta.address {
  margin-bottom: 8px;
}
.candidate-description {
  font-size: 0.9375rem;
  color: var(--ink-2);
  margin: 6px 0 10px;
  overflow-wrap: anywhere;
}
.candidate-highlights {
  margin: 0 0 14px;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  font-size: 0.875rem;
  color: var(--ink-2);
}
.candidate-highlights li {
  display: flex;
  align-items: center;
  gap: 8px;
}
.candidate-highlights li::before {
  content: '';
  width: 5px;
  height: 5px;
  border-radius: 1px;
  background: var(--blue);
}
.tie {
  font-size: 0.875rem;
  color: var(--muted);
  margin-bottom: 10px;
}
.no-pref-note {
  font-size: 0.9375rem;
  color: var(--ok);
  margin-bottom: 14px;
}
.scores {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin: 8px 0 16px;
}
.scores > div {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: baseline;
  gap: 6px 8px;
}
.scores dt {
  font-size: 0.8125rem;
  color: var(--muted);
  font-weight: 600;
}
.scores dd {
  margin: 0;
  font-size: 1.375rem;
  font-weight: 300;
  font-variant-numeric: tabular-nums;
  color: var(--night);
}
.scores .meter {
  grid-column: 1 / -1;
}
.attr-breakdown {
  display: flex;
  flex-direction: column;
  padding: 22px 24px;
  min-width: 0;
  background: var(--surface-2);
}
.attr-breakdown-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 14px;
}
.attr-breakdown-head h4 {
  font-size: 1rem;
  margin: 0;
}
.attr-breakdown-head span {
  font-size: 0.875rem;
  color: var(--muted);
}
.attr-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 12px;
  align-content: start;
}
.attr-item {
  display: flex;
  flex-direction: column;
  padding: 14px 16px;
  border-radius: 14px;
  background: var(--surface);
  border: 1px solid var(--line);
  animation: rise var(--slow) var(--ease-out) both;
  animation-delay: calc(min(var(--ai, 0), 6) * 60ms);
}
.attr-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.attr-name {
  font-size: 0.9375rem;
}
.attr-score {
  font-size: 0.875rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.attr-score.fit-high {
  color: var(--ok);
}
.attr-score.fit-mid {
  color: var(--warn);
}
.attr-score.fit-low {
  color: var(--danger);
}
.attr-score.fit-neutral {
  color: var(--muted);
}
.attr-role {
  font-size: 0.8125rem;
  color: var(--muted);
  margin: 2px 0 8px;
}
.attr-value {
  font-size: 0.9375rem;
  font-weight: 600;
  margin: 0 0 10px;
}
.attr-meter {
  height: 5px;
  margin-bottom: 8px;
  margin-top: auto;
}
.attr-meter > span.fit-high {
  background: #1f9d5c;
}
.attr-meter > span.fit-mid {
  background: #d98a00;
}
.attr-meter > span.fit-low {
  background: var(--danger);
}
.attr-reason {
  font-size: 0.8125rem;
  color: var(--muted);
  margin: 0;
}
.facts {
  display: grid;
  gap: 8px;
  margin: 0 0 14px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  font-size: 0.9375rem;
}
.facts > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.facts dt {
  color: var(--muted);
}
.facts dd {
  margin: 0;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  text-align: right;
}
.tradeoff {
  font-size: 0.875rem;
  color: var(--muted);
  margin-bottom: 12px;
}
.candidate-body > button {
  margin-top: auto;
  align-self: flex-start;
}
.unavailable {
  margin-top: 28px;
}
.unavailable h3 {
  font-size: 1rem;
  color: var(--ink-2);
  margin-bottom: 10px;
}
.unavailable ul {
  list-style: none;
  padding: 0;
  margin: 0;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--surface);
}
.unavailable li {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 14px 18px;
  font-size: 0.9375rem;
}
.unavailable li + li {
  border-top: 1px solid var(--line);
}
.unavailable li > span:first-child {
  text-decoration: line-through;
  text-decoration-color: var(--faint);
}
@keyframes row-in {
  from {
    opacity: 0;
    transform: translateY(16px);
    clip-path: inset(0 0 100% 0);
  }
  to {
    clip-path: inset(0 0 0 0);
  }
}
@keyframes bar-in {
  from {
    transform: scaleX(0);
  }
}
@container (max-width: 760px) {
  .candidate-card.has-attributes,
  .candidate-card:not(.has-attributes) .candidate-overview:has(.candidate-photo-strip) {
    grid-template-columns: minmax(0, 1fr);
  }
  .candidate-card.has-attributes .candidate-overview {
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }
  .candidate-card:not(.has-attributes) .candidate-photo-strip {
    min-height: 0;
    height: 168px;
  }
}
@media (max-width: 760px) {
  .board-head {
    padding: 16px 18px;
  }
  .board-cols {
    display: none;
  }
  .board-row {
    grid-template-columns: 28px minmax(0, 1fr) auto;
    grid-template-areas: 'rank opt min' 'rank fit fit';
    gap: 8px 12px;
    padding: 14px 18px;
  }
  .board-rank {
    grid-area: rank;
    font-size: 1.375rem;
  }
  .board-option {
    grid-area: opt;
  }
  .board-fit {
    grid-area: fit;
  }
  .board-min {
    grid-area: min;
    font-size: 0.875rem;
  }
  .board-thumb {
    display: none;
  }
  .candidate-body,
  .attr-breakdown {
    padding: 18px;
  }
  .scores {
    grid-template-columns: minmax(0, 1fr);
  }
  .date-rows li {
    grid-template-columns: minmax(0, 1fr);
    gap: 6px;
  }
  .confirm-when-fields {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
