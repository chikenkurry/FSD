<template>
  <article :class="['overview-card', { compact, chosen }]">
    <div v-if="photos.length" class="photo-strip">
      <figure v-for="(photo, i) in photos" :key="photo.name" :class="{ lead: i === 0 }">
        <img
          v-if="urls[photo.name]"
          :src="urls[photo.name]"
          :alt="i === 0 ? `${title}` : ''"
          loading="lazy"
          @load="loaded.add(photo.name)"
          :class="{ ready: loaded.has(photo.name) }"
        />
        <span v-else class="photo-placeholder" aria-hidden="true"></span>
        <figcaption v-if="photo.attributions.length && i === 0">
          Photo:
          <template v-for="(a, ai) in photo.attributions" :key="ai"
            ><a v-if="a.uri" :href="a.uri" target="_blank" rel="noopener noreferrer">{{ a.name }}</a
            ><span v-else>{{ a.name }}</span></template
          >
        </figcaption>
      </figure>
    </div>
    <div class="body">
      <div v-if="position || kindLabel" class="eyebrow">
        <span v-if="position" class="position" aria-hidden="true">{{ position }}</span>
        <span v-if="kindLabel" class="kind">{{ kindLabel }}</span>
      </div>
      <h3>
        <span class="name">{{ heading.name }}</span
        ><template v-if="heading.detail"
          ><span class="sr-only"> – </span><span class="detail">{{ heading.detail }}</span></template
        >
      </h3>
      <p v-if="data?.rating || details.length" class="meta">
        <span v-if="data?.rating" class="rating"
          ><span class="star" aria-hidden="true">★</span><strong>{{ data.rating.toFixed(1) }}</strong
          ><span class="sr-only"> stars</span
          ><span v-if="data.rating_count" class="count">({{ data.rating_count.toLocaleString() }})</span></span
        >
        <span v-for="part in details" :key="part" class="detail-part">{{ part }}</span>
      </p>
      <p v-if="facts2" class="address"><UiIcon name="pin" />{{ facts2 }}</p>
      <div v-if="loading" class="loading" aria-hidden="true">
        <span class="skeleton line"></span><span class="skeleton line"></span><span class="skeleton line short"></span>
      </div>
      <template v-else-if="summary || data">
        <p v-if="data?.tagline" class="tagline">{{ data.tagline }}</p>
        <p v-if="summary" class="summary">{{ summary }}</p>
        <ul v-if="highlights.length" class="highlights">
          <li v-for="h in highlights" :key="h">{{ h }}</li>
        </ul>
        <details v-if="data?.review_summary" class="reviews">
          <summary>What reviewers say</summary>
          <p>{{ data.review_summary }}</p>
          <p v-if="data.review_disclosure" class="disclosure">{{ data.review_disclosure }}</p>
        </details>
        <p
          v-if="data?.maps_url || source === 'organiser' || source === 'ai_general' || sources.length"
          class="provenance"
        >
          <a v-if="data?.maps_url" class="maps-link" :href="data.maps_url" target="_blank" rel="noopener noreferrer"
            >View on Google Maps<UiIcon name="external"
          /></a>
          <span v-if="source === 'organiser'">Overview corrected by the organiser.</span>
          <span v-else-if="source === 'ai_general'">General description by AI, not about a specific venue.</span>
          <span v-else-if="sources.length"
            >Summary from
            <template v-for="(s, si) in sources" :key="s.url"
              ><a :href="s.url" target="_blank" rel="noopener noreferrer">{{ s.title || 'the web' }}</a
              ><template v-if="si < sources.length - 1">, </template></template
            ></span
          >
        </p>
      </template>
      <p v-else-if="!facts?.length" class="summary muted">No overview yet.</p>
      <dl v-if="facts?.length" class="facts">
        <div v-for="fact in facts" :key="fact.criterion">
          <dt>{{ factLabel(fact.criterion) }}</dt>
          <dd>{{ factValue(fact, currency) }}</dd>
        </div>
      </dl>
      <slot />
    </div>
  </article>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue';
import type { Brief, Overview, OptionKind, PublishedFact } from '@/types/form';
import { factLabel, factValue } from '@/services/facts';
import { apiService } from '@/services/api';
import { splitTitle } from '@/services/labels';
import UiIcon from './UiIcon.vue';

const props = withDefaults(
  defineProps<{
    title: string;
    overview?: Overview | null;
    kind?: OptionKind;
    roundId?: string;
    placeId?: string;
    description?: string;
    brief?: Brief;
    facts?: PublishedFact[];
    currency?: string;
    position?: number;
    loading?: boolean;
    compact?: boolean;
    chosen?: boolean;
    photoKey?: number;
  }>(),
  { currency: 'SGD', compact: false, chosen: false, loading: false },
);

