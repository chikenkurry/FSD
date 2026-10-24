<template>
  <div v-if="invited" class="invite-page">
    <aside class="invite-side">
      <span class="brand on-dark"><BrandMark />What to do?</span>
      <div class="invite-side-body">
        <p class="invite-side-title">Someone wants your view on a group decision.</p>
        <ol class="mini-route">
          <li class="rise" style="--i: 2"><span class="stop" aria-hidden="true"></span><div><strong>Tell them who you are</strong><span>Just a name. No account.</span></div></li>
          <li class="rise" style="--i: 3"><span class="stop" aria-hidden="true"></span><div><strong>See the options</strong><span>With the facts the organiser checked.</span></div></li>
          <li class="rise" style="--i: 4"><span class="stop" aria-hidden="true"></span><div><strong>Answer privately</strong><span>The group only sees the combined result.</span></div></li>
        </ol>
      </div>
    </aside>
    <main class="invite-main" id="main-content">
      <section class="invite-card rise" aria-labelledby="invite-heading">
        <h1 id="invite-heading">Help your group decide</h1>
        <p class="muted">Tell everyone who you are, then you’ll see the options and answer a few short questions.</p>
        <Transition name="reveal"><p v-if="error" role="alert" class="error-banner">{{ error }}</p></Transition>
        <form @submit.prevent="create" :aria-busy="busy">
          <label>Your name<input v-model="name" required maxlength="255" autocomplete="nickname" placeholder="The name your group knows" autofocus /></label>
          <button class="btn-primary btn-wide" :disabled="busy || !name.trim()">{{ busy ? 'Joining…' : 'Continue' }}<UiIcon name="arrow" /></button>
        </form>
        <p class="session-note"><UiIcon name="lock" />No account needed. Your answers stay private to you.</p>
        <details><summary>I’ve joined before on another device</summary><form @submit.prevent="resume">
          <p class="helper-text">Paste copied session details into either field, or enter them below.</p>
          <label>User ID<input v-model="id" @input="parseSession" required autocomplete="off" /></label>
          <label>Session token<input v-model="token" @input="parseSession" type="password" required autocomplete="off" /></label>
          <button :disabled="busy">Resume session<UiIcon name="arrow" /></button>
        </form></details>
      </section>
    </main>
  </div>

  <div v-else ref="page" class="landing">
    <header class="landing-bar">
      <span class="brand"><BrandMark />What to do?</span>
      <nav class="landing-links" aria-label="Page">
        <a href="#how" @click.prevent="scrollTo('how')">How it works</a>
        <button class="btn-small" @click="openResume">Resume a session</button>
      </nav>
    </header>

    <main id="main-content" tabindex="-1">
      <section class="hero" aria-labelledby="welcome-heading">
        <div class="hero-copy">
          <h1 id="welcome-heading" class="headline"><span class="line"><span>Different preferences.</span></span><span class="line"><span>One shared plan.</span></span></h1>
          <p class="hero-lede">Bring the options, hear from everyone in private, and land on a choice your group can move forward with.</p>

          <div class="quick" aria-labelledby="quick-heading">
            <h2 id="quick-heading" class="sr-only">Get started</h2>
            <div class="tabs" role="tablist" aria-label="Get started" :style="{ '--tab': mode === 'start' ? 0 : 1 }">
              <button id="tab-start" role="tab" :aria-selected="mode === 'start'" aria-controls="panel-start" :tabindex="mode === 'start' ? 0 : -1" @click="mode = 'start'" @keydown.right.prevent="switchTab('join')">Start a plan</button>
              <button id="tab-join" role="tab" :aria-selected="mode === 'join'" aria-controls="panel-join" :tabindex="mode === 'join' ? 0 : -1" @click="mode = 'join'" @keydown.left.prevent="switchTab('start')">Join with a link</button>
              <span class="tab-ink" aria-hidden="true"></span>
            </div>
            <Transition name="swap" mode="out-in">
              <div v-if="mode === 'start'" id="panel-start" key="start" role="tabpanel" aria-labelledby="tab-start" class="quick-panel">
                <Transition name="reveal"><p v-if="error" role="alert" class="error-banner">{{ error }}</p></Transition>
                <form class="inline-form" @submit.prevent="create" :aria-busy="busy">
                  <label>Your display name<input ref="nameField" v-model="name" required maxlength="255" autocomplete="nickname" placeholder="The name your group knows" /></label>
                  <button class="btn-primary" :disabled="busy">{{ busy ? 'Connecting…' : 'Create guest session' }}<UiIcon name="arrow" /></button>
                </form>
                <p class="session-note"><UiIcon name="lock" />No account or password. Copy your session details later to return on another device.</p>
              </div>
              <div v-else id="panel-join" key="join" role="tabpanel" aria-labelledby="tab-join" class="quick-panel">
                <form class="inline-form" @submit.prevent="joinLink">
                  <label>Paste your invitation link<input ref="linkField" v-model="link" autocomplete="off" spellcheck="false" placeholder="https://…/#round=…&invite=…" :aria-invalid="linkError ? 'true' : undefined" /></label>
                  <button class="btn-primary" :disabled="!link.trim()">Open invitation<UiIcon name="arrow" /></button>
                </form>
                <p v-if="linkError" class="field-error">{{ linkError }}</p>
                <p v-else class="session-note"><UiIcon name="link" />You’ll add your name on the next screen, then see the options.</p>
              </div>
            </Transition>
            <details ref="resumeBox" class="resume"><summary>Resume an existing session</summary><form @submit.prevent="resume">
              <p class="helper-text">Paste copied session details into either field, or enter them below.</p>
              <div class="resume-fields">
                <label>User ID<input v-model="id" @input="parseSession" required autocomplete="off" /></label>
                <label>Session token<input v-model="token" @input="parseSession" type="password" required autocomplete="off" /></label>
              </div>
              <button :disabled="busy">Resume session<UiIcon name="arrow" /></button>
            </form></details>
          </div>
        </div>
        <div class="hero-visual">
          <LandingBoard />
        </div>
      </section>

      <section id="how" class="route-section" aria-labelledby="how-heading">
        <div class="section-head reveal-block">
          <h2 id="how-heading">From “what should we do?” to a confirmed plan</h2>
          <p>One route for every decision, whether it’s a team offsite or Saturday dinner.</p>
        </div>
        <ol :class="['route', { drawn: routeDrawn }]" ref="route">
          <li v-for="(stop, i) in stops" :key="stop.title" :style="{ '--i': i }">
            <span class="stop" aria-hidden="true"></span>
            <h3>{{ stop.title }}</h3>
            <p>{{ stop.text }}</p>
          </li>
        </ol>
      </section>

      <section class="principles" aria-label="What you can rely on">
        <div v-for="(item, i) in principles" :key="item.title" class="principle reveal-block" :style="{ '--i': i }">
          <h3>{{ item.title }}</h3>
          <p>{{ item.text }}</p>
        </div>
      </section>

      <section class="closing" aria-labelledby="closing-heading">
        <h2 id="closing-heading">Your group’s next plan starts with one name.</h2>
        <div class="closing-actions">
          <button class="btn-primary on-dark" @click="startHere">Start a plan<UiIcon name="arrow" /></button>
          <button class="btn-quiet on-dark-quiet" @click="joinHere">I have an invitation link</button>
        </div>
      </section>
    </main>
    <footer class="landing-foot"><span class="brand"><BrandMark />What to do?</span><span>Clear options. Considered decisions.</span></footer>
  </div>
