<template>
  <figure ref="root" class="board" :class="`phase-${phase}`" aria-label="Example: a group decision being ranked">
    <div class="board-head">
      <div class="board-title">
        <Transition name="board-swap" mode="out-in"
          ><strong :key="scenario.title">{{ scenario.title }}</strong></Transition
        >
        <Transition name="board-swap" mode="out-in"
          ><span :key="scenario.question">{{ scenario.question }}</span></Transition
        >
      </div>
      <div class="board-count" aria-hidden="true">
        <span class="dots"
          ><span v-for="n in scenario.members" :key="`${scenario.title}-${n}`" :class="{ on: n <= responded }"></span
        ></span>
        <span class="count-text"
          ><b>{{ responded }}</b> of {{ scenario.members }} answered</span
        >
      </div>
    </div>
    <div class="board-cols" aria-hidden="true">
      <span>Rank</span><span>Option</span><span>Group fit</span><span>Status</span>
    </div>
    <TransitionGroup tag="ol" name="board-row" class="board-rows" aria-hidden="true">
      <li
        v-for="(row, index) in ordered"
        :key="row.id"
        :class="{ lead: phase >= 3 && index === 0, out: row.out && phase >= 2, dim: phase >= 3 && index > 0 }"
        :style="{ '--i': index }"
      >
        <span class="rank"
          ><Transition name="board-swap" mode="out-in"
            ><span :key="rankLabel(row, index)">{{ rankLabel(row, index) }}</span></Transition
          ></span
        >
        <span class="opt"
          ><strong>{{ row.name }}</strong
          ><small>{{ row.meta }}</small></span
        >
        <span class="fit"
          ><span class="bar"><span :style="{ '--v': phase >= 2 && !row.out ? row.fit : 0 }"></span></span
          ><span class="pct">{{ row.out && phase >= 2 ? '—' : `${Math.round(row.fit * 100 * tween)}%` }}</span></span
        >
        <span class="status">
          <Transition name="board-swap" mode="out-in">
            <span :key="statusLabel(row, index)" :class="['status-text', statusClass(row, index)]">
              <svg v-if="statusClass(row, index) === 'is-confirmed'" viewBox="0 0 24 24" class="tick">
                <path d="m5 12.5 4.5 4.5L19 7.5" /></svg
              >{{ statusLabel(row, index) }}
            </span>
          </Transition>
        </span>
      </li>
    </TransitionGroup>
    <figcaption class="board-foot">
      <span>Example decision</span
      ><Transition name="board-swap" mode="out-in"
        ><span :key="footNote">{{ footNote }}</span></Transition
      >
    </figcaption>
  </figure>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
type Row = { id: string; name: string; meta: string; fit: number; out?: boolean; reason?: string };
type Scenario = { title: string; question: string; members: number; rule: string; rows: Row[] };
const scenarios: Scenario[] = [
  {
    title: 'Saturday dinner',
    question: 'Where should we eat?',
    members: 6,
    rule: 'Requirement: under $60 per person',
    rows: [
      { id: 'a1', name: 'Garden picnic', meta: 'Outdoor · $', fit: 0.74 },
      { id: 'a2', name: 'Rooftop bar', meta: 'Drinks · $$$', fit: 0.81, out: true, reason: 'Over budget' },
      { id: 'a3', name: 'Ramen counter', meta: 'Japanese · $$', fit: 0.88 },
      { id: 'a4', name: 'Hawker food walk', meta: 'Walking · $', fit: 0.69 },
    ],
  },
  {
    title: 'Q3 team offsite',
    question: 'Which venue suits the team?',
    members: 9,
    rule: 'Requirement: step-free access',
    rows: [
      { id: 'b1', name: 'Co-working floor', meta: 'Central · Quiet rooms', fit: 0.71 },
      { id: 'b2', name: 'Harbourfront loft', meta: 'Waterfront · Catering', fit: 0.9 },
      { id: 'b3', name: 'Pottery studio', meta: 'Hands-on · 3 hours', fit: 0.77, out: true, reason: 'Not accessible' },
      { id: 'b4', name: 'Beach club day', meta: 'Outdoor · Full day', fit: 0.64 },
    ],
  },
];
const root = ref<HTMLElement>();
const which = ref(0);
const phase = ref(0);
const responded = ref(0);
const sorted = ref(false);
const tween = ref(0);
const scenario = computed(() => scenarios[which.value]!);
const ordered = computed(() =>
  sorted.value
    ? [...scenario.value.rows].sort((a, b) => Number(!!a.out) - Number(!!b.out) || b.fit - a.fit)
    : scenario.value.rows,
);
const footNote = computed(() => (phase.value >= 2 ? scenario.value.rule : 'Answers stay private to each member'));
function rankLabel(row: Row, index: number) {
  return !sorted.value || row.out ? '–' : String(index + 1);
}
function statusLabel(row: Row, index: number) {
  if (row.out && phase.value >= 2) return row.reason || 'Ruled out';
  if (phase.value >= 3 && index === 0) return 'Confirmed';
  if (phase.value >= 2) return sorted.value && index === 0 ? 'Recommended' : 'Ranked';
  return 'Collecting';
}
function statusClass(row: Row, index: number) {
  if (row.out && phase.value >= 2) return 'is-out';
  if (phase.value >= 3 && index === 0) return 'is-confirmed';
  if (phase.value >= 2 && sorted.value && index === 0) return 'is-lead';
  return '';
}

