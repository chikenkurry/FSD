<template>
  <article :class="['overview-card', { compact, chosen }]">
    <div v-if="photos.length" class="photo-strip">
      <figure v-for="(photo, i) in photos" :key="photo.name" :class="{ lead: i === 0 }">
        <img v-if="urls[photo.name]" :src="urls[photo.name]" :alt="i === 0 ? `${title}` : ''" loading="lazy" @load="loaded.add(photo.name)" :class="{ ready: loaded.has(photo.name) }" />
        <span v-else class="photo-placeholder" aria-hidden="true"></span>
        <figcaption v-if="photo.attributions.length && i === 0">Photo: <template v-for="(a, ai) in photo.attributions" :key="ai"><a v-if="a.uri" :href="a.uri" target="_blank" rel="noopener noreferrer">{{ a.name }}</a><span v-else>{{ a.name }}</span></template></figcaption>
      </figure>
    </div>
    <div class="body">
      <div class="head">
        <span v-if="position" class="position" aria-hidden="true">{{ position }}</span>
        <h3>{{ title }}</h3>
        <span v-if="kind" class="kind">{{ kindLabel }}</span>
      </div>
      <p v-if="facts1" class="meta">{{ facts1 }}</p>
      <p v-if="facts2" class="meta address">{{ facts2 }}</p>
      <div v-if="loading" class="loading" aria-hidden="true"><span class="skeleton line"></span><span class="skeleton line"></span><span class="skeleton line short"></span></div>
      <template v-else-if="summary || data">
        <p v-if="data?.tagline" class="tagline">{{ data.tagline }}</p>
        <p v-if="summary" class="summary">{{ summary }}</p>
        <ul v-if="highlights.length" class="highlights"><li v-for="h in highlights" :key="h">{{ h }}</li></ul>
        <details v-if="data?.review_summary" class="reviews"><summary>What reviewers say</summary><p>{{ data.review_summary }}</p><p v-if="data.review_disclosure" class="disclosure">{{ data.review_disclosure }}</p></details>
        <p class="provenance">
          <a v-if="data?.maps_url" :href="data.maps_url" target="_blank" rel="noopener noreferrer">View on Google Maps</a>
          <span v-if="source === 'organiser'">Overview corrected by the organiser.</span>
          <span v-else-if="source === 'ai_general'">General description by AI, not about a specific venue.</span>
          <span v-else-if="sources.length">Summary from <template v-for="(s, si) in sources" :key="s.url"><a :href="s.url" target="_blank" rel="noopener noreferrer">{{ s.title || 'the web' }}</a><template v-if="si < sources.length - 1">, </template></template></span>
        </p>
      </template>
      <p v-else-if="!facts?.length" class="summary muted">No overview yet.</p>
      <dl v-if="facts?.length" class="facts">
        <div v-for="fact in facts" :key="fact.criterion"><dt>{{ factLabel(fact.criterion) }}</dt><dd>{{ factValue(fact, currency) }}</dd></div>
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

const props = withDefaults(defineProps<{ title: string; overview?: Overview | null; kind?: OptionKind; roundId?: string; placeId?: string;
  description?: string; brief?: Brief; facts?: PublishedFact[]; currency?: string; position?: number; loading?: boolean; compact?: boolean; chosen?: boolean; photoKey?: number }>(),
  { currency: 'SGD', compact: false, chosen: false, loading: false });

// Place cards are fetched live by place ID; Google’s terms don’t allow storing their content.
const live = ref<Overview>();
const data = computed(() => live.value || (props.overview?.source === 'google_places' ? props.overview : undefined));
watch(() => [props.roundId, props.placeId] as const, async ([roundId, placeId]) => {
  if (!roundId || !placeId || props.overview?.source === 'google_places') return;
  live.value = undefined;
  try { live.value = await apiService.placeCard(roundId, placeId); } catch { /* fall back to stored description */ }
}, { immediate: true });

const kindLabel = computed(() => ({ place: 'Place', destination: 'Destination', event: 'Event', activity: 'Activity', other: '' } as Record<string, string>)[props.kind || 'other']);
// Live Places details (rating, address, photos) combine with the stored web/AI brief.
const brief = computed(() => props.brief || (props.overview && props.overview.source !== 'google_places' ? props.overview : undefined));
const summary = computed(() => brief.value?.summary || data.value?.summary || props.description || data.value?.review_summary || '');
const highlights = computed(() => (brief.value?.highlights?.length ? brief.value.highlights : data.value?.highlights || []).slice(0, props.compact ? 3 : 4));
const source = computed(() => brief.value?.source || data.value?.source);
// Sources are de-duplicated by site name, so one site cited three times reads once.
const sources = computed(() => {
  const list = brief.value?.sources?.length ? brief.value.sources : data.value?.sources || [];
  const seen = new Set<string>();
  return list.filter(s => { const key = (s.title || s.url).toLowerCase(); if (seen.has(key)) return false; seen.add(key); return true; }).slice(0, 2);
});
const facts1 = computed(() => {
  const d = data.value; const parts: string[] = [];
  if (d?.rating) parts.push(`${d.rating.toFixed(1)} ★${d.rating_count ? ` (${d.rating_count.toLocaleString()})` : ''}`);
  if (d?.price_level != null) parts.push(d.price_level === 0 ? 'Free' : '$'.repeat(d.price_level));
  if (d?.kind_label) parts.push(d.kind_label);
  const note = brief.value?.price_note || d?.price_note; if (note) parts.push(note);
  const when = brief.value?.when || d?.when; if (when) parts.push(when);
  return parts.join(' · ');
});
const facts2 = computed(() => data.value?.address || brief.value?.where || data.value?.where || '');