</template>
<script setup lang="ts">
import BrandMark from './BrandMark.vue';
import UiIcon from './UiIcon.vue';
import LandingBoard from './LandingBoard.vue';
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { apiService } from '@/services/api';
import { parseInvite } from '@/services/invite';
defineProps<{ invited?: boolean }>();
const emit = defineEmits<{ (e: 'navigate', frame: string): void }>();
const auth = useAuthStore();
const name = ref(''); const id = ref(''); const token = ref(''); const error = ref(''); const busy = ref(false);
const mode = ref<'start' | 'join'>('start'); const link = ref(''); const linkError = ref('');
const page = ref<HTMLElement>(); const route = ref<HTMLElement>(); const resumeBox = ref<HTMLDetailsElement>();
const nameField = ref<HTMLInputElement>(); const linkField = ref<HTMLInputElement>(); const routeDrawn = ref(false);
const stops = [
  { title: 'Set out the options', text: 'Name what you’re deciding. Research drafts an overview and the facts for each option, and you correct anything off.' },
  { title: 'Everyone answers privately', text: 'Members share preferences and must-haves on their phone in a few minutes. Nobody sees anyone else’s answers.' },
  { title: 'Compare the ranking', text: 'Options are ranked against confirmed answers, with requirements ruling out what can’t work.' },
  { title: 'Confirm and RSVP', text: 'Confirm the choice. The group says who’s going, and it lands in their calendar.' },
];
const principles = [
  { title: 'Private by default', text: 'Individual answers and notes stay with the person who wrote them. The group sees the combined result.' },
  { title: 'Facts with their source', text: 'AI estimates and third-party details are labelled with where they came from, and the organiser can correct them.' },
  { title: 'Works where your group is', text: 'The same flow on a phone in a group chat or a laptop in a meeting room. Formal or informal, it fits.' },
];
function parseSession(event?: Event) {
  const candidate = event ? (event.target as HTMLInputElement).value.trim() : id.value.trim();
  if (!candidate.startsWith('{')) return;
  try {
    const parsed = JSON.parse(candidate) as { user_id?: string; session_token?: string };
    if (typeof parsed.user_id === 'string' && typeof parsed.session_token === 'string') {
      id.value = parsed.user_id.trim();
      token.value = parsed.session_token.trim();
    }
  } catch { /* plain text input */ }
}
async function create() { await act(async () => auth.setSession(await apiService.register(name.value.trim()))); }
async function resume() { parseSession(); await act(async () => { const user = await apiService.resume(id.value.trim(), token.value.trim()); auth.setSession({ ...user, session_token: token.value.trim() }); }); }
async function act(fn: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true; error.value = '';
  try { await fn(); emit('navigate', 'dashboard'); } catch(e) { error.value = e instanceof Error ? e.message : 'Unable to connect'; }
  finally { busy.value = false; }
}
// The invitation page takes over once the hash carries the round and token.
function joinLink() {
  const parsed = parseInvite(link.value);
  if (!parsed) { linkError.value = 'That doesn’t look like an invitation link. It should contain “round=” and “invite=”.'; return; }
  linkError.value = ''; location.hash = new URLSearchParams(parsed).toString();
}
async function switchTab(next: 'start' | 'join') { mode.value = next; await nextTick(); document.getElementById(`tab-${next}`)?.focus(); }
function scrollTo(target: string) { document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
async function focusField(next: 'start' | 'join') {
  mode.value = next; window.scrollTo({ top: 0, behavior: 'smooth' });
  await nextTick(); setTimeout(() => (next === 'start' ? nameField : linkField).value?.focus({ preventScroll: true }), 420);
}
function startHere() { void focusField('start'); }
function joinHere() { void focusField('join'); }
function openResume() { if (resumeBox.value) { resumeBox.value.open = true; resumeBox.value.scrollIntoView({ behavior: 'smooth', block: 'center' }); resumeBox.value.querySelector('summary')?.focus({ preventScroll: true }); } }

// Sections settle into place once as they enter the viewport; content stays visible without script.
let observer: IntersectionObserver | undefined;
onMounted(() => {
  nameField.value?.focus({ preventScroll: true });
  if (!page.value || typeof IntersectionObserver !== 'function') { routeDrawn.value = true; return; }
  page.value.classList.add('motion-ready');
  observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      if (entry.target === route.value) routeDrawn.value = true;
      entry.target.classList.add('in-view'); observer?.unobserve(entry.target);
    }
  }, { threshold: .25, rootMargin: '0px 0px -8% 0px' });
  page.value.querySelectorAll('.reveal-block').forEach(el => observer!.observe(el));
  if (route.value) observer.observe(route.value);
});
onBeforeUnmount(() => observer?.disconnect());
</script>
<style scoped>
/* ---------- Landing ---------- */
.landing { min-height: 100dvh; background: var(--ground); overflow-x: clip; }
.landing-bar { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 20px var(--gutter); }
.landing-links { display: flex; align-items: center; gap: 20px; font-size: .9375rem; font-weight: 600; }
.landing-links a { color: var(--ink-2); text-decoration: none; }
.landing-links a:hover { color: var(--blue); }

