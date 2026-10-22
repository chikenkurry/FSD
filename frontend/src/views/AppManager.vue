<template>
  <div class="app-container">
    <a v-if="auth.token" class="skip-link" href="#main-content" @click.prevent="focusContent">Skip to content</a>
    <header v-if="auth.token" class="session-bar">
      <button class="brand home-brand" aria-label="What to do? Home" @click="dashboard"><BrandMark />What to do?</button>
      <nav aria-label="Main navigation"><button class="nav-button" :aria-current="!roundId && frame === 'dashboard' ? 'page' : undefined" @click="dashboard">My forms</button></nav>
      <div class="session-actions"><span class="session-name">{{ auth.username }}</span>
      <details ref="menu" class="session-menu" @keydown.esc="closeMenu"><summary>Session details</summary><div class="session-popover"><p>Keep these private. They allow access to your session.</p>
        <label>User ID<input readonly :value="auth.userID" /></label>
        <label>Session token<input readonly type="password" :value="auth.token" /></label>
        <div class="popover-actions"><button @click="copySession">{{ copied ? 'Copied' : 'Copy session details' }}</button><span role="status">{{ copied ? 'Copied to clipboard' : '' }}</span></div>
      </div></details>
      <button class="sign-out" @click="logout">Sign out</button></div>
    </header>
    <Transition name="reveal"><div v-if="error" class="app-error" role="alert"><span>{{ error }}</span><button class="btn-quiet btn-small" @click="error = ''">Dismiss</button></div></Transition>
    <Transition name="view" mode="out-in">
      <Login v-if="!auth.token" :invited="!!inviteToken" @navigate="afterLogin" />
      <RoundWorkspace v-else-if="roundId" :key="roundId" :round-id="roundId" :invite-token="inviteToken" @open-round="openRound" @open-draft="openDraft" />
      <FormCreator v-else-if="frame === 'creator'" :plan-id="creatorPlanId" @navigate="navigate" @draft-saved="draftSaved" @published="published" />
      <FormsDashboard v-else @navigate="navigate" @open-plan="openPlan" />
    </Transition>
  </div>
