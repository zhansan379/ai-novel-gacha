<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDecisionStore } from '../stores/decision'
import DecisionPanel from '../components/DecisionPanel.vue'

const route = useRoute()
const router = useRouter()
const store = useDecisionStore()

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  const id = route.params.id as string | undefined
  // 本会话刚创建（Home 已 set storyId）→ 直接使用；否则按 id 载入已有故事
  if (id && store.storyId !== id) {
    await store.load(id)
  }
})
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

const storyId = computed(() => route.params.id as string)
const wordCount = computed(() => store.passages.reduce((n, p) => n + p.length, 0))

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && store.drawOpen) store.closeDraw()
}

function goLore() {
  router.push({ name: 'lore', params: { id: storyId.value } })
}
</script>

<template>
  <section class="story">
    <article class="reader">
      <header class="chapter-head">
        <p class="book-crumb">AI 帮你写互动小说</p>
        <h2 class="chapter-title">正文</h2>
        <p class="meta" v-if="!store.loading">
          <span>{{ store.passages.length }} 段</span>
          <span class="dot">·</span>
          <span>约 {{ wordCount }} 字</span>
          <template v-if="store.decisionNo"><span class="dot">·</span><span>已到节点 {{ store.decisionNo }}</span></template>
        </p>
      </header>

      <div class="prose">
        <p v-if="store.loading && !store.passages.length" class="hint phase">加载中…</p>
        <article v-for="(p, i) in store.passages" :key="i" class="passage">
          <p>{{ p }}</p>
        </article>
        <div v-if="store.streamingText" class="streaming">
          <span class="caret">{{ store.streamingText }}</span>
        </div>
        <div v-else-if="store.loading && store.passages.length" class="streaming hint">正文生成中…</div>
        <p v-if="store.error" class="error">{{ store.error }}</p>
      </div>

      <!-- 章节底端导航（仿起点：上一章 | 目录 | 下一章） -->
      <nav class="chapter-nav">
        <button class="nav-btn" @click="router.push({ name: 'home' })">返回书架</button>
        <button class="nav-btn" @click="goLore">世界观 · 历史线</button>
        <button class="nav-btn" @click="store.toggleDraw">剧情分歧 · 抽卡</button>
      </nav>
    </article>

    <!-- 抽卡遮罩层：卡片网格以整页宽度在页面中部展开（绝对定位 + 背景遮罩） -->
    <Teleport to="body">
      <div
        v-if="store.drawOpen"
        class="draw-mask"
        role="dialog"
        aria-modal="true"
        aria-label="剧情分歧 · 命运卡"
        @click.self="store.closeDraw"
      >
        <button class="draw-close" title="关闭 (Esc)" @click="store.closeDraw" aria-label="关闭">✕</button>
        <div class="draw-panel">
          <DecisionPanel />
        </div>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.story {
  max-width: var(--reader-width, 820px);
  margin: 0 auto;
}

/* ---------- 阅读主体（仿起点章读，纸感） ---------- */
.reader {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 0;
  padding: 34px 40px 26px;
  box-shadow: 0 8px 30px rgba(80, 60, 20, 0.08);
  font-family: var(--reader-font);
  font-size: var(--reader-font-size, inherit);
}
.chapter-head {
  text-align: center;
  margin-bottom: 22px;
}
.book-crumb {
  margin: 0 0 8px;
  color: var(--muted);
  font-size: 13px;
}
.chapter-title {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: 1px;
  color: var(--text);
}
.meta {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.meta .dot {
  color: var(--border);
}
.prose {
  color: var(--text);
}
.passage p {
  margin: 0 0 14px;
  text-indent: 2em;
  line-height: 1.9;
  white-space: pre-wrap;
}
.hint {
  color: var(--muted);
}
.phase {
  text-align: center;
}
.streaming {
  text-indent: 2em;
  line-height: 1.9;
  color: var(--muted);
  white-space: pre-wrap;
  border-left: 3px solid #8a9b6e;
  padding-left: 10px;
  min-height: 2em;
}
.streaming .caret::after {
  content: '▍';
  color: #8a9b6e;
  animation: blink 1s steps(2) infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}
.error {
  color: #b0452e;
  text-indent: 2em;
}

/* ---------- 章节底端导航（仿起点 nav-btn-group） ---------- */
.chapter-nav {
  display: flex;
  align-items: stretch;
  margin-top: 26px;
  border: 1px solid var(--border);
  border-radius: 0;
  overflow: hidden;
  background: var(--accent-soft);
}
.nav-btn {
  flex: 1;
  border: none;
  background: none;
  padding: 14px 8px;
  font-size: 14px;
  color: var(--muted);
  cursor: pointer;
  position: relative;
  transition: color 0.15s, background 0.15s;
  font-weight: 500;
}
.nav-btn + .nav-btn {
  border-left: 1px solid var(--border);
}
.nav-btn:hover {
  background: var(--bg-card);
  color: var(--accent);
}

/* ---------- 抽卡遮罩：卡片网格占整页宽度，绝对定位居中 ---------- */
.draw-mask {
  position: fixed;
  inset: 0;
  z-index: 60;
  background: rgba(43, 36, 24, 0.45);
  backdrop-filter: blur(3px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 18px;
  overflow: auto;
  animation: mask-in 0.18s ease both;
}
@keyframes mask-in {
  from { opacity: 0; }
  to { opacity: 1; }
}
.draw-panel {
  width: min(1200px, 100%);
  animation: deck-in 0.22s ease both;
}
@keyframes deck-in {
  from { transform: translateY(10px) scale(0.98); opacity: 0; }
  to { transform: none; opacity: 1; }
}
.draw-close {
  position: fixed;
  top: 18px;
  right: 18px;
  z-index: 61;
  width: 34px;
  height: 34px;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--muted);
  border-radius: 50%;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(40, 33, 20, 0.25);
  line-height: 1;
  font-size: 15px;
}
.draw-close:hover {
  color: var(--accent);
  border-color: var(--accent);
}

@media (max-width: 720px) {
  .reader {
    padding: 24px 20px 18px;
  }
}
</style>