.hero { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 6fr); gap: clamp(32px, 5vw, 96px); align-items: center; padding: clamp(24px, 5vh, 72px) var(--gutter) clamp(56px, 9vh, 112px); min-height: calc(100dvh - 88px); }
.headline { font-size: clamp(2.75rem, 1.6rem + 3.6vw, 5.25rem); font-weight: 300; line-height: 1.02; letter-spacing: -.035em; margin-bottom: 24px; color: var(--night); }
.headline .line { display: block; overflow: hidden; padding-bottom: .06em; }
.headline .line > span { display: block; animation: line-up 1100ms var(--ease-out) both; }
.headline .line:nth-child(2) > span { animation-delay: 140ms; font-weight: 600; color: var(--blue); }
@keyframes line-up { from { transform: translateY(105%); } }
.hero-lede { font-size: clamp(1.125rem, 1rem + .4vw, 1.3125rem); color: var(--ink-2); max-width: 46ch; margin-bottom: 36px; animation: fade-up 900ms 360ms var(--ease-out) both; }
@keyframes fade-up { from { opacity: 0; transform: translateY(14px); } }

.quick { max-width: 560px; background: var(--surface); border-radius: 20px; padding: 8px 24px 6px; box-shadow: var(--shadow-md); animation: fade-up 900ms 520ms var(--ease-out) both; }
.tabs { position: relative; display: grid; grid-template-columns: 1fr 1fr; border-bottom: 1px solid var(--line); margin: 0 -24px; padding: 0 24px; }
.tabs [role='tab'] { border: 0; border-radius: 0; background: transparent; min-height: 54px; color: var(--muted); font-size: 1rem; }
.tabs [role='tab']:hover:not(:disabled) { color: var(--ink); }
.tabs [role='tab'][aria-selected='true'] { color: var(--blue-ink); }
.tabs [role='tab']:active:not(:disabled) { transform: none; }
.tab-ink { position: absolute; left: 24px; bottom: -1px; width: calc((100% - 48px) / 2); height: 3px; border-radius: 3px 3px 0 0; background: var(--blue); transform: translateX(calc(var(--tab) * 100%)); transition: transform 420ms var(--ease-out); }
.quick-panel { padding: 6px 0 2px; }
.quick-panel > .error-banner { margin: 16px 0 0; }
.inline-form { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: 12px; }
.inline-form label { margin: 18px 0 0; }
.inline-form button { min-height: 48px; }
.session-note { display: flex; gap: 8px; align-items: flex-start; font-size: .875rem; color: var(--muted); margin: 14px 0 12px; }
.session-note .ui-icon { width: 17px; height: 17px; margin-top: 2px; }
.field-error { color: var(--danger); font-size: .875rem; margin: 12px 0; }
.resume { margin: 0 -24px; padding: 0 24px; }
.resume summary { min-height: 52px; font-size: .9375rem; }
.resume form { padding-bottom: 18px; }
.resume-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
.resume-fields label { margin: 14px 0; }

