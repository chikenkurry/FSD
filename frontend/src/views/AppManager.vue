<template>
  <div class="app-container">
    <!-- Frame switcher navbar for debugging and previewing all frames -->
    <nav class="frame-switcher">
      <span>Jump to Frame:</span>
      <button :class="{ active: currentFrame === 'login' }" @click="currentFrame = 'login'">Login</button>
      <button :class="{ active: currentFrame === 'dashboard' }" @click="currentFrame = 'dashboard'">Dashboard</button>
      <button :class="{ active: currentFrame === 'creator' }" @click="currentFrame = 'creator'">Form Creator</button>
      <button :class="{ active: currentFrame === 'published' }" @click="currentFrame = 'published'">Publish view</button>
      <button :class="{ active: currentFrame === 'answering' }" @click="currentFrame = 'answering'">Answer Form</button>
    </nav>

    <!-- Dynamically rendered active frame component -->
    <component 
      :is="activeFrameComponent"
      v-bind="frameProps"
      @navigate="handleNavigation"
      @published="onPublished"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, type Component } from 'vue';
import Login from '@/components/Login.vue';
import FormsDashboard from '@/components/FormsDashboard.vue';
import FormCreator from '@/components/FormCreator.vue';
import FormPublishedView from '@/components/FormPublishedView.vue';
import FormParticipantView from '@/components/FormParticipantView.vue';
import type { Form } from '@/types/form';

const currentFrame = ref<string>("login"); 

const publishedForm = ref<Form | null>(null);

const frameProps = computed(() =>
  currentFrame.value === 'published' ? { form: publishedForm.value } : {}
);

const onPublished = (form: Form) => {
  publishedForm.value = form;
  currentFrame.value = 'published';
};

// Computed property to select component based on active frame number
const activeFrameComponent = computed<Component>(() => {
  switch (currentFrame.value) {
    case "login": return Login;
    case "dashboard": return FormsDashboard;
    case "creator": return FormCreator;
    case "published": return FormPublishedView
    case "answering": return FormParticipantView
    default: return FormsDashboard;
  }
});

// Handles cross-frame navigation events
const handleNavigation = (target: number | string): void => {
  if (typeof target === 'number') {
    currentFrame.value = "login";
  } else if (target === 'creator') {
    currentFrame.value = "creator";
  } else if (target === 'dashboard') {
    currentFrame.value = "dashboard";
  } else if (target === 'published') {
    currentFrame.value = "published";
  } else if (target === 'anwering') {
    currentFrame.value = "answering";
  }
};
</script>

<style scoped>
.app-container {
  min-height: 100vh;
  background-color: #EFECE9;
  font-family: system-ui, -apple-system, sans-serif;
  color: #2D3748;
}

.frame-switcher {
  background: #2D3748;
  padding: 10px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  color: white;
  font-size: 0.9rem;
}

.frame-switcher button {
  background: #4A5568;
  border: none;
  color: white;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
}

.frame-switcher button.active {
  background: #3182CE;
  font-weight: bold;
}
</style>