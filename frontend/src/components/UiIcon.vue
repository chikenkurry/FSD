<template>
  <svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path :d="paths[name]" /></svg>
</template>
<script setup lang="ts">
const paths = {
  plus: 'M12 5v14M5 12h14', arrow: 'M5 12h14m-6-6 6 6-6 6', back: 'M19 12H5m6-6-6 6 6 6',
  check: 'm5 12 4 4L19 6', close: 'm6 6 12 12M6 18 18 6',
  search: 'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0', refresh: 'M20 8a8 8 0 1 0 0 8M20 3v5h-5',
  lock: 'M6 10h12v11H6zM8 10V6a4 4 0 0 1 8 0v4m-4 5v2',
  document: 'M6 3h8l4 4v14H6zM14 3v5h4M9 12h6m-6 4h6',
  people: 'M16 21v-3a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v3m20 0v-3a4 4 0 0 0-3-4M13 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0m4-4a4 4 0 0 1 0 8',
};
defineProps<{ name: keyof typeof paths }>();
</script>