.hero-visual { position: relative; }
.hero-visual::before { content: ''; position: absolute; inset: -9% -100vw -9% 9%; background: var(--sky-100); border-radius: 32px 0 0 32px; z-index: 0; transform-origin: right; animation: field-in 1400ms var(--ease-out) both; }
@keyframes field-in { from { transform: scaleX(.6); opacity: 0; } }
.hero-visual > * { position: relative; z-index: 1; animation: board-in 1200ms 260ms var(--ease-out) both; }
@keyframes board-in { from { opacity: 0; transform: translateY(32px) scale(.98); } }

/* Route: the decision as a line with stops, drawn once on arrival. */
.route-section { padding: clamp(64px, 10vh, 128px) var(--gutter); background: var(--surface); }
.section-head { max-width: 760px; margin-bottom: 56px; }
.section-head h2 { font-size: clamp(1.875rem, 1.3rem + 1.8vw, 3rem); font-weight: 300; letter-spacing: -.025em; line-height: 1.1; color: var(--night); }
.section-head p { color: var(--muted); font-size: 1.125rem; }
.route { --line-y: 13px; position: relative; list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 32px; }
.route::before, .route::after { content: ''; position: absolute; left: 0; right: 0; top: var(--line-y); height: 3px; border-radius: 3px; background: var(--sky-100); }
.route::after { background: var(--blue); transform-origin: left; transform: scaleX(0); transition: transform 1800ms var(--ease-io); }
.route.drawn::after { transform: scaleX(1); }
.route li { position: relative; z-index: 1; padding-right: 8px; }
.route .stop { display: block; width: 29px; height: 29px; margin-bottom: 22px; border-radius: 50%; background: var(--surface); border: 3px solid var(--sky-200); transition: border-color 300ms ease-out, background-color 300ms ease-out, transform 500ms var(--ease-out); transition-delay: calc(var(--i) * 420ms + 200ms); }
.route.drawn .stop { border-color: var(--blue); transform: scale(1.04); }
.route li:last-child .stop { transition-delay: calc(var(--i) * 420ms + 200ms); }
.route.drawn li:last-child .stop { background: var(--blue); box-shadow: inset 0 0 0 5px #fff; }
.route h3 { font-size: 1.25rem; margin-bottom: 8px; }
.route p { color: var(--muted); font-size: 1rem; }
.route li h3, .route li p { transition: opacity 600ms var(--ease-out), transform 600ms var(--ease-out); transition-delay: calc(var(--i) * 420ms + 260ms); }
.motion-ready .route:not(.drawn) li h3, .motion-ready .route:not(.drawn) li p { opacity: 0; transform: translateY(10px); }

.principles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: clamp(24px, 4vw, 64px); padding: clamp(56px, 9vh, 112px) var(--gutter); }
.principle { padding-top: 22px; border-top: 2px solid var(--night); }
.principle h3 { font-size: 1.25rem; }
.principle p { color: var(--ink-2); }
.reveal-block { transition: opacity 700ms var(--ease-out), transform 700ms var(--ease-out); transition-delay: calc(var(--i, 0) * 110ms); }
.motion-ready .reveal-block:not(.in-view) { opacity: 0; transform: translateY(18px); }

