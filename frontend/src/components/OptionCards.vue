<template>
  <ul class="option-cards">
    <li v-for="(option, index) in options" :key="option.option_id" class="rise" :style="{ '--i': index }">
      <OverviewCard :title="option.title" :description="option.description" :brief="option.brief" :kind="option.identity?.kind" :round-id="roundId"
        :place-id="option.identity?.place_id" :position="index + 1" :chosen="option.option_id === chosen" :compact="compact" />
    </li>
  </ul>
</template>
<script setup lang="ts">
import type { Snapshot } from '@/types/form';
import OverviewCard from './OverviewCard.vue';
// Members see the overview, not the internal comparison facts used for ranking.
withDefaults(defineProps<{ options: Snapshot['options']; currency: string; roundId?: string; chosen?: string; compact?: boolean }>(), { compact: false });
</script>
<style scoped>
.option-cards { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr)); gap: 16px; }
.option-cards > li { display: flex; min-width: 0; }
.option-cards > li > * { flex: 1; }
</style>