// Photos need the session, so they are fetched with it and shown from local object URLs.
const photos = computed(() => (props.compact ? data.value?.photos?.slice(0, 1) : data.value?.photos?.slice(0, 3)) || []);
const urls = reactive<Record<string, string>>({});
const loaded = reactive(new Set<string>());
watch([photos, () => props.photoKey] as const, async ([list]) => {
  const round = props.roundId; if (!round) return;
  for (const photo of list) {
    if (urls[photo.name]) continue;
    try {
      const response = await fetch(apiService.placePhotoUrl(round, photo.name), { headers: { Authorization: `Bearer ${sessionStorage.getItem('session_token') || ''}` } });
      if (response.ok) urls[photo.name] = URL.createObjectURL(await response.blob());
      else if (response.status === 404) break; // Not saved on the plan yet; retried when photoKey changes.
    } catch { /* keep the placeholder */ }
  }
}, { immediate: true });
onBeforeUnmount(() => Object.values(urls).forEach(url => URL.revokeObjectURL(url)));
</script>
<style scoped>
.overview-card { display: flex; flex-direction: column; background: var(--surface); border: 1px solid var(--line); border-radius: 16px; overflow: hidden; min-width: 0; transition: border-color var(--base) ease-out, box-shadow var(--base) var(--ease-out), transform var(--base) var(--ease-out); }
.overview-card:hover { border-color: var(--sky-300); box-shadow: var(--shadow-md); }
.overview-card.chosen { border-color: var(--blue); box-shadow: 0 0 0 1px var(--blue); }
.photo-strip { display: grid; grid-template-columns: 2fr 1fr; grid-template-rows: 1fr 1fr; gap: 2px; height: 188px; background: var(--sky-100); }
.photo-strip:has(figure:only-child) { grid-template-columns: 1fr; grid-template-rows: 1fr; }
.photo-strip:has(figure:nth-child(2):last-child) figure:nth-child(2) { grid-row: 1 / -1; }
.photo-strip figure { position: relative; margin: 0; overflow: hidden; background: var(--sky-100); }
.photo-strip figure.lead { grid-row: 1 / -1; }
.photo-strip img { width: 100%; height: 100%; object-fit: cover; display: block; opacity: 0; transform: scale(1.04); transition: opacity 500ms var(--ease-out), transform 900ms var(--ease-out); }
.photo-strip img.ready { opacity: 1; transform: none; }
.photo-placeholder { position: absolute; inset: 0; background: var(--sky-100); animation: pulse 1.6s ease-in-out infinite; }
figcaption { position: absolute; left: 8px; bottom: 8px; max-width: calc(100% - 16px); padding: 2px 8px; border-radius: 6px; font-size: .6875rem; color: #fff; background: rgba(10, 33, 80, .72); }
figcaption a { color: #fff; }
.compact .photo-strip { height: 132px; grid-template-columns: 1fr; grid-template-rows: 1fr; }
.body { padding: 18px 20px 20px; display: flex; flex-direction: column; flex: 1; min-width: 0; }
.head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.head h3 { font-size: 1.125rem; margin: 0; overflow-wrap: anywhere; }
.position { display: inline-grid; place-items: center; min-width: 24px; height: 24px; padding: 0 5px; border-radius: 7px; background: var(--sky-100); color: var(--blue-ink); font-size: .8125rem; font-weight: 700; font-variant-numeric: tabular-nums; align-self: center; }
.chosen .position { background: var(--blue); color: #fff; }
.kind { font-size: .8125rem; font-weight: 600; color: var(--muted); margin-left: auto; }
.meta { font-size: .875rem; color: var(--muted); margin: 6px 0 0; overflow-wrap: anywhere; }
.meta.address { margin-top: 0; }
.tagline { font-size: .9375rem; color: var(--ink-2); margin: 10px 0 0; }
.summary { font-size: .9375rem; margin: 10px 0 0; color: var(--ink-2); overflow-wrap: anywhere; }
.compact .summary { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.reviews { margin: 12px 0 0; }
.reviews summary { min-height: 36px; padding: 8px 0; font-size: .875rem; }
.reviews p { font-size: .875rem; color: var(--ink-2); margin: 0 0 10px; }
.reviews .disclosure { font-size: .75rem; color: var(--muted); }
.highlights { margin: 12px 0 0; padding: 0; list-style: none; display: grid; gap: 4px; }
.highlights li { display: flex; align-items: baseline; gap: 10px; font-size: .875rem; color: var(--ink-2); min-width: 0; overflow-wrap: anywhere; }
.highlights li::before { content: ''; flex-shrink: 0; width: 5px; height: 5px; border-radius: 1px; background: var(--blue); transform: translateY(-2px); }
.compact .reviews { display: none; }
.provenance { font-size: .8125rem; color: var(--muted); margin: 12px 0 0; display: flex; flex-wrap: wrap; gap: 4px 12px; }
.loading { display: grid; gap: 8px; margin-top: 12px; }
.skeleton.line { height: 14px; margin: 0; border-radius: 6px; }
.skeleton.short { width: 60%; }
.facts { margin: 14px 0 0; padding-top: 12px; border-top: 1px solid var(--line); display: grid; gap: 6px; font-size: .875rem; }
.facts > div { display: flex; justify-content: space-between; gap: 12px; }
.facts dt { color: var(--muted); }
.facts dd { margin: 0; font-weight: 600; text-align: right; overflow-wrap: anywhere; }
</style>
