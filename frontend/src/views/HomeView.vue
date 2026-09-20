<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useDecisionStore } from '../stores/decision'
import type { StoryListItem, StorySnapshot, StyleProfile } from '../types'

const router = useRouter()
const store = useDecisionStore()
const premise = ref('')
const styles = ref<StyleProfile[]>([])
const selectedStyle = ref<string>('')
const stories = ref<StoryListItem[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const actionMsg = ref('')

onMounted(async () => {
  try {
    styles.value = await api.getStyles()
    selectedStyle.value = ''  // 默认自动匹配（留空 → 后端按内容推荐）
  } catch {
    styles.value = []
  }
  await loadStories()
  store.resumePendingCreate() // 刷新恢复仍在进行中的异步开书任务
})

async function loadStories() {
  try {
    stories.value = (await api.getStories()).stories
  } catch {
    stories.value = []
  }
}

function openStory(storyId: string) {
  router.push({ name: 'story', params: { id: storyId } })
}

/** 由 story_id 派生一个稳定的 4 位“书号”，用于封面占位（无真实书号字段）。 */
function bookNo(id: string): string {
  let sum = 0
  for (const ch of id) sum += ch.charCodeAt(0)
  return String((sum % 9000) + 1000)
}

/** 导出下拉：当前张开菜单的故事 id（null 表示全部收起）。 */
const exportOpen = ref<string | null>(null)

function toggleExport(s: StoryListItem) {
  exportOpen.value = exportOpen.value === s.story_id ? null : s.story_id
}

/** 把快照里的各段正文按顺序拼接为 Markdown / TXT 纯文本（不含简介，无段标题）。 */
function stitchExport(data: StorySnapshot, format: 'md' | 'txt'): string {
  const title = data.premise || '未命名'
  const body = (data.passages as Array<{ content?: string }>)
    .filter((p) => p?.content)
    .map((p) => p.content)
    .join('\n\n')
  if (format === 'md') return `# ${title}\n\n${body}\n`
  return `${title}\n\n${body}\n`
}

/** 触发浏览器下载一段文本。 */
function downloadBlob(text: string, mime: string, filename: string) {
  const blob = new Blob([text], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** 按所选格式导出：md / txt 拼接正文，json 导出整本快照。 */
async function downloadExport(s: StoryListItem, format: 'md' | 'txt' | 'json') {
  exportOpen.value = null
  try {
    const data = await api.exportStory(s.story_id)
    const base = (s.premise || '故事').slice(0, 30)
    if (format === 'json') {
      downloadBlob(JSON.stringify(data, null, 2), 'application/json', `${base}.json`)
    } else {
      downloadBlob(stitchExport(data, format), format === 'md' ? 'text/markdown' : 'text/plain', `${base}.${format}`)
    }
    actionMsg.value = ''
  } catch (e) {
    actionMsg.value = e instanceof Error ? e.message : String(e)
  }
}

/** 从书架移除一本故事（需二次确认）。 */
async function deleteStory(s: StoryListItem) {
  if (!window.confirm(`确定删除「${s.premise || '未命名'}」吗？此操作不可恢复。`)) return
  try {
    await api.deleteStory(s.story_id)
    await loadStories()
    actionMsg.value = ''
  } catch (e) {
    actionMsg.value = e instanceof Error ? e.message : String(e)
  }
}

/** 读取用户选择的 JSON 快照并导入为新一本故事。 */
async function onImportFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const snapshot = JSON.parse(await file.text())
    await api.importStory(snapshot)
    actionMsg.value = ''
    await loadStories()
  } catch (err) {
    actionMsg.value = `导入失败：${err instanceof Error ? err.message : String(err)}`
  }
}

async function createStory() {
  if (store.creating) return
  await store.create(
    premise.value || '一个少年在雨夜的旧城、被迫背负一个不为人知的秘密',
    selectedStyle.value || undefined,
  )
  if (store.storyId) {
    router.push({ name: 'story', params: { id: store.storyId } })
  }
}
</script>

<template>
  <section class="home">
    <div class="home-inner">
      <h1 class="hero-title"><span class="hl">AI 帮你写</span>互动小说</h1>
      <p class="sub">
        输入一句灵感，系统先为你构建世界观、历史与大纲；每个剧情分歧点，你可以
        <strong>抽一张命运卡</strong> 或用 <strong>自由输入</strong> 决定故事去向。
      </p>

      <div class="cta">
        <input
          v-model="premise"
          class="premise-input"
          maxlength="200"
          placeholder="例：一个失忆的杀手想找回身份……（留空则随机开书）"
        />
        <button class="btn primary big" :disabled="store.creating" @click="createStory">
          {{ store.creating ? '开书中…' : '抽 卡 开 书' }}
        </button>
      </div>

      <div v-if="store.creating" class="opening">
        <span class="spinner" aria-hidden="true"></span>
        <span class="phase">{{ store.createStage || '开书任务已提交，等待后端响应…' }}</span>
        <span v-if="store.creatingTaskId" class="resumed">（后台任务 · 刷新页面自动恢复）</span>
        <span class="dots" aria-hidden="true"><i>.</i><i>.</i><i>.</i></span>
      </div>

      <div class="style-row">
        <label class="style-label" for="style">文风：</label>
        <select v-model="selectedStyle" id="style" class="style-select">
          <option value="">自动匹配（按内容推荐）</option>
          <option v-for="s in styles" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
        <span class="style-desc">
          {{ selectedStyle ? styles.find((s) => s.id === selectedStyle)?.description : '不选则由系统根据故事内容自动推荐' }}
        </span>
      </div>

      <p v-if="store.error" class="error">{{ store.error }}</p>

<section class="shelf">
        <div class="shelf-bar">
          <h3 class="shelf-title">书架 <span v-if="stories.length" class="shelf-count">{{ stories.length }} 本</span></h3>
          <div class="bar-actions">
            <span class="import-hint">仅支持导入 .json 快照</span>
            <button type="button" class="btn btn-secondary" @click="router.push({ name: 'favorites' })">我的收藏</button>
            <button type="button" class="btn btn-secondary btn-import" title="仅支持导入导出生成 .json 快照"
                    @click="fileInput?.click()">导入</button>
            <input ref="fileInput" type="file" accept=".json,application/json" class="hidden-file"
                   @change="onImportFile" aria-label="导入故事 JSON" />
          </div>
        </div>
        <p v-if="actionMsg" class="action-msg">{{ actionMsg }}</p>
        <div v-if="stories.length" class="shelf-list">
          <div v-for="s in stories" :key="s.story_id" class="book-card">
            <!-- 左：封面（抽象水墨纹理占位） -->
            <div class="cover" aria-hidden="true">
              <span class="cover-title">{{ s.premise || '未命名' }}</span>
              <span class="cover-no">{{ bookNo(s.story_id) }}</span>
              <span class="cover-logo"><i class="cover-logo-mark"></i>抽卡小说</span>
            </div>

            <!-- 中：作品信息 -->
            <div class="info">
              <h4 class="info-title">{{ s.premise || '未命名' }}</h4>
            </div>

            <!-- 右：操作按钮（从右至左：去写作 · 导出下拉 · 删除） -->
            <div class="actions">
              <button type="button" class="btn btn-danger" @click="deleteStory(s)">删除</button>
              <div class="export-wrap">
                <button type="button" class="btn btn-secondary" :class="{ on: exportOpen === s.story_id }"
                        @click="toggleExport(s)">导出 ▾</button>
                <div v-if="exportOpen === s.story_id" class="export-menu">
                  <button type="button" @click="downloadExport(s, 'md')">Markdown (.md)</button>
                  <button type="button" @click="downloadExport(s, 'txt')">TXT (.txt)</button>
                  <button type="button" @click="downloadExport(s, 'json')">JSON 快照 (.json)</button>
                </div>
              </div>
              <button type="button" class="btn btn-primary" @click="openStory(s.story_id)">去写作</button>
            </div>
          </div>
        </div>
        <p v-else class="shelf-empty">书架是空的——点上方“导入”恢复一本作品，或用开书表单新开一本。</p>
      </section>

    </div>
  </section>
</template>

<style scoped>
.home {
  min-height: 60vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 0;
  position: relative;
}
.home-inner {
  width: 100%;
  text-align: center;
  animation: fadeUp 0.5s ease both;
}
@keyframes fadeUp {
  from { transform: translateY(14px); opacity: 0; }
  to { transform: none; opacity: 1; }
}
.hero-title {
  font-size: 34px;
  margin: 0 0 12px;
  letter-spacing: 1px;
  color: var(--text);
  font-weight: 800;
}
/* 签名细节：关键短语下划线高亮，单一强调色 */
.hl {
  background: linear-gradient(transparent 64%, var(--accent-soft) 0);
  padding: 0 3px;
  color: var(--accent);
  font-weight: 800;
}
.sub {
  max-width: 640px;
  margin: 0 auto 26px;
  color: var(--muted);
}
.cta {
  display: flex;
  gap: 12px;
  justify-content: center;
}
.premise-input {
  width: min(520px, 66vw);
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 0;
  font-size: 15px;
  background: var(--bg-card);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.premise-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(138, 106, 59, 0.18);
}
.btn {
  padding: 12px 26px;
  border: none;
  border-radius: 0;
  cursor: pointer;
}
.btn.primary {
  background: var(--accent);
  color: var(--on-accent);
  font-weight: 600;
  box-shadow: 0 6px 18px rgba(138, 106, 59, 0.3);
  transition: background-color 0.15s, transform 0.15s, box-shadow 0.2s;
}
.btn.primary:hover:not(:disabled) {
  background: #75572f;
  transform: translateY(-2px);
}
.btn.primary:active:not(:disabled) {
  transform: translateY(0);
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.style-row {
  margin-top: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--muted);
  font-size: 14px;
}
.style-select {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 0;
  background: var(--bg-card);
}
.style-desc {
  max-width: 420px;
  text-align: left;
  color: var(--muted);
  font-size: 13px;
}
.error {
  color: #b0452e;
}
.shelf {
  margin-top: 34px;
  text-align: left;
  max-width: 720px;
  margin-left: auto;
  margin-right: auto;
}
.shelf-bar {
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.shelf-title {
  margin: 0;
  font-size: 14px;
  letter-spacing: 2px;
  color: var(--muted);
  font-weight: 700;
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.shelf-count {
  font-weight: 600;
  color: var(--accent);
  letter-spacing: 0;
  font-size: 13px;
}
.bar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.import-hint {
  font-size: 12px;
  color: var(--muted);
}
.btn-import {
  padding: 7px 16px;
}
.shelf-empty {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--muted);
}
.hidden-file {
  display: none;
}
.action-msg {
  margin: 0 0 12px;
  font-size: 13px;
  color: #dc2626;
}
.shelf-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
/* 卡片：左（封面）· 中（信息）· 右（操作）三段横排，垂直居中，B 端口碑式作品行 */
.book-card {
  display: flex;
  align-items: stretch;
  gap: 22px;
  padding: 16px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 0;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
  font-family: 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif;
  transition: border-color 0.15s, box-shadow 0.2s;
}
.book-card:hover {
  border-color: var(--accent);
  box-shadow: 0 6px 16px rgba(16, 24, 40, 0.07);
}
/* 左：封面 */
.cover {
  position: relative;
  flex: none;
  align-self: flex-start;
  width: 104px;
  height: 140px;
  border: 1px solid var(--border);
  background-color: var(--bg-page);
  background-image:
    radial-gradient(circle at 22% 28%, rgba(20, 20, 20, 0.06), transparent 32%),
    radial-gradient(circle at 82% 72%, rgba(20, 20, 20, 0.05), transparent 30%),
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='160' viewBox='0 0 120 160'%3E%3Cg fill='none' stroke-linecap='round'%3E%3Cpath d='M22 128 C30 92 48 66 74 60 C96 55 106 74 92 92 C80 108 56 104 52 84 C49 68 70 62 82 74' stroke='%231c1c1c' stroke-width='7' opacity='0.14'/%3E%3Cpath d='M34 100 C52 84 64 88 70 104 C76 120 62 132 48 126' stroke='%231c1c1c' stroke-width='5' opacity='0.10'/%3E%3Cpath d='M80 46 C92 34 106 40 98 56 C92 68 78 62 80 54' stroke='%231c1c1c' stroke-width='4' opacity='0.12'/%3E%3Cpath d='M96 118 C108 108 112 96 104 88' stroke='%231c1c1c' stroke-width='3' opacity='0.10'/%3E%3C/g%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: center;
  background-size: cover;
  overflow: hidden;
}
.cover-title {
  position: absolute;
  top: 12px;
  left: 10px;
  right: 10px;
  color: var(--text);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.25;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.cover-no {
  position: absolute;
  left: 10px;
  bottom: 24px;
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 1px;
}
.cover-logo {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 3px 0;
  background: #e1251b;
  color: #fff;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 1px;
}
.cover-logo-mark {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #fff;
}
/* 中：作品信息 */
.info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  gap: 6px;
  padding-top: 3px;
}
.info-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 右：操作按钮（从右至左：去写作 · 导出） */
.actions {
  flex: none;
  display: flex;
  align-items: flex-end;
  justify-content: flex-end;
  gap: 10px;
  padding-right: 2px;
  padding-bottom: 2px;
}
.btn {
  border: none;
  border-radius: 0;
  padding: 8px 18px;
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: background-color 0.15s, border-color 0.15s, color 0.15s;
}
.btn-primary {
  background: #1664ff;
  color: #fff;
}
.btn-primary:hover {
  background: #0f55e6;
}
.btn-secondary {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--muted);
}
.btn-secondary:hover {
  border-color: var(--accent);
  color: var(--text);
}
.btn-danger {
  background: var(--bg-card);
  border: 1px solid #fca5a5;
  color: #dc2626;
}
.btn-danger:hover {
  background: #fef2f2;
  border-color: #f87171;
}
/* 导出下拉 */
.export-wrap {
  position: relative;
}
.btn-secondary:hover,
.btn-secondary.on {
  border-color: var(--accent);
  color: var(--text);
}
.export-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  display: flex;
  flex-direction: column;
  min-width: 168px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 0;
  box-shadow: 0 8px 22px rgba(16, 24, 40, 0.12);
  z-index: 20;
  padding: 4px;
}
.export-menu button {
  border: none;
  background: none;
  text-align: left;
  padding: 8px 10px;
  font-size: 13px;
  color: var(--muted);
  cursor: pointer;
  font-family: inherit;
}
.export-menu button:hover {
  background: var(--soft);
  color: var(--text);
}
.opening {
  margin-top: 18px;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--muted);
  font-size: 14px;
  min-height: 22px;
}
.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex: none;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.phase {
  color: var(--text);
  font-weight: 500;
}
.dots i {
  font-style: normal;
  animation: blink 1.4s infinite;
}
.dots i:nth-child(2) { animation-delay: 0.2s; }
.dots i:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink {
  0%, 20% { opacity: 0; }
  40% { opacity: 1; }
}
.note {
  margin-top: 34px;
  color: var(--muted);
  font-size: 13px;
}
@media (max-width: 640px) {
  .cta {
    flex-direction: column;
    align-items: center;
  }
  .premise-input {
    width: 100%;
    max-width: 92vw;
  }
}
</style>