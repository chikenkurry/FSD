<template>
  <Transition name="view" mode="out-in">
    <div v-if="resuming" class="resuming" role="status"><BrandMark /><p>Signing you back in…</p></div>
    <Login v-else-if="!auth.token" :invited="!!inviteToken" @navigate="afterLogin" />
    <div v-else :class="['shell', { collapsed }]">
      <a class="skip-link" href="#main-content" @click.prevent="focusContent">Skip to content</a>
      <aside class="sidebar" aria-label="Application">
        <div class="sidebar-top">
          <button class="brand home-brand" aria-label="What2Do Home" @click="dashboard"><BrandMark /><span class="brand-name">What2Do</span></button>
          <button class="btn-quiet btn-icon collapse-toggle" :aria-label="collapsed ? 'Expand sidebar' : 'Collapse sidebar'" :aria-expanded="!collapsed" @click="toggleSidebar"><UiIcon name="sidebar" /></button>
        </div>
        <nav class="sidebar-nav" aria-label="Main navigation">
          <button class="nav-item" data-tip="My forms" :aria-current="!roundId && frame === 'dashboard' ? 'page' : undefined" @click="dashboard"><UiIcon name="forms" /><span class="nav-label">My forms</span></button>
          <button class="nav-item" data-tip="New form" :aria-current="!roundId && frame === 'creator' ? 'page' : undefined" @click="navigate('creator')"><UiIcon name="plus" /><span class="nav-label">New form</span></button>
          <button class="nav-item" data-tip="Join with a link" @click="joining = true"><UiIcon name="link" /><span class="nav-label">Join with a link</span></button>
        </nav>
        <div class="sidebar-foot">
          <details ref="menu" class="session-menu" @keydown.esc="closeMenu">
            <summary data-tip="Session details"><span class="avatar" aria-hidden="true">{{ initial }}</span><span class="who"><span class="who-name">{{ auth.username }}</span><span class="who-hint">Session details</span></span></summary>
            <div class="session-popover"><h2 class="popover-title">Your session</h2><p>Your return link signs you back in as yourself on any device. Keep it private, like a password.</p>
              <button class="btn-primary btn-small return-copy" @click="copyReturnLink"><UiIcon :name="linkCopied ? 'check' : 'link'" />{{ linkCopied ? 'Return link copied' : 'Copy my return link' }}</button>
              <details class="raw-session"><summary>Show session details</summary>
              <label>User ID<input readonly :value="auth.userID" /></label>
              <label>Session token<input readonly type="password" :value="auth.token" /></label>
              <div class="popover-actions"><button class="btn-small" @click="copySession"><UiIcon :name="copied ? 'check' : 'key'" />{{ copied ? 'Copied' : 'Copy session details' }}</button><span role="status">{{ copied ? 'Copied to clipboard' : '' }}</span></div>
              </details>
            </div>
          </details>
          <button class="nav-item sign-out" data-tip="Sign out" @click="logout"><UiIcon name="logout" /><span class="nav-label">Sign out</span></button>
        </div>
      </aside>
      <div class="main-col">
        <Transition name="reveal"><div v-if="error" class="app-error" role="alert"><span>{{ error }}</span><button class="btn-quiet btn-small" @click="error = ''">Dismiss</button></div></Transition>
        <Transition name="view" mode="out-in">
          <RoundWorkspace v-if="roundId" :key="roundId" :round-id="roundId" :invite-token="inviteToken" @open-round="openRound" @open-draft="openDraft" />
          <FormCreator v-else-if="frame === 'creator'" :key="`creator-${creatorKey}`" :plan-id="creatorPlanId" @navigate="navigate" @draft-saved="draftSaved" @published="published" />
          <FormsDashboard v-else @navigate="navigate" @open-plan="openPlan" />
        </Transition>
      </div>
      <JoinDialog v-if="joining" @close="joining = false" @join="joinPlan" />
    </div>
  </Transition>
