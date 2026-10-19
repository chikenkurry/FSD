<template>
  <div class="auth-wrapper"><div class="auth-card">
    <h2 class="auth-title">What to do?</h2>
    <p>Create a guest session to plan or join a group. Keep your session details to return on another device.</p>
    <p v-if="error" role="alert" class="error-banner">{{ error }}</p>
    <form @submit.prevent="create">
      <label>Your display name<input v-model="name" required maxlength="255" autocomplete="nickname" /></label>
      <button class="btn-primary" :disabled="busy">{{ busy ? 'Connecting…' : 'Create guest session' }}</button>
    </form>
    <details><summary>Resume an existing session</summary><form @submit.prevent="resume">
      <label>User ID<input v-model="id" required autocomplete="off" /></label>
      <label>Session token<input v-model="token" type="password" required autocomplete="off" /></label>
      <button class="btn-primary" :disabled="busy">Resume session</button>
    </form></details>
  </div></div>
</template>
<script setup lang="ts">
import { ref } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { apiService } from '@/services/api';
const emit = defineEmits<{ (e: 'navigate', frame: string): void }>();
const auth = useAuthStore();
const name = ref(''); const id = ref(''); const token = ref(''); const error = ref(''); const busy = ref(false);
async function create() { await act(async () => auth.setSession(await apiService.register(name.value))); }
async function resume() { await act(async () => { const user = await apiService.resume(id.value, token.value); auth.setSession({ ...user, session_token: token.value }); }); }
async function act(fn: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true; error.value = '';
  try { await fn(); emit('navigate', 'dashboard'); } catch(e) { error.value = e instanceof Error ? e.message : 'Unable to connect'; }
  finally { busy.value = false; }
}
</script>
<style scoped>
.auth-wrapper {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 85vh;
}

.auth-card {
  background: white;
  padding: 40px;
  border-radius: 8px;
  width: 100%;
  max-width: 440px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
}

.auth-title {
  margin-bottom: 24px;
  font-size: 1.5rem;
  font-weight: bold;
}

.error-banner {
  background-color: #FED7D7;
  color: #C53030;
  border: 1px solid #FEB2B2;
  padding: 10px 14px;
  border-radius: 6px;
  margin-bottom: 18px;
  font-size: 0.875rem;
  font-weight: 600;
}

.input-group {
  display: flex;
  flex-direction: column;
  margin-bottom: 16px;
}

.input-group label {
  font-weight: 600;
  margin-bottom: 6px;
  font-size: 0.9rem;
}

.input-group input {
  padding: 10px;
  border: 1px solid #CBD5E0;
  border-radius: 6px;
  width: 100%;
  box-sizing: border-box;
}

/* Red border highlighting for errors */
.input-group input.input-error {
  border-color: #E53E3E !important;
  background-color: #FFF5F5;
}

.password-field-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.eye-icon {
  position: absolute;
  right: 12px;
  cursor: pointer;
  color: #718096;
}

.helper-text {
  font-size: 0.75rem;
  color: #718096;
  margin-top: 6px;
}

.auth-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 16px 0 24px 0;
  font-size: 0.9rem;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.forgot-link {
  color: #3182CE;
  text-decoration: none;
}

.btn-primary {
  width: 100%;
  background-color: #3182CE;
  color: white;
  border: none;
  padding: 12px;
  border-radius: 6px;
  font-weight: bold;
  cursor: pointer;
}

.btn-primary:hover {
  background-color: #2B6CB0;
}

.signup-footer {
  margin-top: 24px;
  text-align: left;
  font-size: 0.9rem;
}

.signup-footer a {
  color: #2D3748;
  font-weight: 600;
  text-decoration: none;
}
</style>