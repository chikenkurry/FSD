import { defineStore } from 'pinia';
import { ref } from 'vue';

export const useAuthStore = defineStore('auth', () => {
    const userID = ref<string>(localStorage.getItem('user_id') || '');

    function setUser(id: string) {
        userID.value = id;
        localStorage.setItem('user_id', id); // persist across relaod
    }

    function logout() {
        userID.value = ''; 
        localStorage.removeItem('user_id');
    }

    return { userID, setUser, logout };
})