<template>
  <header class="top-bar">
    <div class="brand-section">
      <h3 class="brand-title">What to do?</h3>
    </div>
    <nav class="nav-links">
      <a class="nav-link active" href="/#">Forms</a>
    </nav>
  </header>
</template>

<script setup lang="ts">
// TopBar component for post-login screens
</script>

<style scoped>
.top-bar {
  background-color: white;
  border-bottom: 1px solid #E2E8F0;
  padding: 12px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 3px rgba(0,0,0,0.02);
}

.brand-title {
  font-size: 1.1rem;
  font-weight: bold;
  color: #2D3748;
  margin: 0;
}

.nav-links {
  display: flex;
  gap: 24px;
  font-size: 0.9rem;
  color: #718096;
}

.nav-link {
  cursor: pointer;
  padding-bottom: 4px;
}

.nav-link.active {
  color: #3182CE;
  font-weight: 600;
  border-bottom: 2px solid #3182CE;
}
</style>
