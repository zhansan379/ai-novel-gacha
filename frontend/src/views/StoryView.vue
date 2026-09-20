<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDecisionStore } from '../stores/decision'
import { useReadingStore } from '../stores/reading'
import DecisionPanel from '../components/DecisionPanel.vue'
import ChapterDirPanel from '../components/ChapterDirPanel.vue'
import type { Chapter } from '../types'

const route = useRoute()
const router = useRouter()
const store = useDecisionStore()
const rstore = useReadingStore()

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  const id = route.params.id as string | undefined
  // 本会话刚创建（Home 已 set storyId）→ 直接使用；否则按 id 载入已有故事
  if (id && store.storyId !== id) {
    await store.load(id)
  }
  viewNo.value = lastContentfulChapter()?.no ?? 1
  loadedAt.value = formatNow()
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  store.closeDir()
})

const storyId = computed(() => route.params.id as string)
const wordCount = computed(() => store.passages.reduce((n, p) => n + p.length, 0))
const curNo = computed(() => store.currentChapter?.no ?? 1)
const chapterByNo = (no: number) => store.chapters.find((c) => c.no === no) ?? null

/** 章节翻页模式下当前展示的章号；滚动模式忽略 */
const viewNo = ref(curNo.value)
const isPaged = computed(() => rstore.pageMode === 'paged')
/** 有效阅读章号：滚动模式跟踪开放章，章节翻页模式跟随 viewNo */
const activeNo = computed(() => (isPaged.value ? viewNo.value : curNo.value))
const viewChapter = computed(() => chapterByNo(activeNo.value))

/** 一章只有在覆盖到实际正文段（含端点）时才算“有内容”；空的开章（passage_from > passage_to）不渲染、不翻到。 */
function isContentful(ch: Chapter | null): boolean {
  return !!ch && ch.passage_from > 0 && ch.passage_to >= ch.passage_from && ch.passage_from - 1 < store.passages.length
}
function chapterRangeWords(ch: Chapter): number {
  const from = Math.max(0, ch.passage_from - 1)
  const to = Math.min(ch.passage_to, store.passages.length)
  let n = 0
  for (let i = from; i < to; i++) n += store.passages[i].length
  return n
}
/** 最近的“有内容”章：章节翻页模式的初始阅读章，避免落在空的开章上白屏。 */
function lastContentfulChapter(): Chapter | null {
  let best: Chapter | null = null
  for (const c of store.chapters) if (isContentful(c)) best = c
  return best
}

/** 正文渲染列表：滚动模式在每章首段前插入章节头；翻页模式只取当前有内容章及其章节头。 */
interface HeaderBlock { kind: 'header'; ch: Chapter; words: number }
interface PassageBlock { kind: 'passage'; text: string; index: number }
type ReadingBlock = HeaderBlock | PassageBlock
const readingBlocks = computed<ReadingBlock[]>(() => {
  const blocks: ReadingBlock[] = []
  if (isPaged.value) {
    const ch = viewChapter.value
    if (!ch || !isContentful(ch)) return blocks
    const from = ch.passage_from - 1
    const to = Math.min(ch.passage_to, store.passages.length)
    blocks.push({ kind: 'header', ch, words: chapterRangeWords(ch) })
    for (let i = from; i < to; i++) blocks.push({ kind: 'passage', text: store.passages[i], index: i })
    return blocks
  }
  const headerAt = new Map<number, Chapter>()
  for (const c of store.chapters) if (isContentful(c)) headerAt.set(c.passage_from - 1, c)
  for (let i = 0; i < store.passages.length; i++) {
    const c = headerAt.get(i)
    if (c) blocks.push({ kind: 'header', ch: c, words: chapterRangeWords(c) })
    blocks.push({ kind: 'passage', text: store.passages[i], index: i })
  }
  return blocks
})

const canPrev = computed(() => chapterByNo(activeNo.value - 1) != null)
const canNext = computed(() => chapterByNo(activeNo.value + 1) != null)

// 本地未落库作者 / 时间，阅读页章节头占位兜底
const author = 'AI 创作'
const loadedAt = ref('')
function _pad(n: number) { return String(n).padStart(2, '0') }
function formatNow() {
  const d = new Date()
  return `${d.getFullYear()}年${_pad(d.getMonth() + 1)}月${_pad(d.getDate())}日 ${_pad(d.getHours())}:${_pad(d.getMinutes())}`
}