// One authored sequence: collect → rank → confirm, then the next scenario.
let timers: ReturnType<typeof setTimeout>[] = [];
let frame = 0;
let running = false;
let visible = true;
const reduce = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
function at(ms: number, fn: () => void) {
  timers.push(setTimeout(fn, ms));
}
function clear() {
  timers.forEach(clearTimeout);
  timers = [];
  cancelAnimationFrame(frame);
}
function count(duration: number) {
  const start = performance.now();
  const step = (now: number) => {
    const t = Math.min(1, (now - start) / duration);
    tween.value = 1 - Math.pow(1 - t, 4);
    if (t < 1) frame = requestAnimationFrame(step);
  };
  frame = requestAnimationFrame(step);
}
function finalState() {
  phase.value = 3;
  responded.value = scenario.value.members;
  sorted.value = true;
  tween.value = 1;
}
function play() {
  clear();
  running = true;
  phase.value = 0;
  responded.value = 0;
  sorted.value = false;
  tween.value = 0;
  const members = scenario.value.members;
  at(900, () => {
    phase.value = 1;
    for (let n = 1; n <= members; n++)
      at(n * 190, () => {
        responded.value = n;
      });
  });
  const ranked = 900 + members * 190 + 500;
  at(ranked, () => {
    phase.value = 2;
    count(1100);
  });
  at(ranked + 1300, () => {
    sorted.value = true;
  });
  at(ranked + 2400, () => {
    phase.value = 3;
  });
  at(ranked + 6200, () => {
    phase.value = 4;
  });
  at(ranked + 6700, () => {
    which.value = (which.value + 1) % scenarios.length;
    if (visible && !document.hidden) play();
    else running = false;
  });
}
function resume() {
  if (!running && visible && !document.hidden && !reduce) play();
}
let observer: IntersectionObserver | undefined;
function onVisibility() {
  if (document.hidden) {
    clear();
    running = false;
  } else resume();
}
onMounted(() => {
  if (reduce) {
    finalState();
    return;
  }
  observer = new IntersectionObserver(
    ([entry]) => {
      visible = !!entry?.isIntersecting;
      if (!visible) {
        clear();
        running = false;
      } else resume();
    },
    { threshold: 0.2 },
  );
  if (root.value) observer.observe(root.value);
  document.addEventListener('visibilitychange', onVisibility);
});
onBeforeUnmount(() => {
  clear();
  observer?.disconnect();
  document.removeEventListener('visibilitychange', onVisibility);
});
</script>
<style scoped>
.board {
  margin: 0;
  width: 100%;
  background: var(--surface);
  border-radius: 20px;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
  transition:
    opacity 400ms var(--ease-out),
    transform 400ms var(--ease-out);
}
.board.phase-4 {
  opacity: 0;
  transform: translateY(6px);
}
.board-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 22px 26px 18px;
  background: var(--night);
  color: #fff;
}
.board-title {
  display: grid;
  min-width: 0;
}
.board-title strong {
  font-size: 1.375rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: 1.2;
}
.board-title span {
  color: #b9cdf0;
  font-size: 0.9375rem;
}
.board-count {
  display: grid;
  justify-items: end;
  gap: 6px;
  flex-shrink: 0;
}
.dots {
  display: flex;
  gap: 5px;
}
.dots span {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.16);
  transition:
    background-color 240ms ease-out,
    transform 360ms var(--ease-out);
}
.dots span.on {
  background: #6fa2ff;
  transform: scale(1.15);
}
.count-text {
  font-size: 0.8125rem;
  color: #b9cdf0;
}
.count-text b {
  color: #fff;
  font-weight: 700;
}

