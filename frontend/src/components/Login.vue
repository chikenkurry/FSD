<template>
  <div v-if="invited" class="auth-page invite-page">
    <header class="auth-header"><span class="brand"><BrandMark />What to do?</span></header>
    <main class="invite-wrapper" id="main-content">
      <section class="invite-card rise" aria-labelledby="invite-heading">
        <p class="eyebrow">You’ve been invited</p>
        <h1 id="invite-heading">Help your group decide</h1>
        <p class="muted">Tell everyone who you are, then you’ll see the options and answer a few short questions.</p>
        <Transition name="reveal"><p v-if="error" role="alert" class="error-banner">{{ error }}</p></Transition>
        <form @submit.prevent="create" :aria-busy="busy">
          <label>Your name<input v-model="name" required maxlength="255" autocomplete="nickname" placeholder="The name your group knows" autofocus /></label>
          <button class="btn-primary btn-join" :disabled="busy || !name.trim()">{{ busy ? 'Joining…' : 'Continue' }}<UiIcon name="arrow" /></button>
        </form>
        <p class="session-note"><UiIcon name="lock" />No account needed. Your answers stay private to you.</p>
        <details><summary>I’ve joined before on another device</summary><form @submit.prevent="resume">
          <label>User ID<input v-model="id" required autocomplete="off" /></label>
          <label>Session token<input v-model="token" type="password" required autocomplete="off" /></label>
          <button :disabled="busy">Resume session<UiIcon name="arrow" /></button>
        </form></details>
      </section>
    </main>
  </div>
  <div v-else class="auth-page">
    <header class="auth-header"><span class="brand"><BrandMark />What to do?</span><span class="auth-caption">A place to decide together.</span></header>
    <main class="auth-wrapper" id="main-content">
      <section class="auth-intro rise" aria-labelledby="welcome-heading">
        <h1 id="welcome-heading">Different preferences.<br />One shared plan.</h1>
        <p>Bring the options, hear from everyone, and find a decision your group can move forward with.</p>
        <ol class="intro-steps">
          <li class="rise" style="--i: 2"><span>1</span><div><strong>Set out the options</strong><p>Define what you’re deciding and the facts that matter.</p></div></li>
          <li class="rise" style="--i: 3"><span>2</span><div><strong>Give everyone a voice</strong><p>Collect preferences and review individual requirements.</p></div></li>
          <li class="rise" style="--i: 4"><span>3</span><div><strong>Agree on what’s next</strong><p>Compare the results, confirm a choice, and gather RSVPs.</p></div></li>
        </ol>
        <p class="context-note">For teams, organisations, and the people you make plans with.</p>
      </section>
      <section class="auth-card rise" style="--i: 1" aria-labelledby="session-heading">
        <h2 id="session-heading">Start with your name</h2>
        <p class="muted">Create a guest session to organise a plan or respond to an invitation.</p>
        <Transition name="reveal"><p v-if="error" role="alert" class="error-banner">{{ error }}</p></Transition>
        <form @submit.prevent="create" :aria-busy="busy">
          <label>Your display name<input v-model="name" required maxlength="255" autocomplete="nickname" placeholder="The name your group knows" autofocus /></label>
          <button class="btn-primary" :disabled="busy">{{ busy ? 'Connecting…' : 'Create guest session' }}<UiIcon name="arrow" /></button>
        </form>
        <p class="session-note"><UiIcon name="lock" />Keep your session details to return on another device.</p>
        <details><summary>Resume an existing session</summary><form @submit.prevent="resume">
          <label>User ID<input v-model="id" required autocomplete="off" /></label>
          <label>Session token<input v-model="token" type="password" required autocomplete="off" /></label>
          <button :disabled="busy">Resume session<UiIcon name="arrow" /></button>
        </form></details>
      </section>
    </main>
    <footer class="auth-footer">Clear options. Considered decisions.</footer>
  </div>
