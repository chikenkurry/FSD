<template>
  <div class="app-container">
    <header v-if="auth.token" class="session-bar">
      <span>{{ auth.username }}</span>
      <button @click="dashboard">My forms</button>
      <details><summary>Session details</summary><p>Keep these private. They allow access to your session.</p>
        <label>User ID<input readonly :value="auth.userID" /></label>
        <label>Session token<input readonly type="password" :value="auth.token" /></label>
        <button @click="copySession">Copy session details</button><span>{{ copied ? 'Copied' : '' }}</span>
      </details>
      <button @click="logout">Sign out</button>
      <span role="alert">{{ error }}</span>
    </header>
    <Login v-if="!auth.token" @navigate="afterLogin" />
    <RoundWorkspace v-else-if="roundId" :key="roundId" :round-id="roundId" :invite-token="inviteToken" @open-round="openRound" />
    <FormCreator v-else-if="frame === 'creator'" @navigate="frame = $event" @published="published" />
    <FormsDashboard v-else @navigate="frame = $event" @open-plan="openPlan" />
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import Login from '@/components/Login.vue';
import FormsDashboard from '@/components/FormsDashboard.vue';
import FormCreator from '@/components/FormCreator.vue';
import RoundWorkspace from '@/components/RoundWorkspace.vue';
import { useAuthStore } from '@/stores/auth';
import { apiService, ApiError } from '@/services/api';
import type { Form } from '@/types/form';
const auth = useAuthStore(); const frame = ref('dashboard'); const roundId = ref(''); const inviteToken = ref(''); const error = ref(''); const copied = ref(false);
function readLink() { const params = new URLSearchParams(location.hash.slice(1)); roundId.value = params.get('round') || ''; inviteToken.value = params.get('invite') || ''; }
readLink();
function openRound(id: string) { location.hash = new URLSearchParams({ round: id }).toString(); readLink(); }
function dashboard() { location.hash = ''; readLink(); frame.value = 'dashboard'; }
function published(form: Form) { if (form.roundId) openRound(form.roundId); }
function afterLogin() { readLink(); frame.value = 'dashboard'; }
async function openPlan(id: string) { try { const result = await apiService.rounds(id); const latest = [...result.data].sort((a,b) => b.round_number-a.round_number)[0]; if (!latest) throw new Error('This draft has no published round. Finish it in the creator tab.'); openRound(latest.id); } catch(e) { error.value = String(e); } }
async function copySession() { await navigator.clipboard.writeText(JSON.stringify({ user_id: auth.userID, session_token: auth.token })); copied.value = true; }
async function logout() { try { await apiService.revoke(); auth.logout(); } catch(e) { if(e instanceof ApiError && e.status === 401) auth.logout(); else error.value = String(e); } }
onMounted(() => { readLink(); window.addEventListener('hashchange', readLink); });
onUnmounted(() => window.removeEventListener('hashchange', readLink));
</script>
<style>
body { margin: 0; font-family: system-ui, sans-serif; color: #2d3748; background: #efece9; }
button { cursor: pointer; } button:disabled { cursor: wait; opacity: .6; }
input, select, textarea { box-sizing: border-box; max-width: 100%; padding: .6rem; border: 1px solid #cbd5e0; border-radius: 5px; }
label { display: block; margin: .7rem 0; } label input:not([type=checkbox]):not([type=radio]), label textarea { display: block; width: 100%; }
.session-bar { display: flex; gap: 1rem; align-items: center; padding: .8rem 1.5rem; background: #fff; flex-wrap: wrap; }
.session-bar details { max-width: 36rem; }.session-bar button { padding: .5rem; }
</style>
