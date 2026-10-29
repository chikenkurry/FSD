import { clearCheckpoints } from '@/services/checkpoints';
import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { Session } from '@/types/form';

const KEYS = ['user_id', 'username', 'session_token'] as const;
const REMEMBERED = 'what2do:session:v1';

// The session is remembered on this device so a member who closes the tab and
// reopens their invitation later returns as themselves, not as a second person.
// The tab copy in sessionStorage stays the working copy the rest of the app reads.
function remembered(): Session | undefined {
  try {
    const raw = localStorage.getItem(REMEMBERED);
    const parsed = raw ? (JSON.parse(raw) as Partial<Session>) : undefined;
    return parsed?.id && parsed.username && parsed.session_token ? (parsed as Session) : undefined;
  } catch {
    return undefined;
  }
}
function restoreTab() {
  if (sessionStorage.getItem('session_token')) return;
  const saved = remembered();
  if (!saved) return;
  sessionStorage.setItem('user_id', saved.id);
  sessionStorage.setItem('username', saved.username);
  sessionStorage.setItem('session_token', saved.session_token);
}
restoreTab();

export const useAuthStore = defineStore('auth', () => {
  const userID = ref(sessionStorage.getItem('user_id') || '');
  const username = ref(sessionStorage.getItem('username') || '');
  const token = ref(sessionStorage.getItem('session_token') || '');
  function setSession(session: Session) {
    userID.value = session.id;
    username.value = session.username;
    token.value = session.session_token;
    sessionStorage.setItem('user_id', session.id);
    sessionStorage.setItem('username', session.username);
    sessionStorage.setItem('session_token', session.session_token);
    localStorage.removeItem('user_id');
    try {
      localStorage.setItem(
        REMEMBERED,
        JSON.stringify({ id: session.id, username: session.username, session_token: session.session_token }),
      );
    } catch {
      /* Private browsing: the session still lasts for this tab. */
    }
  }
  function clear() {
    userID.value = '';
    username.value = '';
    token.value = '';
    for (const key of KEYS) sessionStorage.removeItem(key);
  }
  function logout() {
    clearCheckpoints(userID.value);
    clear();
    try {
      localStorage.removeItem(REMEMBERED);
    } catch {
      /* nothing remembered */
    }
  }
  // Signing out in one tab signs out the others on this device.
  if (typeof window !== 'undefined')
    window.addEventListener('storage', (event) => {
      if (event.key === REMEMBERED && !event.newValue && token.value) clear();
    });
  return { userID, username, token, setSession, logout };
});