</template>
<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import { checkpointKey, readCheckpoint, writeCheckpoint, removeCheckpoint } from '@/services/checkpoints';
import BrandMark from '@/components/BrandMark.vue';
import UiIcon from '@/components/UiIcon.vue';
import Login from '@/components/Login.vue';
import JoinDialog from '@/components/JoinDialog.vue';
import FormsDashboard from '@/components/FormsDashboard.vue';
import FormCreator from '@/components/FormCreator.vue';
import RoundWorkspace from '@/components/RoundWorkspace.vue';
import { useAuthStore } from '@/stores/auth';
import { apiService, ApiError } from '@/services/api';
import { readReturnLink, returnLink } from '@/services/returnLink';
import type { Form } from '@/types/form';
const auth = useAuthStore(); const frame = ref(readCheckpoint<string>(checkpointKey(auth.userID, 'screen')) === 'creator' ? 'creator' : 'dashboard'); const roundId = ref(''); const inviteToken = ref(''); const error = ref(''); const copied = ref(false);
const creatorPlanId=ref(''); const creatorKey = ref(0); const joining = ref(false);
const resuming = ref(false); const linkCopied = ref(false);
const initial = computed(() => auth.username.trim().charAt(0).toUpperCase() || '?');
// The collapsed sidebar is a per-viewer convenience; storage may be unavailable.
function storedCollapse() { try { return localStorage.getItem('w2d.sidebar') === 'collapsed'; } catch { return false; } }
const collapsed = ref(storedCollapse());
function toggleSidebar() { collapsed.value = !collapsed.value; if (menu.value) menu.value.open = false; try { localStorage.setItem('w2d.sidebar', collapsed.value ? 'collapsed' : 'open'); } catch { /* keep in memory */ } }
watch(frame, value => { if (auth.userID) writeCheckpoint(checkpointKey(auth.userID, 'screen'), value); }, { flush: 'sync' });
const menu = ref<HTMLDetailsElement>();
function message(e: unknown) { return e instanceof Error ? e.message : String(e); }
function focusContent() { const main = document.getElementById('main-content'); main?.focus(); main?.scrollIntoView(); }
function readLink() { const params = new URLSearchParams(location.hash.slice(1)); roundId.value = params.get('round') || ''; inviteToken.value = params.get('invite') || ''; creatorPlanId.value=params.get('draft') || ''; if(creatorPlanId.value)frame.value='creator'; }
readLink();
// A return link (#resume=…) signs the person back in, then the rest of the link opens normally.
async function consumeReturnLink() {
  const params = new URLSearchParams(location.hash.slice(1));
  const link = readReturnLink(params.get('resume'));
  if (!params.has('resume')) return;
  params.delete('resume');
  history.replaceState(null, '', params.toString() ? `/#${params}` : '/');
  if (!link) { error.value = 'That return link is incomplete. Ask for a new one or sign in again.'; return; }
  if (link.userId === auth.userID && link.token === auth.token) { readLink(); return; }
  resuming.value = true;
  try { const user = await apiService.resume(link.userId, link.token); auth.setSession({ ...user, session_token: link.token }); }
  catch { error.value = 'That return link has expired. Join again from your invitation, or ask the organiser for a new one.'; }
  finally { resuming.value = false; readLink(); }
}
void consumeReturnLink();
async function copyReturnLink() {
  try { await navigator.clipboard.writeText(returnLink(auth.userID, auth.token, roundId.value || undefined)); linkCopied.value = true; setTimeout(() => { linkCopied.value = false; }, 2400); }
  catch { error.value = 'Clipboard unavailable. Use “Show session details” to copy them manually.'; }
}
function openRound(id: string) { error.value = ''; location.hash = new URLSearchParams({ round: id }).toString(); readLink(); }
function dashboard() { error.value = ''; location.hash = ''; readLink(); frame.value = 'dashboard'; }
function navigate(next:string){ if(next==='join'){joining.value=true;return;} if(next==='creator'){removeCheckpoint(checkpointKey(auth.userID,'creator'));creatorPlanId.value='';creatorKey.value++;location.hash='';readLink();frame.value='creator';}else dashboard(); }
function openDraft(id:string){location.hash=new URLSearchParams({draft:id}).toString();readLink();frame.value='creator';}
function joinPlan(value: { round: string; invite: string }) { error.value = ''; location.hash = new URLSearchParams(value).toString(); readLink(); }
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
function onHash() { if (new URLSearchParams(location.hash.slice(1)).has('resume')) void consumeReturnLink(); else readLink(); }
onMounted(() => { readLink(); window.addEventListener('hashchange', onHash); document.addEventListener('pointerdown', outside); });
onUnmounted(() => { window.removeEventListener('hashchange', onHash); document.removeEventListener('pointerdown', outside); });
</script>
<style scoped>
.shell { --sidebar-w: 268px; display: grid; grid-template-columns: var(--sidebar-w) minmax(0, 1fr); min-height: 100dvh; transition: grid-template-columns 360ms var(--ease-out); }
.shell.collapsed { --sidebar-w: 76px; }