// Place cards are fetched live by place ID; Google’s terms don’t allow storing their content.
const live = ref<Overview>();
const data = computed(() => live.value || (props.overview?.source === 'google_places' ? props.overview : undefined));
watch(
  () => [props.roundId, props.placeId] as const,
  async ([roundId, placeId]) => {
    if (!roundId || !placeId || props.overview?.source === 'google_places') return;
    live.value = undefined;
    try {
      live.value = await apiService.placeCard(roundId, placeId);
    } catch {
      /* fall back to stored description */
    }
  },
  { immediate: true },
);

const kindLabel = computed(
  () =>
    (
      ({ place: 'Place', destination: 'Destination', event: 'Event', activity: 'Activity', other: '' }) as Record<
        string,
        string
      >
    )[props.kind || 'other'],
);
// Live Places details (rating, address, photos) combine with the stored web/AI brief.
const brief = computed(
  () => props.brief || (props.overview && props.overview.source !== 'google_places' ? props.overview : undefined),
);
const summary = computed(
  () => brief.value?.summary || data.value?.summary || props.description || data.value?.review_summary || '',
);
const highlights = computed(() =>
  (brief.value?.highlights?.length ? brief.value.highlights : data.value?.highlights || []).slice(
    0,
    props.compact ? 3 : 4,
  ),
);
const source = computed(() => brief.value?.source || data.value?.source);
// Sources are de-duplicated by site name, so one site cited three times reads once.
const sources = computed(() => {
  const list = brief.value?.sources?.length ? brief.value.sources : data.value?.sources || [];
  const seen = new Set<string>();
  return list
    .filter((s) => {
      const key = (s.title || s.url).toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 2);
});
const heading = computed(() => splitTitle(props.title));
// The rating is shown on its own; the rest of the live details follow it.
const details = computed(() => {
  const d = data.value;
  const parts: string[] = [];
  if (d?.price_level != null) parts.push(d.price_level === 0 ? 'Free' : '$'.repeat(d.price_level));
  if (d?.kind_label) parts.push(d.kind_label);
  const note = brief.value?.price_note || d?.price_note;
  if (note) parts.push(note);
  const when = brief.value?.when || d?.when;
  if (when) parts.push(when);
  return parts;
});
const facts2 = computed(() => data.value?.address || brief.value?.where || data.value?.where || '');

// Photos need the session, so they are fetched with it and shown from local object URLs.
const photos = computed(
  () => (props.compact ? data.value?.photos?.slice(0, 1) : data.value?.photos?.slice(0, 3)) || [],
);
const urls = reactive<Record<string, string>>({});
const loaded = reactive(new Set<string>());
watch(
  [photos, () => props.photoKey] as const,
  async ([list]) => {
    const round = props.roundId;
    if (!round) return;
    for (const photo of list) {
      if (urls[photo.name]) continue;
      try {
        const response = await fetch(apiService.placePhotoUrl(round, photo.name), {
          headers: { Authorization: `Bearer ${sessionStorage.getItem('session_token') || ''}` },
        });
        if (response.ok) urls[photo.name] = URL.createObjectURL(await response.blob());
        else if (response.status === 404) break; // Not saved on the plan yet; retried when photoKey changes.
      } catch {
        /* keep the placeholder */
      }
    }
  },
  { immediate: true },
);
onBeforeUnmount(() => Object.values(urls).forEach((url) => URL.revokeObjectURL(url)));
</script>
<style scoped>
.overview-card {
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 16px;
  overflow: hidden;
  min-width: 0;
  transition:
    border-color var(--base) ease-out,
    box-shadow var(--base) var(--ease-out),
    transform var(--base) var(--ease-out);
}
.overview-card:hover {
  border-color: var(--sky-300);
  box-shadow: var(--shadow-md);
}
.overview-card.chosen {
  border-color: var(--blue);
  box-shadow: 0 0 0 1px var(--blue);
}
.photo-strip {
  display: grid;
  grid-template-columns: 2fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 2px;
  height: 200px;
  background: var(--sky-100);
}
.photo-strip:has(figure:only-child) {
  grid-template-columns: 1fr;
  grid-template-rows: 1fr;
}
.photo-strip:has(figure:nth-child(2):last-child) figure:nth-child(2) {
  grid-row: 1 / -1;
}
.photo-strip figure {
  position: relative;
  margin: 0;
  overflow: hidden;
  background: var(--sky-100);
}
.photo-strip figure.lead {
  grid-row: 1 / -1;
}
.photo-strip img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  opacity: 0;
  transform: scale(1.04);
  transition:
    opacity 500ms var(--ease-out),
    transform 900ms var(--ease-out);
}
.photo-strip img.ready {
  opacity: 1;
  transform: none;
}
.overview-card:hover .photo-strip img.ready {
  transform: scale(1.03);
}
.photo-placeholder {
  position: absolute;
  inset: 0;
  background: var(--sky-100);
  animation: pulse 1.6s ease-in-out infinite;
}
figcaption {
  position: absolute;
  left: 8px;
  bottom: 8px;
  max-width: calc(100% - 16px);
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 0.6875rem;
  color: #fff;
  background: rgba(10, 20, 40, 0.55);
  backdrop-filter: blur(4px);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
figcaption a {
  color: #fff;
}
.compact .photo-strip {
  height: 132px;
  grid-template-columns: 1fr;
  grid-template-rows: 1fr;
}
.body {
  padding: 18px 20px 20px;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}
.eyebrow {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
h3 {
  margin: 0;
  overflow-wrap: anywhere;
}
h3 .name {
  display: block;
  font-size: 1.25rem;
  line-height: 1.25;
  color: var(--night);
}
h3 .detail {
  display: block;
  margin-top: 4px;
  font-size: 0.9375rem;
  font-weight: 400;
  line-height: 1.4;
  color: var(--muted);
}
.compact h3 .name {
  font-size: 1.125rem;
}
.position {
  display: inline-grid;
  place-items: center;
  min-width: 24px;
  height: 24px;
  padding: 0 5px;
  border-radius: 7px;
  background: var(--sky-100);
  color: var(--blue-ink);
  font-size: 0.8125rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.chosen .position {
  background: var(--blue);
  color: #fff;
}
.kind {
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--faint);
}
.meta {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  font-size: 0.875rem;
  color: var(--muted);
  margin: 10px 0 0 -16px;
  overflow-wrap: anywhere;
  /* Every part carries a leading dot; the dot of whichever part starts a line falls in the clipped edge. */
  clip-path: inset(0 0 0 16px);
}
.meta > * {
  position: relative;
  margin-left: 16px;
}
.meta > *::before {
  content: '·';
  position: absolute;
  left: -11px;
  color: var(--faint);
}
.rating strong {
  color: var(--ink);
}
.star {
  margin-right: 3px;
  color: #d98a00;
}
.count {
  margin-left: 4px;
}
.address {
  display: flex;
  gap: 6px;
  font-size: 0.875rem;
  color: var(--muted);
  margin: 4px 0 0;
  overflow-wrap: anywhere;
}
.address .ui-icon {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
  margin-top: 3px;
}
.tagline {
  font-size: 0.9375rem;
  color: var(--ink-2);
  margin: 10px 0 0;
}
.summary {
  font-size: 0.9375rem;
  margin: 10px 0 0;
  color: var(--ink-2);
  overflow-wrap: anywhere;
}
.compact .summary {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.reviews {
  margin: 12px 0 0;
}
.reviews summary {
  min-height: 36px;
  padding: 8px 0;
  font-size: 0.875rem;
}
.reviews p {
  font-size: 0.875rem;
  color: var(--ink-2);
  margin: 0 0 10px;
}
.reviews .disclosure {
  font-size: 0.75rem;
  color: var(--muted);
}
.highlights {
  margin: 14px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.highlights li {
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--sky-50);
  border: 1px solid var(--sky-100);
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--blue-ink);
  min-width: 0;
  overflow-wrap: anywhere;
}
.compact .reviews {
  display: none;
}
/* Links sit at the foot of the card so cards in a row line up. */
.provenance {
  position: relative;
  font-size: 0.8125rem;
  color: var(--muted);
  margin: auto 0 0;
  padding-top: 32px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.provenance::before {
  content: '';
  position: absolute;
  top: 16px;
  left: 0;
  right: 0;
  border-top: 1px solid var(--line);
}
.maps-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  align-self: flex-start;
  font-size: 0.875rem;
  font-weight: 600;
  text-decoration: none;
}
.maps-link:hover {
  text-decoration: underline;
}
.maps-link .ui-icon {
  width: 14px;
  height: 14px;
}
.loading {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}
.skeleton.line {
  height: 14px;
  margin: 0;
  border-radius: 6px;
}
.skeleton.short {
  width: 60%;
}
/* Horizontal layout: photos on the left, details on the right, when the list is wide enough. */
@container (min-width: 640px) {
  .overview-card.wide {
    flex-direction: row;
  }
  .wide .photo-strip {
    flex: 0 0 clamp(260px, 38%, 400px);
    height: auto;
    min-height: 260px;
  }
  .wide .body {
    padding: 22px 26px 22px;
  }
  .wide .summary,
  .wide .tagline {
    max-width: 68ch;
  }
  .wide .provenance {
    padding-top: 28px;
  }
}
.facts {
  margin: 14px 0 0;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  display: grid;
  gap: 6px;
  font-size: 0.875rem;
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
  text-align: right;
  overflow-wrap: anywhere;
}
</style>
