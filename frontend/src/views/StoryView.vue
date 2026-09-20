<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDecisionStore } from '../stores/decision'
import DecisionPanel from '../components/DecisionPanel.vue'

const route = useRoute()
const router = useRouter()
const store = useDecisionStore()

onMounted(async () => {
  const id = route.params.id as string | undefined
  // 本会话刚创建（Home 已 set storyId）→ 直接使用；否则按 id 载入已有故事
  if (id && store.storyId !== id) {
    await store.load(id)
  }
})

const storyId = computed(() => route.params.id as string)
const wordCount = computed(() => store.passages.reduce((n, p) => n + p.length, 0))

function scrollToDraw() {
  document.getElementById('draw')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
function goLore() {
  router.push({ name: 'lore', params: { id: storyId.value } })
}
</script>

<template>
  <section class="story">
    <!-- 右侧固定侧栏：世界观/历史线等跳转 -->
    <nav class="side-rail" aria-label="侧边栏">
      <button class="rail-btn" title="世界观 · 历史线" @click="goLore">
        <span class="rail-ico" aria-hidden="true">🌍</span>
        <span class="rail-label">世界观</span>
      </button>
      <button class="rail-btn" title="抽命运卡" @click="scrollToDraw">
        <span class="rail-ico" aria-hidden="true">🃏</span>
        <span class="rail-label">抽卡</span>
      </button>
    </nav>

    <article class="reader">
      <header class="chapter-head">
        <p class="book-crumb">命运抽卡 · AI 互动小说</p>
        <h2 class="chapter-title">正文</h2>
        <p class="meta" v-if="!store.loading">
          <span>{{ store.passages.length }} 段</span>
          <span class="dot">·</span>
          <span>约 {{ wordCount }} 字</span>
          <template v-if="store.decisionNo"><span class="dot">·</span><span>已到节点 {{ store.decisionNo }}</span></template>
        </p>
      </header>

      <blockquote v-if="store.synopsis" class="synopsis">{{ store.synopsis }}</blockquote>

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
        <button class="nav-btn" @click="scrollToDraw">剧情分歧 · 抽卡</button>
      </nav>
    </article>

    <!-- 抽卡置于最下方 -->
    <section id="draw" class="draw">
      <div class="draw-inner">
        <DecisionPanel />
      </div>
    </section>
  </section>
</template>

<style scoped>
.story {
  max-width: 820px;
  margin: 0 auto;
}

/* ---------- 右侧固定侧栏 ---------- */
.side-rail {
  position: fixed;
  right: 18px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  gap: 10px;
  z-index: 30;
}
.rail-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 62px;
  padding: 12px 6px 10px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  backdrop-filter: saturate(1.2) blur(6px);
  cursor: pointer;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.05);
  transition: border-color 0.15s, transform 0.15s, box-shadow 0.2s;
}
.rail-btn:hover {
  border-color: var(--accent);
  transform: translateY(-2px);
  box-shadow: 0 10px 22px rgba(79, 70, 229, 0.14);
}
.rail-ico {
  font-size: 19px;
  line-height: 1;
}
.rail-label {
  font-size: 12px;
  color: var(--muted);
}
.rail-btn:hover .rail-label {
  color: var(--accent);
}

/* ---------- 阅读主体（仿起点章读，纸感） ---------- */
.reader {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 34px 40px 26px;
  box-shadow: 0 8px 30px rgba(80, 60, 20, 0.08);
}
.chapter-head {
  text-align: center;
  margin-bottom: 22px;
}
.book-crumb {
  margin: 0 0 8px;
  color: #a89782;
  font-size: 13px;
}
.chapter-title {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: 1px;
  color: #3a3124;
}
.meta {
  margin: 8px 0 0;
  color: #a89782;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.meta .dot {
  color: #d9cfb8;
}
.synopsis {
  margin: 0 auto 20px;
  padding: 14px 18px;
  border-left: 3px solid var(--accent);
  background: var(--accent-soft);
  color: #6b5f4a;
  font-size: 14px;
  line-height: 1.7;
  border-radius: 0 8px 8px 0;
}
.prose {
  color: #443a2c;
}
.passage p {
  margin: 0 0 14px;
  text-indent: 2em;
  line-height: 1.9;
  white-space: pre-wrap;
}
.hint {
  color: #a89782;
}
.phase {
  text-align: center;
}
.streaming {
  text-indent: 2em;
  line-height: 1.9;
  color: #6b5f4a;
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
  border-radius: 12px;
  overflow: hidden;
  background: #f6f0e3;
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

/* ---------- 抽卡（最下方） ---------- */
.draw {
  margin-top: 26px;
  padding-top: 26px;
  border-top: 1px solid var(--border);
}
.draw-inner {
  margin: 0 auto;
}

@media (max-width: 720px) {
  .reader {
    padding: 24px 20px 18px;
  }
  .side-rail {
    right: 8px;
    top: auto;
    bottom: 14px;
    transform: none;
    flex-direction: row;
  }
  .rail-btn {
    flex-direction: row;
    width: auto;
    gap: 6px;
    padding: 9px 14px;
  }
}
</style>