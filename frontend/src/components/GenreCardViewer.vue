<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { GenreCardDetail, GenreCardSummary } from '../types'

const props = defineProps<{
  /** 打开时默认选中的题材卡 id（当前书的命中卡），无则选第一张 */
  initialId?: string
}>()
const emit = defineEmits<{ close: [] }>()

const cards = ref<GenreCardSummary[]>([])
const currentId = ref<string>('')
const detail = ref<GenreCardDetail | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const bodyOpen = ref(false)

async function loadDetail(id: string) {
  currentId.value = id
  loading.value = true
  error.value = null
  detail.value = null
  bodyOpen.value = false
  try {
    detail.value = await api.getGenreCard(id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    cards.value = await api.getGenres()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    return
  }
  const pick =
    cards.value.find((c) => c.id === props.initialId) ?? cards.value[0]
  if (pick) loadDetail(pick.id)
})

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

/** 把剧本卡正文的极简 markdown 拆成可读块：标题 / 列表项 / 段落。 */
function renderBody(body: string): Array<{ type: 'h' | 'li' | 'p'; text: string }> {
  const out: Array<{ type: 'h' | 'li' | 'p'; text: string }> = []
  for (const raw of body.split('\n')) {
    const line = raw.trim()
    if (!line) continue
    const h = line.match(/^#{1,4}\s+(.*)$/)
    if (h) {
      out.push({ type: 'h', text: h[1]!.trim() })
      continue
    }
    const li = line.match(/^[-*•]\s+(.*)$/) || line.match(/^\d+[\.、]\s*(.*)$/)
    if (li) {
      out.push({ type: 'li', text: li[1]!.trim() })
      continue
    }
    out.push({ type: 'p', text: line })
  }
  return out
}
</script>

<template>
  <div class="gv-mask" @click.self="emit('close')">
    <div class="gv-panel" role="dialog" aria-modal="true">
      <header class="gv-head">
        <div class="gv-title">
          <span v-if="detail" class="gv-label">{{ detail.label }}</span>
          <span class="gv-name">{{ detail?.card_title || '题材手册' }}</span>
        </div>
        <button type="button" class="gv-close" @click="emit('close')" title="关闭">✕</button>
      </header>

      <nav class="gv-nav" aria-label="题材列表">
        <button
          v-for="c in cards"
          :key="c.id"
          type="button"
          class="gv-chip"
          :class="{ on: c.id === currentId }"
          @click="loadDetail(c.id)"
        >
          {{ c.label }}
        </button>
      </nav>

      <div class="gv-body">
        <p v-if="loading" class="hint">加载题材卡…</p>
        <p v-else-if="error" class="err">{{ error }}</p>
        <template v-else-if="detail">
          <section v-if="detail.anti_patterns?.length" class="gv-sec">
            <h3>反模式（请避免）</h3>
            <ul>
              <li v-for="(a, i) in detail.anti_patterns" :key="i">{{ a }}</li>
            </ul>
          </section>

          <section v-if="detail.pacing" class="gv-sec">
            <h3>节奏策略</h3>
            <p class="gv-flow">{{ detail.pacing }}</p>
          </section>

          <section v-if="detail.structure?.length" class="gv-sec">
            <h3>典型分幕</h3>
            <ul>
              <li v-for="(s, i) in detail.structure" :key="i">
                <b>{{ s[0] }}</b>：{{ s[1] }}
              </li>
            </ul>
          </section>

          <section v-if="detail.body" class="gv-sec">
            <button
              type="button"
              class="gv-collapse"
              :class="{ on: bodyOpen }"
              @click="bodyOpen = !bodyOpen"
            >
              <span>正文题材参考</span>
              <span class="gv-chev">{{ bodyOpen ? '收起' : '展开' }}</span>
            </button>
            <div v-if="bodyOpen" class="gv-prose">
              <div
                v-for="(b, i) in renderBody(detail.body)"
                :key="i"
                :class="{ h: b.type === 'h', li: b.type === 'li', p: b.type === 'p' }"
              >{{ b.text }}</div>
            </div>
          </section>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gv-mask {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(24, 24, 27, 0.45);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 48px 16px;
  overflow-y: auto;
}
.gv-panel {
  width: min(600px, 100%);
  background: var(--bg-card, #fff);
  border: 1px solid var(--border, #e5e5e5);
  border-radius: 8px;
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 96px);
}
.gv-head {
  display: flex;
  align-items: center;
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--border, #eceff3);
}
.gv-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.gv-label {
  font-size: 12px;
  color: #047857;
  background: #d1fae5;
  border-radius: 4px;
  padding: 0 6px;
  flex: none;
}
.gv-name {
  font-size: 17px;
  font-weight: 700;
  color: var(--text, #3a3124);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gv-close {
  margin-left: auto;
  border: none;
  background: none;
  font-size: 16px;
  color: var(--muted, #9ca3af);
  cursor: pointer;
  padding: 4px;
}
.gv-close:hover {
  color: var(--accent, #4f46e5);
}
.gv-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border, #eceff3);
  max-height: 120px;
  overflow-y: auto;
}
.gv-chip {
  border: 1px solid var(--border, #e5e7eb);
  background: #f8f8f7;
  border-radius: 12px;
  padding: 2px 10px;
  font-size: 12px;
  color: #57534e;
  cursor: pointer;
}
.gv-chip:hover {
  border-color: var(--accent, #4f46e5);
  color: var(--accent, #4f46e5);
}
.gv-chip.on {
  background: var(--accent, #4f46e5);
  border-color: var(--accent, #4f46e5);
  color: #fff;
}
.gv-body {
  padding: 14px 16px 18px;
  overflow-y: auto;
}
.gv-sec {
  margin-bottom: 14px;
}
.gv-sec h3 {
  margin: 0 0 6px;
  font-size: 14px;
  color: var(--text, #3a3124);
}
.gv-sec ul {
  margin: 0;
  padding-left: 18px;
}
.gv-sec li {
  margin: 3px 0;
  font-size: 13px;
  line-height: 1.6;
  color: #44403c;
}
.gv-flow {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: #44403c;
}
.gv-collapse {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  border: 1px solid var(--border, #e5e7eb);
  background: #fafafa;
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text, #3a3124);
  cursor: pointer;
  font-family: inherit;
}
.gv-collapse.on {
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
}
.gv-chev {
  color: var(--muted, #9ca3af);
  font-size: 12px;
}
.gv-prose {
  border: 1px solid var(--border, #e5e7eb);
  border-top: none;
  border-radius: 0 0 6px 6px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.7;
  color: #44403c;
}
.gv-prose .h {
  font-weight: 700;
  color: var(--text, #3a3124);
  margin: 6px 0 2px;
}
.gv-prose .li {
  padding-left: 12px;
}
.gv-prose .li::before {
  content: '·';
  margin-right: 6px;
  color: var(--accent, #4f46e5);
}
.hint {
  color: var(--muted, #9ca3af);
  font-size: 13px;
}
.err {
  color: #dc2626;
  font-size: 13px;
}
</style>