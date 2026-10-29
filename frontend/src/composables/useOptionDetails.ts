import { onUnmounted, reactive, toValue, watch, type MaybeRefOrGetter } from 'vue';
import { apiService } from '@/services/api';
import type { Overview, Snapshot } from '@/types/form';

// Live Google Places details and photos for a round's options, plus display helpers
// that fall back to the option's stored brief when Places has nothing to add.
export function useOptionDetails(roundId: MaybeRefOrGetter<string>, snapshot: MaybeRefOrGetter<Snapshot | undefined>) {
  let alive = true;
  const liveOverviews = reactive<Record<string, Overview>>({});
  const photoUrls = reactive<Record<string, string>>({});
  const loadedPhotos = reactive(new Set<string>());

  // Fetch live Google Places metadata & photos for options that carry a place_id.
  watch(
    () => toValue(snapshot)?.options,
    async (options) => {
      if (!options?.length || !toValue(roundId)) return;
      await Promise.all(
        options.map(async (opt) => {
          const placeId = opt.identity?.place_id;
          if (!placeId || liveOverviews[opt.option_id]) return;
          try {
            const card = await apiService.placeCard(toValue(roundId), placeId);
            if (!alive) return;
            liveOverviews[opt.option_id] = card;
            for (const photo of (card.photos || []).slice(0, 2)) {
              if (photoUrls[photo.name]) continue;
              const response = await fetch(apiService.placePhotoUrl(toValue(roundId), photo.name), {
                headers: { Authorization: `Bearer ${sessionStorage.getItem('session_token') || ''}` },
              });
              if (response.ok && alive) photoUrls[photo.name] = URL.createObjectURL(await response.blob());
            }
          } catch {
            /* Fall back to stored brief and monogram banner */
          }
        }),
      );
    },
    { immediate: true },
  );

  function optionOf(id: string) {
    return toValue(snapshot)?.options.find((o) => o.option_id === id);
  }
  function optionPhotos(id: string) {
    return (liveOverviews[id]?.photos || []).slice(0, 2);
  }
  function optionLeadPhoto(id: string) {
    const first = optionPhotos(id)[0];
    return first ? photoUrls[first.name] || '' : '';
  }
  function optionKindLabel(id: string) {
    const kind = optionOf(id)?.identity?.kind || 'other';
    return (
      (
        { place: 'Place', destination: 'Destination', event: 'Event', activity: 'Activity', other: '' } as Record<
          string,
          string
        >
      )[kind] || ''
    );
  }
  function optionSummary(id: string) {
    const opt = optionOf(id);
    const live = liveOverviews[id];
    return opt?.brief?.summary || live?.summary || opt?.description || live?.review_summary || '';
  }
  function optionHighlights(id: string) {
    const opt = optionOf(id);
    const live = liveOverviews[id];
    return (opt?.brief?.highlights?.length ? opt.brief.highlights : live?.highlights || []).slice(0, 4);
  }
  function optionMeta(id: string) {
    const opt = optionOf(id);
    const live = liveOverviews[id];
    const parts: string[] = [];
    if (live?.rating)
      parts.push(`${live.rating.toFixed(1)} ★${live.rating_count ? ` (${live.rating_count.toLocaleString()})` : ''}`);
    if (live?.price_level != null) parts.push(live.price_level === 0 ? 'Free' : '$'.repeat(live.price_level));
    if (live?.kind_label) parts.push(live.kind_label);
    const note = opt?.brief?.price_note || live?.price_note;
    if (note) parts.push(note);
    const when = opt?.brief?.when || live?.when;
    if (when) parts.push(when);
    return parts.join(' · ');
  }
  function optionAddress(id: string) {
    const opt = optionOf(id);
    const live = liveOverviews[id];
    return live?.address || opt?.brief?.where || live?.where || '';
  }
  function optionMonogram(title: string) {
    const words = title.trim().split(/\s+/).filter(Boolean);
    return (
      words
        .slice(0, 2)
        .map((w) => w[0]?.toUpperCase() || '')
        .join('') || '?'
    );
  }
  onUnmounted(() => {
    alive = false;
    Object.values(photoUrls).forEach((url) => URL.revokeObjectURL(url));
  });
  return {
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
  };
}
