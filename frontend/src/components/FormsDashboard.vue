<template>
  <div class="dashboard-layout">
    <!-- Post-login navigation top bar -->
    <TopBar />

    <div class="dashboard-wrapper">
      <header class="dashboard-header">
        <h2>Forms</h2>
        <button class="btn-primary" @click="emit('navigate', 'creator')">
          Create form
        </button>
      </header>

      <!-- loading state -->
      <div v-if="isLoading" class="state-card loading-state">
        <div class="spinner"></div>
        <p>...Loading the forms...</p>
      </div>

      <!-- error state -->
      <div v-else-if="errorMessage" class="state-card error-state">
        <p class="error-text">⚠️ {{ errorMessage }}</p>
        <button class="btn-secondary" @click="fetchForms"> Try Again </button>
      </div>

      <!-- fallback empty state -->
       <div v-else-if="forms.length === 0" class="state-card error-state">
        <div class="empty-icon">📋</div>
        <h3>No forms created yet</h3>
        <p class="empty-description">
          Get started by creating your first form
        </p>
        <button class="btn-primary" @click="emit('navigate', 'creator')">
          + Create a form
        </button>
       </div>
      
      <!-- data table view  success -->
      <div class="table-container">
        <table class="forms-table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Title</th>
              <th>Members</th>
              <th>Created by</th>
              <th>Category</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="form in forms" :key="form.id">
              <td>
                <span :class="['badge', form.state?.toLowerCase()]">{{ form.state }}</span>
              </td>
              <td class="cell-text">{{ form.title }}</td>
              <td>{{ form.membersCount }}</td>
              <td>{{ form.createdBy }}</td>
              <td><span class="category-badge">{{ form.category }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>


<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue';
import type { Form } from '@/types/form';
import { apiService } from '@/services/api';
import TopBar from '@/components/TopBar.vue';
import { useAuthStore } from '@/stores/auth';
import { errorMessages } from 'vue/compiler-sfc';

const authStore = useAuthStore();

const emit = defineEmits<{
  (e: 'navigate', frame: string): void;
}>();


// reactive component state
const forms = ref<Form[]>([]);
const isLoading = ref<boolean>(true);
const errorMessage = ref<string | null>(null);

// fetch from backend
const fetchForms = async (): Promise<void> => {
  if (!authStore.userID) {
    errorMessage.value = 'No logged in user';
    isLoading.value = false;
    return;
  }

  isLoading.value = true;
  errorMessage.value = null;
  
  try {
    forms.value = await apiService.getForms(authStore.userID);
  } catch (err) {
    console.error('Failed to load forms:', err); 
    errorMessage.value = 'Could not connect to the backend server.';
  } finally{
    isLoading.value = false;
  }
}

onMounted(() => {
  fetchForms();
});
// const forms = ref<Form[]>([
//   { id: 1, title: 'Sweden trip', description:'', state: 'Draft', membersCount: 5, createdBy: 'Jane Doe', category: 'Travel', questions: [] },
//   { id: 2, title: "Jane's Birthday dinner", description:'', state: 'Collecting', membersCount: 8, createdBy: 'Jane Doe', category: 'Event', questions: [] },
//   { id: 3, title: 'Content planning', description:'', state: 'Collecting', membersCount: 2, createdBy: 'Jane Doe', category: 'Work', questions: [] },
//   { id: 4, title: 'Wedding plans', description:'', state: 'Collecting', membersCount: 15, createdBy: 'John Doe', category: 'Event', questions: [] },
//   { id: 5, title: 'Doomsday plans', description:'', state: 'Reviewing', membersCount: 7, createdBy: 'Mr Nice Guy', category: 'General', questions: [] },
// ]);
</script>

<style scoped>
.dashboard-layout {
  min-height: 100vh;
  background-color: #EFECE9;
}
.dashboard-wrapper {
  padding: 32px;
  max-width: 1100px;
  margin: 0 auto;
}
.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}
.btn-primary {
  background-color: #3182CE;
  color: white;
  border: none;
  padding: 10px 20px;
  font-weight: bold;
  border-radius: 6px;
  cursor: pointer;
}

.btn-primary:hover { 
  background-color: #2B6CB0; 
}

.btn-secondary {
  background: white; 
  border: 1px solid #CBD5E0; 
  color: #4A5568; 
  padding: 8px 16px; 
  border-radius: 6px; 
  cursor: pointer;
}

/* Base State Container (Empty / Loading / Error) \*/ 
.state-card { background: white; 
  border-radius: 8px; 
  padding: 48px 24px; 
  text-align: center; 
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04); 
  border: 1px dashed #CBD5E0; /* Dashed frame matching theme \*/ 
  margin-top: 12px; 
}

/* Fallback Empty State Styles \*/ 
.empty-state .empty-icon { 
  font-size: 3rem; 
  margin-bottom: 12px; 
}
.empty-state h3 {
  font-size: 1.25rem; 
  color: #2D3748; 
  margin-bottom: 8px; 
  font-weight: 700;
} 
.empty-state .empty-description {
  color: #718096;
  max-width: 420px;
  margin: 0 auto 20px auto;
  font-size: 0.95rem;
  line-height: 1.5;
}

/* loading and error state styles*/
.loading-state p {
  color: #718096;
  font-weight: 500;
}

.error-state .error-text {
  color: #E53E3E;
  margin-bottom: 16px;
  font-weight: 500;
}

/* table view */
.table-container {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  overflow: hidden;
}
.forms-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}
.forms-table th, .forms-table td {
  padding: 14px 16px;
  border-bottom: 1px solid #EDF2F7;
}
.forms-table th {
  background-color: #F7FAFC;
  font-weight: 600;
  color: #4A5568;
}
.badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.85rem;
  font-weight: 500;
}
.badge.draft { background-color: #EDF2F7; color: #4A5568; }
.badge.collecting { background-color: #C6F6D5; color: #22543D; }
.badge.reviewing { background-color: #FEFCBF; color: #744210; }
</style>