</template>
<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue';
import { checkpointKey, readCheckpoint, writeCheckpoint, removeCheckpoint } from '@/services/checkpoints';
import BrandMark from '@/components/BrandMark.vue';
import Login from '@/components/Login.vue';
import FormsDashboard from '@/components/FormsDashboard.vue';
import FormCreator from '@/components/FormCreator.vue';
import RoundWorkspace from '@/components/RoundWorkspace.vue';
import { useAuthStore } from '@/stores/auth';
import { apiService, ApiError } from '@/services/api';
import type { Form } from '@/types/form';
const auth = useAuthStore(); const frame = ref(readCheckpoint<string>(checkpointKey(auth.userID, 'screen')) === 'creator' ? 'creator' : 'dashboard'); const roundId = ref(''); const inviteToken = ref(''); const error = ref(''); const copied = ref(false);
const creatorPlanId=ref('');
watch(frame, value => { if (auth.userID) writeCheckpoint(checkpointKey(auth.userID, 'screen'), value); }, { flush: 'sync' });
const menu = ref<HTMLDetailsElement>();
function message(e: unknown) { return e instanceof Error ? e.message : String(e); }
function focusContent() { const main = document.getElementById('main-content'); main?.focus(); main?.scrollIntoView(); }
function readLink() { const params = new URLSearchParams(location.hash.slice(1)); roundId.value = params.get('round') || ''; inviteToken.value = params.get('invite') || ''; creatorPlanId.value=params.get('draft') || ''; if(creatorPlanId.value)frame.value='creator'; }
readLink();
function openRound(id: string) { error.value = ''; location.hash = new URLSearchParams({ round: id }).toString(); readLink(); }
function dashboard() { error.value = ''; location.hash = ''; readLink(); frame.value = 'dashboard'; }
function navigate(next:string){ if(next==='creator'){removeCheckpoint(checkpointKey(auth.userID,'creator'));creatorPlanId.value='';location.hash='';readLink();frame.value='creator';}else dashboard(); }
function openDraft(id:string){location.hash=new URLSearchParams({draft:id}).toString();readLink();frame.value='creator';}
function draftSaved(id:string){history.replaceState(null,'',`/#${new URLSearchParams({draft:id})}`);creatorPlanId.value=id;}
function published(form: Form) { if (form.roundId) openRound(form.roundId); }
function afterLogin() { readLink(); frame.value = readCheckpoint<string>(checkpointKey(auth.userID, 'screen')) === 'creator' ? 'creator' : 'dashboard'; }
async function openPlan(id: string) {
  try {
    const plan=await apiService.plan(id);
    if(plan.state==='DRAFT' && plan.created_by_user_id===auth.userID){openDraft(id);return;}
    const result=await apiService.rounds(id);
    for(const round of [...result.data].sort((a,b)=>b.round_number-a.round_number)){
      try{await apiService.snapshot(round.id);openRound(round.id);return;}catch(e){if(!(e instanceof ApiError && e.status===404))throw e;}
    }
    throw new Error('The organiser has not published a round yet.');
  }catch(e){error.value=message(e);}
}
async function copySession() { try { await navigator.clipboard.writeText(JSON.stringify({ user_id: auth.userID, session_token: auth.token })); copied.value = true; setTimeout(() => { copied.value = false; }, 2400); } catch { error.value = 'Clipboard unavailable. Select and copy your session fields manually.'; } }
async function logout() { try { await apiService.revoke(); auth.logout(); } catch(e) { if(e instanceof ApiError && e.status === 401) auth.logout(); else error.value = message(e); } }
function closeMenu() { if (menu.value?.open) { menu.value.open = false; menu.value.querySelector('summary')?.focus(); } }
function outside(event: PointerEvent) { if (menu.value?.open && !menu.value.contains(event.target as Node)) menu.value.open = false; }
onMounted(() => { readLink(); window.addEventListener('hashchange', readLink); document.addEventListener('pointerdown', outside); });
onUnmounted(() => { window.removeEventListener('hashchange', readLink); document.removeEventListener('pointerdown', outside); });
</script>
<style scoped>
.session-bar { position: relative; display: flex; align-items: center; gap: 32px; padding: 12px max(24px, calc((100vw - 1200px) / 2)); background: var(--navy); color: #f1f5f6; flex-wrap: wrap; }
.home-brand { background: transparent; border: 0; color: inherit; padding: 0; }
.home-brand:hover:not(:disabled) { background: transparent; color: #c6e0d2; }
.home-brand:active:not(:disabled) { background: transparent; }
.nav-button, .sign-out { background: transparent; border-color: transparent; color: #d9e3e8; font-size: .875rem; }
.nav-button[aria-current='page'] { background: #304b59; color: #fff; }
.nav-button:hover:not(:disabled), .sign-out:hover:not(:disabled), .nav-button:active:not(:disabled), .sign-out:active:not(:disabled) { background: #304b59; color: #fff; border-color: transparent; }
.session-actions { margin-left: auto; display: flex; align-items: center; gap: 16px; min-width: 0; }
.session-name { font-size: .8125rem; max-width: 160px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; color: #d2dfe5; }
.session-menu { position: relative; border: 0; }
.session-menu summary { font-size: .8125rem; color: #d9e3e8; padding: 10px 12px; border-radius: 7px; }
.session-menu summary:hover, .session-menu[open] summary { color: #fff; background: #304b59; }
.session-popover { position: absolute; right: 0; top: 52px; width: min(360px, calc(100vw - 32px)); background: #fff; color: var(--ink); padding: 24px; border: 1px solid var(--line); border-radius: 12px; z-index: 10; box-shadow: 0 12px 32px -12px rgba(24, 46, 59, .28); transform-origin: top right; }
.session-menu[open] .session-popover { animation: pop var(--base) var(--ease-out); }
@keyframes pop { from { opacity: 0; transform: translateY(-4px) scale(.98); } }
.session-popover p { font-size: .875rem; color: var(--muted); }
.session-popover label:first-of-type { margin-top: 0; }
.session-popover input { font-size: .8125rem; }
.popover-actions { display: flex; align-items: center; gap: 12px; }
.popover-actions [role='status'] { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
.app-error { display: flex; align-items: center; justify-content: space-between; gap: 16px; max-width: 1200px; margin: 20px auto 0; width: calc(100% - 64px); }
.app-error button { color: var(--danger); flex-shrink: 0; }
.app-error button:hover:not(:disabled) { background: #fbe1dc; }
@media(max-width: 900px) { .session-bar { gap: 16px; padding: 12px 20px; } .session-name { display: none; } .session-actions { gap: 8px; } }
@media(max-width: 700px) { .app-error { width: calc(100% - 40px); } }
@media(max-width: 600px) { .session-bar { gap: 8px; padding: 12px 16px; } .home-brand { flex: 1 1 100%; justify-content: flex-start; } .session-actions { margin-left: auto; } .session-menu { position: static; } .session-popover { right: 16px; top: calc(100% - 4px); } .session-menu summary, .sign-out, .nav-button { font-size: .75rem; padding: 10px 7px; } }
</style>
