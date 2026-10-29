<template>
  <section class="panel recheck-panel" aria-labelledby="recheck-heading">
    <h2 id="recheck-heading">Still accurate?</h2>
    <p class="aside-lede">
      Before you confirm, check the top {{ Math.min(3, candidates.length) }} options against current sources{{
        planDates ? ` for ${planDates}` : ''
      }}: prices, details and whether they’re open.
    </p>
    <button type="button" :disabled="recheck.state === 'loading'" @click="recheckFacts">
      <UiIcon name="refresh" :class="{ spinning: recheck.state === 'loading' }" />{{
        recheck.state === 'loading'
          ? 'Checking sources…'
          : recheck.state === 'done'
            ? 'Check again'
            : 'Check top options'
      }}
    </button>
    <p v-if="recheck.message" class="helper-text" role="status">{{ recheck.message }}</p>
    <Transition name="reveal">
      <div v-if="recheck.state === 'done'" class="recheck-results">
        <p class="recheck-summary">{{ recheckSummary }}</p>
        <ul>
          <li v-for="row in recheck.rows" :key="`${row.option}:${row.criterion}`" :class="['recheck-row', row.status]">
            <div class="recheck-top">
              <strong>{{ row.title }}</strong
              ><span class="recheck-status">{{ recheckStatusLabels[row.status] }}</span>
            </div>
            <p>
              {{ factLabel(row.criterion) }}:
              <template v-if="row.status === 'changed'"
                ><s>{{ row.before }}</s> → </template
              >{{ row.status === 'unconfirmed' ? row.before || 'No current source' : row.after }}
            </p>
            <a v-if="row.source" :href="row.source.url" target="_blank" rel="noopener noreferrer">{{
              row.source.title || 'Source'
            }}</a>
          </li>
        </ul>
        <p class="helper-text">
          This check is advisory. It doesn’t change the ranking. If something important changed, revise in a new round.
        </p>
      </div>
    </Transition>
  </section>
</template>
<script setup lang="ts">
import { reactive, computed } from 'vue';
import UiIcon from './UiIcon.vue';
import { apiService, ApiError } from '@/services/api';
import { factLabel, factValue } from '@/services/facts';
import type { Candidate, PublishedFact, Snapshot } from '@/types/form';