</template>
<script setup lang="ts">
import BrandMark from './BrandMark.vue';
import UiIcon from './UiIcon.vue';
import { ref } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { apiService } from '@/services/api';
defineProps<{ invited?: boolean }>();
const emit = defineEmits<{ (e: 'navigate', frame: string): void }>();
const auth = useAuthStore();
const name = ref(''); const id = ref(''); const token = ref(''); const error = ref(''); const busy = ref(false);
async function create() { await act(async () => auth.setSession(await apiService.register(name.value.trim()))); }
async function resume() { await act(async () => { const user = await apiService.resume(id.value, token.value); auth.setSession({ ...user, session_token: token.value }); }); }
async function act(fn: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true; error.value = '';
  try { await fn(); emit('navigate', 'dashboard'); } catch(e) { error.value = e instanceof Error ? e.message : 'Unable to connect'; }
  finally { busy.value = false; }
}
</script>
<style scoped>
.auth-page { min-height: 100dvh; display: flex; flex-direction: column; }
.auth-header { padding: 28px 5vw; display: flex; align-items: center; justify-content: space-between; color: var(--navy); }
.auth-caption { font-size: .8125rem; color: var(--muted); }
.auth-wrapper { width: 100%; max-width: 1200px; margin: auto; padding: 64px 48px; display: grid; grid-template-columns: 1.2fr 1fr; gap: 100px; align-items: start; }
.auth-intro { padding-top: 12px; }
.auth-intro h1 { font-size: 2.75rem; line-height: 1.15; font-weight: 600; margin-bottom: 24px; }
.auth-intro > p { color: var(--muted); font-size: 1.0625rem; }
.intro-steps { list-style: none; margin: 36px 0; padding: 0; }
.intro-steps li { display: flex; align-items: flex-start; gap: 18px; padding: 16px 0; }
.intro-steps li > span { display: grid; place-items: center; width: 28px; height: 28px; border: 1px solid #aabbb1; border-radius: 50%; color: var(--accent); font-size: .75rem; flex-shrink: 0; }
.intro-steps strong { font-weight: 600; }
.intro-steps p { color: var(--muted); font-size: .875rem; margin: 4px 0 0; }
.auth-intro .context-note { font-size: .8125rem; padding-top: 20px; border-top: 1px solid var(--line); }
.auth-card { background: var(--surface); box-shadow: 0 1px 2px rgba(24, 46, 59, .04), 0 12px 32px -20px rgba(24, 46, 59, .18); padding: 36px; border: 1px solid var(--line); border-radius: 12px; }
.auth-card h2 { font-size: 1.5rem; }
.auth-card > p { font-size: .875rem; }
.auth-card form > button { width: 100%; margin-top: 8px; justify-content: space-between; }
.auth-card .session-note { font-size: .75rem; color: var(--muted); display: flex; gap: 8px; align-items: flex-start; margin: 20px 0 24px; }
.session-note .ui-icon { width: 16px; height: 16px; margin-top: 2px; }
.auth-card summary { padding: 20px 0 0; }
.invite-wrapper { flex: 1; display: grid; place-items: start center; padding: 48px 20px 64px; }
.invite-card { width: 100%; max-width: 480px; background: var(--surface); padding: 40px; border: 1px solid var(--line); border-radius: 14px; box-shadow: 0 1px 2px rgba(24, 46, 59, .04), 0 16px 40px -24px rgba(24, 46, 59, .22); }
.invite-card .eyebrow { font-size: .8125rem; font-weight: 600; color: var(--accent); margin-bottom: 8px; }
.invite-card h1 { font-size: 1.875rem; margin-bottom: 10px; }
.invite-card label > input { font-size: 1.0625rem; min-height: 52px; }
.btn-join { width: 100%; min-height: 50px; justify-content: space-between; font-size: 1rem; }
.invite-card .session-note { font-size: .75rem; color: var(--muted); display: flex; gap: 8px; align-items: flex-start; margin: 20px 0 24px; }
.invite-card summary { padding: 20px 0 0; }
.auth-footer { text-align: center; color: var(--muted); font-size: .75rem; padding: 24px; }
@media(max-width: 1000px) { .auth-wrapper { gap: 48px; padding: 48px 32px; } .auth-intro h1 { font-size: 2.25rem; } }
@media(max-width: 700px) { .invite-wrapper { padding: 16px 16px 40px; } .invite-card { padding: 26px 22px; } .invite-card h1 { font-size: 1.5rem; } .auth-header { padding: 20px; } .auth-caption { display: none; } .auth-wrapper { grid-template-columns: 1fr; gap: 28px; padding: 24px 20px; } .auth-intro { padding: 0; } .auth-intro h1 { font-size: 2rem; margin-bottom: 16px; } .intro-steps, .context-note { display: none; } .auth-intro > p { font-size: .9375rem; margin: 0; } .auth-card { padding: 24px; } .auth-card h2 { font-size: 1.25rem; } }
</style>
