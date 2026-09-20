<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { StyleProfile } from '../types'

interface CompareResult {
  style_id: string
  name: string
  output: string | null
  error: string | null
}

const router = useRouter()
const styles = ref<StyleProfile[]>([])
const selected = ref<string[]>([])
const source = ref('深夜的街道空无一人，路灯亮着昏黄的光。他站在路口，不知道该往哪个方向走。')
const loading = ref(false)
const error = ref('')
const results = ref<CompareResult[] | null>(null)

onMounted(async () => {
  try {
    styles.value = await api.getStyles()
    selected.value = styles.value.map((s) => s.id)
  } catch {
    styles.value = []
  }
})

function toggle(id: string) {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((x) => x !== id)
    : [...selected.value, id]
}
function selectAll() { selected.value = styles.value.map((s) => s.id) }
function selectNone() { selected.value = [] }

async function runCompare() {
  if (!source.value.trim()) { error.value = '请先输入一段素材'; return }
  if (!selected.value.length) { error.value = '至少选择一个文风'; return }
  loading.value = true
  error.value = ''
  results.value = null
  try {
    const res = await api.compareStyles(source.value.trim(), selected.value)
    results.value = res.results
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="style-page">
    <header class="page-head">
      <button class="back" @click="router.push('/')">← 返回首页</button>
      <div class="head-txt">
        <h2>文风对比</h2>
        <p class="sub">输入同一段素材，用不同文风真实调用模型改写，直观感受文风的差异。</p>
      </div>
      <router-link class="about-link" to="/styles/about">文风说明 →</router-link>
    </header>

    <div class="panel">
      <label class="field">
        <span class="field-label">素材（同一段内容）</span>
        <textarea v-model="source" class="source" rows="4" maxlength="2000"
                  placeholder="输入一段要改写的小说素材……" />
      </label>

      <div class="pick-row">
        <span class="pick-label">选择文风（{{ selected.length }}/{{ styles.length }}）</span>
        <div class="chips">
          <button v-for="s in styles" :key="s.id" type="button"
                  class="chip" :class="{ on: selected.includes(s.id) }"
                  @click="toggle(s.id)" :title="s.description">{{ s.name }}</button>
        </div>
        <div class="pick-actions">
          <button type="button" class="mini" @click="selectAll">全选</button>
          <button type="button" class="mini" @click="selectNone">清空</button>
        </div>
      </div>

      <div class="actions-row">
        <button class="btn primary" :disabled="loading" @click="runCompare">
          {{ loading ? '生成中…' : '生成对比' }}
        </button>
      </div>

      <p v-if="error" class="err">{{ error }}</p>
    </div>

    <div v-if="results" class="results">
      <h3 class="results-title">改写结果</h3>
      <div class="result-grid">
        <div v-for="r in results" :key="r.style_id" class="result-card">
          <h4 class="result-name">{{ r.name }}</h4>
          <p v-if="r.error" class="err">{{ r.error }}</p>
          <p v-else-if="r.output" class="result-text">{{ r.output }}</p>
          <p v-else class="muted">（无输出）</p>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.style-page {
  max-width: 860px;
  margin: 0 auto;
}
.page-head {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding-bottom: 14px;
  margin-bottom: 6px;
  border-bottom: 1px solid var(--border);
}
.back {
  flex: none;
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: 0;
  background: var(--bg-card);
  color: var(--muted);
  font-size: 14px;
  cursor: pointer;
}
.back:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.head-txt {
  flex: 1;
}
.head-txt h2 {
  margin: 0 0 4px;
  font-size: 22px;
  color: var(--text);
}
.sub {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
}
.about-link {
  flex: none;
  align-self: center;
  color: var(--accent);
  text-decoration: none;
  font-size: 13px;
}
.panel {
  margin-top: 16px;
  border: 1px solid var(--border);
  border-radius: 0;
  padding: 16px 18px;
  background: var(--bg-card);
}
.field {
  display: block;
}
.field-label {
  display: block;
  font-size: 13px;
  color: var(--muted);
  margin-bottom: 6px;
}
.source {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 0;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.7;
  background: var(--bg-page);
  color: var(--text);
  resize: vertical;
}
.pick-row {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
}
.pick-label {
  font-size: 13px;
  color: var(--muted);
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.chip {
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 0;
  background: var(--bg-card);
  color: var(--muted);
  cursor: pointer;
  font-size: 13px;
}
.chip.on {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
}
.pick-actions {
  display: flex;
  gap: 8px;
}
.mini {
  border: none;
  background: none;
  color: var(--accent);
  cursor: pointer;
  font-size: 12px;
  padding: 0;
}
.actions-row {
  margin-top: 16px;
}
.btn {
  padding: 10px 24px;
  border: none;
  border-radius: 0;
  cursor: pointer;
  font-size: 14px;
}
.btn.primary {
  background: var(--accent);
  color: var(--on-accent);
  font-weight: 600;
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.err {
  color: #dc2626;
  font-size: 13px;
}
.muted {
  color: var(--muted);
  font-size: 13px;
}
.results {
  margin-top: 20px;
}
.results-title {
  margin: 0 0 12px;
  font-size: 16px;
  color: var(--text);
}
.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
.result-card {
  border: 1px solid var(--border);
  border-radius: 0;
  background: var(--bg-card);
  padding: 12px 14px;
}
.result-name {
  margin: 0 0 8px;
  font-size: 15px;
  color: var(--accent);
}
.result-text {
  margin: 0;
  color: var(--text);
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
}
</style>