.sidebar { position: sticky; top: 0; height: 100dvh; display: flex; flex-direction: column; gap: 8px; padding: 18px 14px; background: var(--surface); border-right: 1px solid var(--line); z-index: 20; min-width: 0; }
.sidebar-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 48px; margin-bottom: 18px; }
.home-brand { border: 0; background: transparent; padding: 4px; min-height: 44px; border-radius: 12px; overflow: hidden; justify-content: flex-start; }
.home-brand:hover:not(:disabled) { background: transparent; color: var(--ink); }
.brand-name, .nav-label, .who { transition: opacity 200ms var(--ease-out), transform 300ms var(--ease-out); white-space: nowrap; }
.collapse-toggle { color: var(--muted); }
.collapse-toggle .ui-icon { transition: transform 360ms var(--ease-out); }

.sidebar-nav { display: grid; gap: 4px; }
.nav-item { position: relative; justify-content: flex-start; gap: 14px; width: 100%; min-height: 46px; padding: 10px 14px; border: 0; border-radius: 12px; background: transparent; color: var(--ink-2); font-weight: 600; font-size: .9375rem; text-align: left; }
.nav-item .ui-icon { color: var(--muted); transition: color var(--fast) ease-out; }
.nav-item:hover:not(:disabled) { background: var(--sky-50); color: var(--ink); }
.nav-item:hover:not(:disabled) > .ui-icon { transform: none; color: var(--blue); }
.nav-item[aria-current='page'] { background: var(--sky-100); color: var(--blue-ink); }
.nav-item[aria-current='page'] .ui-icon { color: var(--blue); }

