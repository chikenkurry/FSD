import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { Session } from '@/types/form';

export const useAuthStore = defineStore('auth', () => {
  const userID = ref(sessionStorage.getItem('user_id') || '');
  const username = ref(sessionStorage.getItem('username') || '');
  const token = ref(sessionStorage.getItem('session_token') || '');
  function setSession(session: Session) {
    userID.value = session.id; username.value = session.username; token.value = session.session_token;
    sessionStorage.setItem('user_id', session.id); sessionStorage.setItem('username', session.username);
    sessionStorage.setItem('session_token', session.session_token);
    localStorage.removeItem('user_id');
  }
  function logout() {
    userID.value = ''; username.value = ''; token.value = '';
    for (const key of ['user_id', 'username', 'session_token']) sessionStorage.removeItem(key);
  }
  return { userID, username, token, setSession, logout };
});