.board-cols,
.board-rows li {
  display: grid;
  grid-template-columns: 52px minmax(0, 1.6fr) minmax(0, 1.2fr) minmax(112px, 0.9fr);
  align-items: center;
  gap: 16px;
  padding: 0 26px;
}
.board-cols {
  padding-top: 12px;
  padding-bottom: 10px;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--muted);
  border-bottom: 1px solid var(--line);
  background: var(--surface-2);
}
.board-rows {
  list-style: none;
  margin: 0;
  padding: 0;
  position: relative;
}
.board-rows li {
  min-height: 74px;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
  transition:
    background-color 500ms var(--ease-out),
    color 500ms var(--ease-out),
    opacity 500ms var(--ease-out);
}
.board-rows li:last-child {
  border-bottom: 0;
}
.board-rows li.lead {
  background: var(--blue);
  color: #fff;
}
.board-rows li.dim {
  opacity: 0.62;
}
.board-rows li.out .opt strong {
  text-decoration: line-through;
  text-decoration-color: var(--faint);
}
.rank {
  font-size: 1.5rem;
  font-weight: 300;
  color: var(--muted);
}
.lead .rank {
  color: #fff;
  font-weight: 400;
}
.opt {
  display: grid;
  min-width: 0;
  line-height: 1.3;
}
.opt strong {
  font-size: 1.0625rem;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.opt small {
  font-size: 0.8125rem;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color 500ms ease-out;
}
.lead .opt small {
  color: #d4e2fa;
}
.fit {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.bar {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: var(--sky-100);
  overflow: hidden;
  transition: background-color 500ms ease-out;
}
.bar > span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--blue);
  transform-origin: left;
  transform: scaleX(var(--v));
  transition:
    transform 1100ms var(--ease-out),
    background-color 500ms ease-out;
}
.lead .bar {
  background: rgba(255, 255, 255, 0.25);
}
.lead .bar > span {
  background: #fff;
}
.pct {
  width: 3.2ch;
  text-align: right;
  font-size: 0.9375rem;
  font-weight: 600;
}
.status {
  font-size: 0.875rem;
  font-weight: 600;
  overflow: hidden;
}
.status-text {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  white-space: nowrap;
}
.status-text::before {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 2px;
  background: currentColor;
  opacity: 0.8;
}
.status-text.is-lead {
  color: var(--blue-ink);
}
.status-text.is-out {
  color: var(--danger);
}
.status-text.is-confirmed {
  color: #fff;
}
.status-text.is-confirmed::before {
  display: none;
}
.tick {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.6;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 22;
  animation: tick 600ms 120ms var(--ease-out) both;
}
@keyframes tick {
  from {
    stroke-dashoffset: 22;
  }
}
.board-foot {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 26px;
  font-size: 0.8125rem;
  color: var(--muted);
  border-top: 1px solid var(--line);
  background: var(--surface-2);
}
.board-foot > span:first-child {
  font-weight: 600;
  color: var(--ink-2);
}

/* Rows enter one by one, then travel to their ranked position. */
.phase-0 .board-rows li {
  animation: row-in 640ms var(--ease-out) both;
  animation-delay: calc(var(--i) * 90ms + 120ms);
}
@keyframes row-in {
  from {
    opacity: 0;
    transform: translateY(14px);
    clip-path: inset(0 0 100% 0);
  }
  to {
    clip-path: inset(0 0 0 0);
  }
}
.board-row-move {
  transition: transform 900ms cubic-bezier(0.65, 0, 0.35, 1);
}
.board-swap-enter-active {
  transition:
    opacity 260ms var(--ease-out),
    transform 260ms var(--ease-out);
}
.board-swap-leave-active {
  transition:
    opacity 140ms ease-in,
    transform 140ms ease-in;
}
.board-swap-enter-from {
  opacity: 0;
  transform: translateY(60%);
}
.board-swap-leave-to {
  opacity: 0;
  transform: translateY(-60%);
}

@media (max-width: 640px) {
  .board-head {
    flex-direction: column;
    align-items: flex-start;
    padding: 18px 18px 16px;
  }
  .board-count {
    justify-items: start;
  }
  .board-cols {
    display: none;
  }
  .board-rows li {
    grid-template-columns: 30px minmax(0, 1fr) auto;
    grid-template-areas: 'rank opt status' 'rank fit fit';
    gap: 6px 12px;
    padding: 12px 18px;
    min-height: 0;
  }
  .rank {
    grid-area: rank;
    font-size: 1.25rem;
  }
  .opt {
    grid-area: opt;
  }
  .fit {
    grid-area: fit;
  }
  .status {
    grid-area: status;
    font-size: 0.8125rem;
  }
  .board-foot {
    flex-direction: column;
    gap: 2px;
    padding: 12px 18px;
  }
}
</style>
