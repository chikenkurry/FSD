<template>
  <dialog ref="dialog" class="join-dialog" aria-labelledby="join-heading" @close="emit('close')" @click="backdrop">
    <form method="dialog" class="join-body" @submit.prevent="submit">
      <div class="join-head">
        <h2 id="join-heading">Join a plan</h2>
        <button type="button" class="btn-quiet btn-icon" aria-label="Close" @click="dialog?.close()"><UiIcon name="close" /></button>
      </div>
      <p class="muted">Paste the invitation link the organiser shared with you. You’ll join with your current session.</p>
      <label>Paste the invitation link<input ref="field" v-model="link" autocomplete="off" spellcheck="false" placeholder="https://…/#round=…&invite=…" :aria-invalid="error ? 'true' : undefined" aria-describedby="join-error" /></label>
      <Transition name="reveal"><p v-if="error" id="join-error" class="field-error">{{ error }}</p></Transition>
      <div class="join-actions">
        <button type="button" class="btn-quiet" @click="dialog?.close()">Cancel</button>
        <button type="submit" class="btn-primary" :disabled="!link.trim()">Open invitation<UiIcon name="arrow" /></button>
      </div>
    </form>
  </dialog>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue';
import UiIcon from './UiIcon.vue';
import { parseInvite } from '@/services/invite';
const emit = defineEmits<{ (e: 'close'): void; (e: 'join', value: { round: string; invite: string }): void }>();
const dialog = ref<HTMLDialogElement>(); const field = ref<HTMLInputElement>();
const link = ref(''); const error = ref('');
onMounted(() => { dialog.value?.showModal(); field.value?.focus(); });
function backdrop(event: MouseEvent) { if (event.target === dialog.value) dialog.value?.close(); }
function submit() {
  const parsed = parseInvite(link.value);
  if (!parsed) { error.value = 'That doesn’t look like an invitation link. It should contain “round=” and “invite=”.'; return; }
  emit('join', parsed); dialog.value?.close();
}
</script>
<style scoped>
.join-dialog { width: min(520px, calc(100vw - 32px)); padding: 0; border: 0; border-radius: 20px; background: var(--surface); color: var(--ink); box-shadow: var(--shadow-lg); }
.join-dialog[open] { animation: dialog-in 360ms var(--ease-out); }
.join-dialog::backdrop { background: rgba(10, 33, 80, .32); backdrop-filter: blur(3px); animation: fade 240ms ease-out; }
@keyframes dialog-in { from { opacity: 0; transform: translateY(12px) scale(.98); } }
@keyframes fade { from { opacity: 0; } }
.join-body { padding: 28px; }
.join-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.join-head h2 { margin: 0; }
.join-body > p { font-size: .9375rem; }
.join-body label { margin-bottom: 8px; }
.field-error { color: var(--danger); font-size: .875rem; margin: 0; }
.join-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 24px; flex-wrap: wrap; }
@media (max-width: 480px) { .join-body { padding: 22px 20px; } .join-actions button { flex: 1 1 100%; } .join-actions { flex-direction: column-reverse; } }
</style>
