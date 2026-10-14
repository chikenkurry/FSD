<template>
  <div class="auth-wrapper">
    <div class="auth-card">
      <h2 class="auth-title">What to do?</h2>

      <div v-if="hasError" class="error-banner">
        username or password is wrong
      </div>

      <form @submit.prevent="handleLogin">
        <div class="input-group">
          <label>Username</label>
          <input type="text" v-model="form.username" placeholder="username" :class="{ 'input-error': hasError }"
            @input="clearError" required />
        </div>

        <div class="input-group">
          <label>Password</label>
          <div class="password-field-wrapper">
            <input :type="showPassword ? 'text' : 'password'" v-model="form.password" 
            placeholder="password"
            :class="{ 'input-error': hasError}"
            @input="clearError" required />
            <span class="eye-icon" @click="showPassword = !showPassword">👁</span>
          </div>
          <small class="helper-text">It must be a combination of minimum 8 letters, numbers, and symbols.</small>
        </div>

        <div class="auth-options">
          <label class="checkbox-label">
            <input type="checkbox" v-model="form.rememberMe" /> Remember me
          </label>
          <a href="#" class="forgot-link" @click.prevent>Forgot Password?</a>
        </div>

        <button type="submit" class="btn-primary" :disabled="isLoading">
          {{ isLoading ? 'Logging in..' : 'Log in' }}</button>
      </form>

      <div class="signup-footer">
        <span>No account yet? <a href="#" @click.prevent="emit('navigate', 'dashboard')">Sign Up</a></span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue';
import { useAuthStore } from '@/stores/auth';
import type { LoginPayload } from '@/types/form';
import { apiService } from '@/services/api';

const emit = defineEmits<{
  (e: 'navigate', frame: string): void;
}>();

const authStore = useAuthStore()

const form = reactive<LoginPayload>({
  username: '',
  password: '',
  rememberMe: false
});

const handleLogin = async (): Promise<void> => {
  try {
    const response = await apiService.fakeLogin(form.username);

    // save logged in user ID to pinia
    authStore.setUser(response.id);
    emit('navigate', 'dashboard')
  } catch (error) {
    console.error('Login error: ', error)
    hasError.value = true;
  } finally {
    isLoading.value = false;
  }
};

const showPassword = ref<boolean>(false);
const hasError = ref<boolean>(false);
const isLoading = ref<boolean>(false);

// reset error highlighting with user types
const clearError = () => {
  if (hasError.value) {
    hasError.value = false;
  }
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