/** 章节翻页模式下切换展示章；滚动模式跳转到目标章 */
function goChapter(no: number) {
  if (!chapterByNo(no)) return
  if (isPaged.value) {
    viewNo.value = no
    store.closeDir()
    document.querySelector<HTMLElement>('.reader')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  } else {
    scrollToChapter(no)
  }
}

function scrollToChapter(no: number) {
  const ch = chapterByNo(no)
  if (!ch) return
  if (isPaged.value) {
    viewNo.value = no
    store.closeDir()
    return
  }
  const idx = Math.max(0, ch.passage_from - 1)
  document.getElementById(`passage-${idx}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  store.closeDir()
}

// 新章有内容落定时，翻页模式跟随到该章；空的开章不切换，避免白屏
watch(() => store.currentChapter?.no, (no) => {
  if (!no) return
  const c = chapterByNo(no)
  if (isContentful(c)) viewNo.value = no
})

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    if (store.dirOpen) store.closeDir()
    if (store.drawOpen) store.closeDraw()
  }
}

function goLore() {
  router.push({ name: 'lore', params: { id: storyId.value } })
}
</script>

<template>
  <section class="story">
    <article class="reader">
      <header class="chapter-head">
        <nav class="crumb" aria-label="面包屑">
          <a
            class="crumb-link"
            @click.prevent="router.push({ name: 'home' })"
          >书架</a>
          <span class="crumb-sep">&gt;</span>
          <span class="crumb-current">{{ store.title || '未命名' }}</span>
        </nav>
        <!-- 元信息栏（书级）：书名 / 作者 / 全书字数 / 时间；每章的“第N章+字数”在正文内按章渲染 -->
        <div class="meta-bar" v-if="!store.loading">
          <span class="meta-item" title="书名">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
            <span>{{ store.title || '未命名' }}</span>
          </span>
          <span class="meta-item" title="作者">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>
            <span>{{ author }}</span>
          </span>
          <span class="meta-item" title="全书字数">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
            <span>{{ wordCount }} 字</span>
          </span>
          <span class="meta-item" title="更新时间">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
            <span>{{ loadedAt }}</span>
          </span>
        </div>

        <!-- 分割线右侧书签：用于收藏/标记当前页 -->
        <button
          class="bookmark"
          :class="{ on: store.bookmarked }"
          :aria-pressed="store.bookmarked"
          aria-label="收藏本书"
          @click="store.toggleBookmark"
        >
          <svg viewBox="150 0 300 380" width="34" height="46" aria-hidden="true">
            <path d="M 150 0 L 450 0 L 450 380 L 300 320 L 150 380 Z" fill="currentColor" />
          </svg>
        </button>
      </header>

      <div class="prose">
        <p v-if="store.loading && !store.passages.length" class="hint phase">加载中…</p>
        <template v-for="(b, i) in readingBlocks" :key="i">
          <header v-if="b.kind === 'header'" class="chapter-header">
            <h2 class="chap-title">第{{ b.ch.no }}章<template v-if="b.ch.title">　{{ b.ch.title }}</template></h2>
            <span class="word-badge" :title="`本章 ${b.words} 字`">{{ b.words }}</span>
          </header>
          <article v-else :id="`passage-${b.index}`" class="passage">
            <template v-for="(line, li) in b.text.split('\n')" :key="li">
              <p v-if="line.trim()">{{ line.trim() }}</p>
            </template>
          </article>
        </template>
        <div v-if="store.streamingText" class="streaming">
          <span class="caret">{{ store.streamingText }}</span>
        </div>
        <div v-else-if="store.loading && store.passages.length" class="streaming hint">正文生成中…</div>
        <p v-if="store.error" class="error">{{ store.error }}</p>
      </div>

      <!-- 完结横幅：书已走向结局，停止续写入口 -->
      <div v-if="store.storyStatus === 'completed'" class="ended-banner">
        <span class="ended-badge">完</span>
        <span>本书已完结，共 {{ store.chapters.length }} 章 · {{ store.passages.length }} 段。</span>
      </div>

      <!-- 章节底端导航：上一章 | 目录 | 世界观 | 抽卡 | 下一章 -->
      <nav class="chapter-nav">
        <button class="nav-btn" :disabled="!canPrev" @click="goChapter(activeNo - 1)">上一章</button>
        <button class="nav-btn" @click="store.dirOpen = true">目录</button>
        <button class="nav-btn" @click="goLore">世界观 · 历史线</button>
        <button class="nav-btn" :disabled="store.storyStatus === 'completed'" @click="store.toggleDraw">
          剧情分歧 · 抽卡{{ store.storyStatus === 'completed' ? '（已完结）' : '' }}
        </button>
        <button class="nav-btn" :disabled="!canNext" @click="goChapter(activeNo + 1)">下一章</button>
      </nav>
    </article>

    <!-- 章节目录遮罩：列出全书章节，支持跳转与改标题 -->
    <Teleport to="body">
      <div
        v-if="store.dirOpen"
        class="draw-mask"
        role="dialog"
        aria-modal="true"
        aria-label="章节目录"
        @click.self="store.closeDir"
      >
        <div class="draw-panel dir-panel">
          <ChapterDirPanel @jump="scrollToChapter" @close="store.closeDir" />
        </div>
      </div>
    </Teleport>

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
  position: relative;
  margin-bottom: 40px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}
.crumb {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #1a1a1a;
  font-size: 14px;
  line-height: 1;
  font-family: system-ui, "PingFang SC", "Microsoft YaHei", sans-serif;
}
.crumb-link {
  color: #3a3a3a;
  cursor: pointer;
  text-decoration: none;
  transition: color 0.15s;
}
.crumb-link:hover {
  color: var(--accent);
  text-decoration: underline;
}
.crumb-sep {
  color: #9c9c9c;
  font-weight: 700;
}
.crumb-current {
  color: #111;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
/* ---------- 正文内章节头：第N章 + 字数徽章；书级元信息栏在顶部 ---------- */
.chapter-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin: 30px 0 6px;
  padding: 14px 0 0;
  border-top: 1px solid var(--border);
  scroll-margin-top: 24px;
}
.chapter-header:first-child {
  border-top: none;
  margin-top: 0;
  padding-top: 0;
}
.chap-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--text);
  line-height: 1.3;
}
.word-badge {
  flex: none;
  font-size: 12px;
  color: #888;
  border: 1px solid #ccc;
  border-radius: 8px;
  padding: 2px 8px;
  line-height: 1.4;
  font-family: system-ui, "PingFang SC", "Microsoft YaHei", sans-serif;
}
.meta-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 12px;
  color: #888;
  font-size: 14px;
  flex-wrap: wrap;
}
.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}
.meta-item svg {
  flex: none;
}
.prose {
  color: var(--text);
}
.passage p {
  margin: 0 0 14px;
  text-indent: 2em;
  line-height: 1.9;
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
.nav-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.nav-btn:disabled:hover {
  background: none;
  color: var(--muted);
}
.ended-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 22px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  background: var(--accent-soft);
  color: var(--text);
  font-size: 14px;
}
.ended-badge {
  flex: 0 0 auto;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--accent);
  color: var(--bg-card);
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 600;
}
.dir-panel {
  min-width: min(380px, 100%);
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
  width: fit-content;
  max-width: min(1200px, 100%);
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

/* ---------- 分割线右侧书签：丝带造型，固定于面包屑分割线右端 ---------- */
.bookmark {
  position: absolute;
  top: 100%;
  right: 0;
  transform: translateY(-6px);
  z-index: 5;
  width: 34px;
  height: 46px;
  padding: 0;
  border: none;
  background: none;
  color: #c9cecb;
  cursor: pointer;
  filter: drop-shadow(0 2px 4px rgba(80, 60, 20, 0.18));
  transition: color 0.2s, transform 0.15s;
}
.bookmark:hover {
  color: var(--accent);
  transform: translateY(-6px) scale(1.06);
}
.bookmark.on {
  color: var(--accent);
}
.bookmark svg {
  display: block;
  width: 100%;
  height: 100%;
}

@media (max-width: 720px) {
  .reader {
    padding: 24px 20px 18px;
  }
}
</style>