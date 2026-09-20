<script setup lang="ts">
import { ref } from 'vue'
import SettingsPanel from './components/SettingsPanel.vue'

const settingsOpen = ref(false)
</script>

<template>
  <div id="app">
    <header class="app-header">
      <router-link to="/" class="brand">命运抽卡 · AI 小说</router-link>
      <button class="settings-btn" @click="settingsOpen = true">⚙ 模型</button>
    </header>
    <main class="app-main">
      <router-view />
    </main>
    <SettingsPanel :open="settingsOpen" @close="settingsOpen = false" />
  </div>
</template>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 24px;
  border-bottom: 1px solid rgba(229, 231, 235, 0.7);
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(8px);
  position: sticky;
  top: 0;
  z-index: 20;
}
.brand {
  font-weight: 800;
  font-size: 18px;
  color: #1f2937;
  text-decoration: none;
  background: linear-gradient(90deg, #4f46e5, #db2777, #f59e0b);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.settings-btn {
  border: 1px solid #e5e7eb;
  background: #fff;
  color: #4b5563;
  padding: 6px 14px;
  border-radius: 999px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.2s, transform 0.1s;
}
.settings-btn:hover {
  background: #f3f4f6;
}
.settings-btn:active {
  transform: scale(0.96);
}
.app-main {
  max-width: 960px;
  margin: 24px auto;
  padding: 0 16px;
}
</style>