<script setup lang="ts">
import { ref } from 'vue'
import SettingsPanel from './components/SettingsPanel.vue'

const settingsOpen = ref(false)
</script>

<template>
  <div id="app">
    <header class="app-header">
      <router-link to="/" class="brand">
        <span class="brand-mark" aria-hidden="true"></span>
        命运抽卡 · AI 小说
      </router-link>
      <button class="settings-btn" @click="settingsOpen = true">
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
             stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="3.2" />
          <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.11-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.56-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h.01a1.7 1.7 0 0 0 1.03-1.56V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v.01a1.7 1.7 0 0 0 1.56 1.03H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51.95Z" />
        </svg>
        模型设置
      </button>
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
  border-bottom: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: saturate(1.4) blur(8px);
  position: sticky;
  top: 0;
  z-index: 20;
}
.brand {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  font-weight: 800;
  font-size: 18px;
  color: #111827;
  text-decoration: none;
  letter-spacing: 0.3px;
}
.brand-mark {
  width: 12px;
  height: 12px;
  background: var(--accent);
  transform: rotate(45deg);
  border-radius: 3px;
  flex: none;
}
.settings-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border);
  background: #fff;
  color: #4b5563;
  padding: 6px 12px;
  border-radius: 999px;
  cursor: pointer;
  font-size: 13px;
  transition: border-color 0.15s, color 0.15s;
}
.settings-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.app-main {
  max-width: 960px;
  margin: 24px auto;
  padding: 0 16px;
}
</style>