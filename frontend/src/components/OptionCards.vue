<template>
  <ul class="option-cards">
    <li v-for="(option, index) in options" :key="option.option_id" class="rise" :style="{ '--i': index }">
      <OverviewCard
        :title="option.title"
        :description="option.description"
        :brief="option.brief"
        :kind="option.identity?.kind"
        :round-id="roundId"
        :place-id="option.identity?.place_id"
        :position="index + 1"
        :chosen="option.option_id === chosen"
        :compact="compact"
      />
    </li>
  </ul>
</template>
<script setup lang="ts">
import type { Snapshot } from '@/types/form';
import OverviewCard from './OverviewCard.vue';
// Members see the overview, not the internal comparison facts used for ranking.
withDefaults(
  defineProps<{
    options: Snapshot['options'];
    currency: string;
    roundId?: string;
    chosen?: string;
    compact?: boolean;
  }>(),
  { compact: false },
);
</script>
<style scoped>
.option-cards {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));
  gap: 20px;
}
/* One or two options keep a card-like width instead of stretching across the page. */
.option-cards:has(> li:only-child) {
  max-width: 480px;
}
.option-cards:has(> li:nth-child(2):last-child) {
  max-width: 980px;
}
.option-cards > li {
  display: flex;
  min-width: 0;
}
.option-cards > li > * {
  flex: 1;
}
</style>