.sidebar-foot { margin-top: auto; display: grid; gap: 4px; padding-top: 14px; border-top: 1px solid var(--line); }
.session-menu { position: relative; border: 0; }
.session-menu > summary { min-height: 52px; padding: 8px 10px; gap: 12px; border-radius: 12px; color: var(--ink); }
.session-menu > summary::before { display: none; }
.session-menu > summary:hover, .session-menu[open] > summary { background: var(--sky-50); color: var(--ink); }
.avatar { display: grid; place-items: center; width: 34px; height: 34px; flex-shrink: 0; border-radius: 50%; background: var(--night); color: #fff; font-size: .875rem; font-weight: 700; }
.who { display: grid; min-width: 0; line-height: 1.25; }
.who-name { font-size: .9375rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; }
.who-hint { font-size: .8125rem; font-weight: 400; color: var(--muted); }
.session-popover { position: absolute; left: calc(100% + 14px); bottom: 0; width: min(360px, calc(100vw - 32px)); background: var(--surface); color: var(--ink); padding: 24px; border: 1px solid var(--line); border-radius: 16px; z-index: 30; box-shadow: var(--shadow-lg); transform-origin: bottom left; }
.session-menu[open] .session-popover { animation: pop 300ms var(--ease-out); }
@keyframes pop { from { opacity: 0; transform: translateX(-6px) scale(.98); } }
.popover-title { font-size: 1.125rem; margin-bottom: 6px; }
.return-copy { width: 100%; margin-bottom: 8px; }
.raw-session { margin-top: 4px; }
.resuming { min-height: 100dvh; display: grid; place-content: center; justify-items: center; gap: 12px; color: var(--muted); }
.resuming .brand-mark { width: 44px; height: 44px; animation: pulse 1.2s ease-in-out infinite; }
.session-popover p { font-size: .9375rem; color: var(--muted); }
.session-popover label:first-of-type { margin-top: 0; }
.session-popover label { margin: 14px 0; }
.session-popover input { font-size: .875rem; }
.popover-actions { display: flex; align-items: center; gap: 12px; margin-top: 18px; }
.popover-actions [role='status'] { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
.sign-out { color: var(--muted); }

/* Collapsed rail: labels clip away, icons stay centred, tooltips name each item. */
.collapsed .sidebar { padding-inline: 12px; }
.collapsed .sidebar-top { flex-direction: column; gap: 10px; }
.collapsed .brand-name, .collapsed .nav-label, .collapsed .who { opacity: 0; transform: translateX(-6px); position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
.collapsed .collapse-toggle .ui-icon { transform: scaleX(-1); }
.collapsed .nav-item, .collapsed .session-menu > summary { justify-content: center; padding-inline: 0; }
.collapsed [data-tip]:hover::after { content: attr(data-tip); position: absolute; left: calc(100% + 12px); top: 50%; translate: 0 -50%; padding: 6px 10px; border-radius: 8px; background: var(--night); color: #fff; font-size: .8125rem; font-weight: 600; white-space: nowrap; pointer-events: none; animation: tip 200ms var(--ease-out); z-index: 40; }
.collapsed .session-menu[open] > summary::after { display: none; }
@keyframes tip { from { opacity: 0; translate: -4px -50%; } }

.main-col { min-width: 0; display: flex; flex-direction: column; }
.app-error { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin: 20px var(--gutter) 0; }
.app-error button { color: var(--danger); flex-shrink: 0; }
.app-error button:hover:not(:disabled) { background: #fbd9dd; }

/* Phones: brand and session in a top bar; navigation in a bottom tab bar. */
@media (max-width: 860px) {
  .shell, .shell.collapsed { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto 1fr; padding-bottom: calc(68px + env(safe-area-inset-bottom)); }
  .sidebar { position: sticky; height: auto; flex-direction: row; align-items: center; gap: 4px; padding: 8px 12px; border-right: 0; border-bottom: 1px solid var(--line); }
  .collapsed .sidebar { padding-inline: 12px; }
  .sidebar-top, .collapsed .sidebar-top { flex-direction: row; margin: 0; min-height: 0; flex: 1; min-width: 0; }
  .collapse-toggle { display: none; }
  .collapsed .brand-name, .collapsed .who { opacity: 1; transform: none; position: static; width: auto; height: auto; clip-path: none; overflow: visible; }
  .sidebar-nav { position: fixed; left: 0; right: 0; bottom: 0; z-index: 25; grid-auto-flow: column; grid-auto-columns: 1fr; gap: 0; padding: 6px 8px calc(6px + env(safe-area-inset-bottom)); background: rgba(255, 255, 255, .96); border-top: 1px solid var(--line); backdrop-filter: blur(8px); }
  .sidebar-nav .nav-item { flex-direction: column; justify-content: center; gap: 2px; min-height: 54px; padding: 6px 4px; font-size: .75rem; text-align: center; }
  .sidebar-nav .nav-label, .collapsed .sidebar-nav .nav-label { opacity: 1; transform: none; position: static; width: auto; height: auto; clip-path: none; overflow: visible; white-space: normal; line-height: 1.2; }
  .sidebar-nav .nav-item[aria-current='page'] { background: transparent; }
  .sidebar-nav .nav-item[aria-current='page'] .nav-label { color: var(--blue-ink); }
  .sidebar-foot { margin: 0; padding: 0; border: 0; display: flex; align-items: center; gap: 2px; }
  .session-menu { position: static; }
  .session-menu > summary, .collapsed .session-menu > summary { min-height: 44px; padding: 4px 8px; gap: 8px; justify-content: flex-start; }
  .who-name { display: none; }
  .who-hint { font-size: .875rem; font-weight: 600; color: var(--blue-ink); }
  .avatar { width: 30px; height: 30px; font-size: .8125rem; }
  .sign-out { width: 44px; padding: 10px; justify-content: center; }
  .sign-out .nav-label { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
  .session-popover { position: fixed; left: auto; right: 16px; top: 64px; bottom: auto; transform-origin: top right; }
  @keyframes pop { from { opacity: 0; transform: translateY(-6px) scale(.98); } }
  [data-tip]:hover::after { display: none; }
}
@media (max-width: 400px) {
  .brand-name { display: none; }
  .session-popover { right: 16px; left: 16px; width: auto; }
}
</style>
