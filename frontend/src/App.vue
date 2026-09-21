<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SettingsPanel from './components/SettingsPanel.vue'
import ReadingSettingsPanel from './components/ReadingSettingsPanel.vue'
import { useAuthStore } from './stores/auth'
import { useDecisionStore } from './stores/decision'
import { useReadingStore } from './stores/reading'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const store = useDecisionStore()
const rstore = useReadingStore() // 实例化即应用阅读主题/字体/字号/宽度

const settingsOpen = ref(false)
const readingOpen = ref(false)

function logout() {
  void auth.logout()
  void router.push({ name: 'login' })
}

// "世界观 / 抽卡"是阅读页专属动作：抽卡浮层只在阅读页挂载，世界观页点击会空转，
// 世界观按钮也就是当前页重载，因此在世界观页不再展示这两项。
const isOnStory = computed(() => route.name === 'story')
const storyId = computed(() => (route.params.id as string) || null)

function goLore() {
  if (storyId.value) router.push({ name: 'lore', params: { id: storyId.value } })
}
function scrollTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
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

        <button class="rail-btn" title="阅读设置" @click="readingOpen = true">
          <span class="rail-aa" aria-hidden="true">Aa</span>
          <span class="rail-label">阅读</span>
        </button>

        <router-link to="/styles" class="rail-btn" title="文风对比">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
               stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
          </svg>
          <span class="rail-label">文风</span>
        </router-link>

        <button
          class="rail-btn"
          :class="{ active: rstore.isNight }"
          :title="rstore.isNight ? '切换日间模式' : '切换夜间模式'"
          @click="rstore.toggleNight"
        >
          <svg v-if="rstore.isNight" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
               stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
          </svg>
          <svg v-else viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
               stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="4.5" />
            <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5 5l1.4 1.4M17.6 17.6 19 19M19 5l-1.4 1.4M6.4 17.6 5 19" />
          </svg>
          <span class="rail-label">{{ rstore.isNight ? '夜间' : '日间' }}</span>
        </button>

        <template v-if="isOnStory">
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
            :class="{ active: store.dirOpen }"
            :title="store.dirOpen ? '收起目录' : '章节目录'"
            :aria-expanded="store.dirOpen"
            @click="store.toggleDir"
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
                 stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              <path d="M9 7h7M9 11h5" />
            </svg>
            <span class="rail-label">{{ store.dirOpen ? '收起' : '目录' }}</span>
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

        <button class="rail-btn" title="回到顶部" @click="scrollTop">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
               stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 19V5M5 12l7-7 7 7" />
          </svg>
          <span class="rail-label">顶部</span>
        </button>

        <div class="rail-user" :title="`当前用户：${auth.username}`">
          <span class="avatar">{{ (auth.username || '?').slice(0, 1).toUpperCase() }}</span>
          <button class="rail-link" @click="logout">登出</button>
        </div>
      </aside>
    </div>

    <SettingsPanel :open="settingsOpen" @close="settingsOpen = false" />
    <ReadingSettingsPanel :open="readingOpen" @close="readingOpen = false" />
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
  /* 容量放宽到超出最大页面宽度选项，避免正文宽度被外层容器钳制 */
  max-width: 1320px;
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
.rail-aa {
  font-size: 16px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: -0.5px;
}
.rail-label {
  font-size: 11px;
}
.rail-user {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
}
.rail-link {
  border: none;
  background: none;
  color: var(--muted);
  font-size: 11px;
  cursor: pointer;
  padding: 0;
  font-family: inherit;
}
.rail-link:hover { color: var(--danger, #b91c1c); }

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