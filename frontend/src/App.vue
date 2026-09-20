<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SettingsPanel from './components/SettingsPanel.vue'
import { useDecisionStore } from './stores/decision'

const route = useRoute()
const router = useRouter()
const store = useDecisionStore()

const settingsOpen = ref(false)

// 仅在阅读/世界观页显示"世界观 / 抽卡"（需要故事上下文）
const isInStory = computed(() => route.name === 'story' || route.name === 'lore')
const storyId = computed(() => (route.params.id as string) || null)

function goLore() {
  if (storyId.value) router.push({ name: 'lore', params: { id: storyId.value } })
}
</script>

<template>
  <div id="app">
    <div class="app-shell">
      <main class="app-main">
        <router-view />
      </main>

      <!-- 右侧按钮列：贴近正文内容区右侧（首页 / 模型 / 世界观・抽卡） -->
      <aside class="app-rail" aria-label="快捷操作">
        <router-link to="/" class="rail-btn" title="返回书架">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
               stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 10.5 12 3l9 7.5" />
            <path d="M5 9.5V21h14V9.5" />
          </svg>
          <span class="rail-label">首页</span>
        </router-link>

        <button class="rail-btn" title="模型设置" @click="settingsOpen = true">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
               stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="3.2" />
            <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.11-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.56-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h.01a1.7 1.7 0 0 0 1.03-1.56V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v.01a1.7 1.7 0 0 0 1.56 1.03H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51.95Z" />
          </svg>
          <span class="rail-label">模型</span>
        </button>

        <template v-if="isInStory">
          <button class="rail-btn" title="世界观 · 历史线" @click="goLore">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
                 stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
              <path d="M2 12h20" />
            </svg>
            <span class="rail-label">世界观</span>
          </button>

          <button
            class="rail-btn"
            :class="{ active: store.drawOpen }"
            :title="store.drawOpen ? '收起命运卡' : '展开命运卡'"
            :aria-expanded="store.drawOpen"
            @click="store.toggleDraw"
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
                 stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="6" y="5" width="11" height="15" rx="2.5" opacity="0.55" />
              <rect x="10" y="2.5" width="11" height="15" rx="2.5" />
              <circle cx="15.5" cy="10" r="2.1" />
            </svg>
            <span class="rail-label">{{ store.drawOpen ? '收起' : '抽卡' }}</span>
          </button>
        </template>
      </aside>
    </div>

    <SettingsPanel :open="settingsOpen" @close="settingsOpen = false" />
  </div>
</template>

<style scoped>
/* ---------- 内容区 + 右侧按钮列 ---------- */
.app-shell {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  gap: 14px;
  padding: 24px 16px 48px;
}
.app-main {
  max-width: 820px;
  min-width: 0;
}
.app-rail {
  position: sticky;
  top: 24px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  z-index: 25;
}
.rail-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 58px;
  padding: 11px 6px 9px;
  border: 1px solid var(--border);
  border-radius: 0;
  background: var(--bg-card);
  color: var(--muted);
  cursor: pointer;
  text-decoration: none;
  transition: border-color 0.15s, color 0.15s, transform 0.15s, box-shadow 0.2s;
}
.rail-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
  transform: translateY(-2px);
  box-shadow: 0 8px 18px rgba(138, 106, 59, 0.16);
}
.rail-btn.active {
  border-color: var(--accent);
  box-shadow: 0 6px 18px rgba(138, 106, 59, 0.22);
  color: var(--accent);
}
.rail-btn svg {
  display: block;
}
.rail-label {
  font-size: 11px;
}

@media (max-width: 720px) {
  .app-shell {
    flex-wrap: wrap;
  }
  .app-rail {
    position: static;
    flex-direction: row;
    order: 2;
  }
}
</style>