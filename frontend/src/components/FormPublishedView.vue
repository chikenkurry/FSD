<template>
  <RoundWorkspace v-if="form.roundId" :round-id="form.roundId" />
  <p v-else>This form has not been published. Finish publishing before sharing it.</p>
</template>
<script setup lang="ts">
import RoundWorkspace from './RoundWorkspace.vue';
import type { Form } from '@/types/form';
defineProps<{ form: Form }>();
</script>