// Before confirming, the organiser can re-check the top options against current sources.
// The check is advisory: it never changes the round or its ranking.
const props = defineProps<{ roundId: string; snapshot: Snapshot; candidates: Candidate[]; planDates: string }>();
type RecheckRow = {
  option: string;
  title: string;
  criterion: string;
  before: string;
  after: string;
  status: 'same' | 'changed' | 'unconfirmed' | 'new';
  source?: { url: string; title?: string };
};
const recheckStatusLabels: Record<string, string> = {
  same: 'Unchanged',
  changed: 'Changed',
  unconfirmed: 'Couldn’t confirm',
  new: 'Found',
};
const recheck = reactive<{ state: 'idle' | 'loading' | 'done' | 'failed'; rows: RecheckRow[]; message: string }>({
  state: 'idle',
  rows: [],
  message: '',
});
const recheckSummary = computed(() => {
  const changed = recheck.rows.filter((r) => r.status === 'changed').length,
    unknown = recheck.rows.filter((r) => r.status === 'unconfirmed').length;
  return changed
    ? `${changed} ${changed === 1 ? 'detail has' : 'details have'} changed since you published.`
    : unknown
      ? `Nothing changed, but ${unknown} ${unknown === 1 ? 'detail' : 'details'} couldn’t be confirmed.`
      : 'Everything checked still matches what you published.';
});
function optionOf(id: string) {
  return props.snapshot.options.find((o) => o.option_id === id);
}
async function recheckFacts() {
  recheck.state = 'loading';
  recheck.message = '';
  recheck.rows = [];
  const top = props.candidates.slice(0, 3);
  const published = new Map<string, PublishedFact>();
  for (const c of top)
    for (const f of optionOf(c.candidate_id)?.facts || [])
      if (f.criterion !== 'option_rating') published.set(`${c.candidate_id}:${f.criterion}`, f);
  const definitions = new Map<string, { criterion: string; value_type: string; unit: string | null }>();
  for (const f of published.values())
    if (!definitions.has(f.criterion) && definitions.size < 7)
      definitions.set(f.criterion, {
        criterion: f.criterion,
        value_type: f.value_type || 'category',
        unit: f.unit || null,
      });
  definitions.set('open_on_plan_dates', { criterion: 'open_on_plan_dates', value_type: 'boolean', unit: null });
  try {
    const result = await apiService.research<{
      facts: {
        option: string;
        criterion: string;
        value: unknown;
        value_type?: string;
        unit?: string | null;
        sources: { url: string; title?: string }[];
      }[];
    }>(props.roundId, 'facts', {
      decision_question: props.snapshot.decision_question,
      currency: props.snapshot.currency,
      options: top.map((c) => ({
        key: c.candidate_id,
        title: c.title,
        source_url: optionOf(c.candidate_id)?.identity?.source_url || '',
      })),
      attributes: [...definitions.values()],
      correction: `Re-check with current sources${props.planDates ? ` for ${props.planDates}` : ''}: current prices and details, and whether each option is open and operating then.`,
    });
    const currency = props.snapshot.currency;
    const show = (f: { criterion: string; value: unknown; value_type?: string; unit?: string | null }) =>
      factValue({ criterion: f.criterion, value: f.value, value_type: f.value_type, unit: f.unit ?? null }, currency);
    const found = new Map(result.facts.map((f) => [`${f.option}:${f.criterion}`, f]));
    const rows: RecheckRow[] = [];
    for (const c of top)
      for (const d of definitions.values()) {
        const before = published.get(`${c.candidate_id}:${d.criterion}`),
          after = found.get(`${c.candidate_id}:${d.criterion}`);
        const base = {
          option: c.candidate_id,
          title: c.title,
          criterion: d.criterion,
          before: before ? show(before) : '',
          after: after ? show(after) : '',
          source: after?.sources?.[0],
        };
        if (!after) {
          if (before || d.criterion === 'open_on_plan_dates') rows.push({ ...base, status: 'unconfirmed' });
          continue;
        }
        if (d.criterion === 'open_on_plan_dates') {
          rows.push({
            ...base,
            status: after.value === false ? 'changed' : 'same',
            before: after.value === false ? 'Open' : '',
            after: after.value === false ? 'May be closed then' : 'Open then',
          });
          continue;
        }
        rows.push({
          ...base,
          status: !before
            ? 'new'
            : base.before.toLocaleLowerCase() === base.after.toLocaleLowerCase()
              ? 'same'
              : 'changed',
        });
      }
    const order = { changed: 0, unconfirmed: 1, new: 2, same: 3 };
    recheck.rows = rows.sort((a, b) => order[a.status] - order[b.status]);
    recheck.state = 'done';
  } catch (e) {
    recheck.state = 'failed';
    recheck.message =
      e instanceof ApiError && e.code === 'FACT_COLLECTOR_NOT_CONFIGURED'
        ? 'Source checks need AI research to be set up on this server.'
        : 'Sources couldn’t be checked right now. Try again in a moment.';
  }
}
</script>
<style scoped>
/* Shared with the other aside panels in RoundWorkspace. */
h2 {
  font-size: 1.25rem;
  margin-bottom: 6px;
}
.aside-lede {
  color: var(--muted);
  font-size: 0.9375rem;
}
.recheck-panel button .spinning {
  animation: spin 900ms linear infinite;
}
.recheck-results {
  margin-top: 16px;
}
.recheck-summary {
  font-weight: 600;
  font-size: 0.9375rem;
}
.recheck-results ul {
  list-style: none;
  margin: 0 0 12px;
  padding: 0;
}
.recheck-row {
  padding: 10px 0;
  border-top: 1px solid var(--line);
  font-size: 0.875rem;
}
.recheck-row p {
  margin: 2px 0;
  color: var(--ink-2);
  overflow-wrap: anywhere;
}
.recheck-row a {
  font-size: 0.8125rem;
}
.recheck-top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
.recheck-status {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--muted);
  white-space: nowrap;
}
.recheck-row.changed .recheck-status {
  color: var(--warn);
}
.recheck-row.unconfirmed .recheck-status {
  color: var(--muted);
}
.recheck-row.same .recheck-status {
  color: var(--ok);
}
</style>
