<template>
  <div class="app-container">
    <!-- Frame switcher navbar for debugging and previewing all frames -->
    <nav class="frame-switcher">
      <span>Jump to Frame:</span>
      <button :class="{ active: currentFrame === 'login' }" @click="currentFrame = 'login'">Frame 2</button>
      <button :class="{ active: currentFrame === 'dashboard' }" @click="currentFrame = 'dashboard'">Frame 3</button>
      <button :class="{ active: currentFrame === 'creator' }" @click="currentFrame = 'creator'">Frame 4</button>
    </nav>

    <!-- Dynamically rendered active frame component -->
    <component 
      :is="activeFrameComponent" 
      @navigate="handleNavigation"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, type Component } from 'vue';
import Login from '@/components/Login.vue';
import FormsDashboard from '@/components/FormsDashboard.vue';
import FormCreator from '@/components/FormCreator.vue';

const currentFrame = ref<string>("login"); 

// Computed property to select component based on active frame number
const activeFrameComponent = computed<Component>(() => {
  switch (currentFrame.value) {
    case "login": return Login;
    case "dashboard": return FormsDashboard;
    case "creator": return FormCreator;
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