.closing { display: flex; align-items: flex-end; justify-content: space-between; gap: 32px; flex-wrap: wrap; margin: 0 var(--gutter); padding: clamp(40px, 7vh, 80px) clamp(28px, 4vw, 64px); background: var(--night); color: #fff; border-radius: 28px; }
.closing h2 { font-size: clamp(1.875rem, 1.2rem + 2vw, 3.25rem); font-weight: 300; letter-spacing: -.025em; line-height: 1.08; max-width: 18ch; margin: 0; }
.closing-actions { display: flex; gap: 12px; flex-wrap: wrap; }
.on-dark { background: #fff; border-color: #fff; color: var(--night); }
.on-dark:hover:not(:disabled) { background: var(--sky-100); border-color: var(--sky-100); color: var(--night); }
.on-dark-quiet { color: #cfe0fb; }
.on-dark-quiet:hover:not(:disabled) { color: #fff; background: rgba(255, 255, 255, .1); }
.landing-foot { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; padding: 36px var(--gutter) 44px; color: var(--muted); font-size: .9375rem; }

/* ---------- Invitation ---------- */
.invite-page { min-height: 100dvh; display: grid; grid-template-columns: minmax(320px, 5fr) minmax(0, 7fr); background: var(--ground); }
.invite-side { display: flex; flex-direction: column; gap: 48px; padding: 32px clamp(28px, 4vw, 64px); background: var(--night); color: #fff; }
.brand.on-dark { color: #fff; }
.invite-side-body { margin: auto 0; }
.invite-side-title { font-size: clamp(1.75rem, 1.2rem + 1.6vw, 2.75rem); font-weight: 300; line-height: 1.12; letter-spacing: -.02em; margin-bottom: 40px; max-width: 16ch; animation: fade-up 900ms var(--ease-out) both; }
.mini-route { position: relative; list-style: none; margin: 0; padding: 0; display: grid; gap: 26px; }
.mini-route::before { content: ''; position: absolute; left: 8px; top: 10px; bottom: 10px; width: 2px; background: rgba(255, 255, 255, .22); transform-origin: top; animation: draw-down 1400ms 300ms var(--ease-io) both; }
@keyframes draw-down { from { transform: scaleY(0); } }
.mini-route li { position: relative; display: flex; gap: 18px; }
.mini-route .stop { width: 18px; height: 18px; flex-shrink: 0; margin-top: 3px; border-radius: 50%; background: var(--night); border: 2px solid #6fa2ff; }
.mini-route div { display: grid; }
.mini-route strong { font-size: 1.0625rem; }
.mini-route div span { color: #b9cdf0; font-size: .9375rem; }
.invite-main { display: grid; place-items: center; padding: 48px var(--gutter); }
.invite-card { width: 100%; max-width: 500px; background: var(--surface); padding: 40px; border-radius: 20px; box-shadow: var(--shadow-md); }
.invite-card h1 { margin-bottom: 10px; }
.invite-card label > input { font-size: 1.0625rem; min-height: 52px; }
.btn-wide { width: 100%; min-height: 52px; justify-content: space-between; padding-inline: 24px; font-size: 1.0625rem; }
.invite-card details { margin-top: 4px; }
.invite-card details button { margin-bottom: 8px; }

@media (max-width: 1080px) {
  .hero { grid-template-columns: minmax(0, 1fr); min-height: 0; gap: 56px; }
  .hero-visual::before { inset: -40px -100vw -40px 6%; }
  .quick { max-width: 640px; }
  .route { grid-template-columns: repeat(2, minmax(0, 1fr)); row-gap: 48px; }
  .route::before, .route::after { display: none; }
}
@media (max-width: 760px) {
  .landing-links a { display: none; }
  .hero { padding-top: 12px; gap: 48px; }
  .quick { padding: 6px 18px 4px; border-radius: 18px; }
  .tabs, .resume { margin: 0 -18px; padding: 0 18px; }
  .tab-ink { left: 18px; width: calc((100% - 36px) / 2); }
  .tabs [role='tab'] { font-size: .9375rem; }
  .inline-form, .resume-fields { grid-template-columns: minmax(0, 1fr); }
  .inline-form label { margin-bottom: 0; }
  .inline-form button { width: 100%; justify-content: space-between; padding-inline: 22px; }
  .route { grid-template-columns: minmax(0, 1fr); row-gap: 0; padding-left: 4px; }
  .route li { display: grid; grid-template-columns: 29px minmax(0, 1fr); column-gap: 20px; padding-bottom: 32px; }
  .route li::before { content: ''; position: absolute; left: 13px; top: 30px; bottom: 0; width: 3px; background: var(--sky-100); }
  .route li:last-child::before { display: none; }
  .route .stop { grid-row: 1 / 3; margin: 0; }
  .principles { grid-template-columns: minmax(0, 1fr); }
  .closing { margin: 0 16px; border-radius: 22px; }
  .closing-actions, .closing-actions button { width: 100%; }
  .invite-page { grid-template-columns: minmax(0, 1fr); }
  .invite-side { gap: 24px; padding: 20px; }
  .invite-side-title { font-size: 1.5rem; margin-bottom: 0; }
  .mini-route { display: none; }
  .invite-main { padding: 16px 16px 40px; place-items: start center; }
  .invite-card { padding: 26px 22px; }
}
</style>
