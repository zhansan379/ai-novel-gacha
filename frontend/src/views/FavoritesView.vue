<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useDecisionStore } from '../stores/decision'
import type { StoryListItem } from '../types'

const router = useRouter()
const store = useDecisionStore()

const favs = ref<StoryListItem[]>([])
const loading = ref(false)
const error = ref('')

/** 由 story_id 派生一个稳定的 4 位“书号”，用于封面占位（与首页书架一致）。 */
function bookNo(id: string): string {
  let sum = 0
  for (const ch of id) sum += ch.charCodeAt(0)
  return String((sum % 9000) + 1000)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const ids = store.getBookmarkedIds()
    const stories = (await api.getStories()).stories
    const byId = new Map(stories.map((s) => [s.story_id, s]))
    // 保持收藏顺序，最近收藏在前
    favs.value = ids
      .slice()
      .reverse()
      .map((id) => byId.get(id))
      .filter((s): s is StoryListItem => !!s)
  } catch {
    error.value = '收藏列表加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function openStory(id: string) {
  router.push({ name: 'story', params: { id } })
}

function unbook(id: string) {
  store.setBookmarked(id, false)
  favs.value = favs.value.filter((s) => s.story_id !== id)
}

onMounted(load)
</script>

<template>
  <section class="fav-page">
    <div class="fav-inner">
      <div class="fav-head">
        <button type="button" class="back" @click="router.push({ name: 'home' })">← 返回书架</button>
        <h2 class="title">
          我的收藏
          <span v-if="favs.length" class="count">{{ favs.length }} 本</span>
        </h2>
        <p class="head-hint">在阅读页面包屑分割线右侧点书签，即可收藏本书。</p>
      </div>

      <p v-if="loading" class="hint">加载中…</p>
      <p v-if="error" class="error">{{ error }}</p>

      <div v-if="favs.length" class="fav-list">
        <div v-for="s in favs" :key="s.story_id" class="book-card">
          <!-- 左：封面（点击进入正文） -->
          <div class="cover" aria-hidden="true" @click="openStory(s.story_id)">
            <span class="cover-title">{{ s.premise || '未命名' }}</span>
            <span class="cover-no">{{ bookNo(s.story_id) }}</span>
            <span class="cover-logo"><i class="cover-logo-mark"></i>抽卡小说</span>
          </div>

          <!-- 中：作品信息 -->
          <div class="info">
            <h4 class="info-title">{{ s.premise || '未命名' }}
              <span v-if="s.status === 'completed'" class="end-badge">完结</span>
            </h4>
            <p class="info-synopsis">{{ s.synopsis || '（暂无简介）' }}</p>
          </div>

          <!-- 右：操作 -->
          <div class="actions">
            <button type="button" class="btn btn-secondary" @click="unbook(s.story_id)">取消收藏</button>
            <button type="button" class="btn btn-primary" @click="openStory(s.story_id)">去写作</button>
          </div>
        </div>
      </div>
      <p v-else-if="!loading && !error" class="empty">还没有收藏的书——在阅读页面包屑分割线右侧的书签点亮即可收藏。</p>
    </div>
  </section>
</template>

<style scoped>
.fav-page {
  width: min(var(--reader-width, 820px), calc(100vw - 130px));
  max-width: var(--reader-width, 820px);
  margin: 0 auto;
  padding: 32px 8px 60px;
}
.fav-head {
  margin-bottom: 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}
.back {
  border: none;
  background: none;
  padding: 0;
  margin-bottom: 10px;
  color: var(--muted);
  font-size: 13px;
  cursor: pointer;
}
.back:hover {
  color: var(--accent);
}
.title {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  letter-spacing: 1px;
  color: var(--text);
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.count {
  font-size: 14px;
  font-weight: 600;
  color: var(--accent);
}
.head-hint {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--muted);
}
.hint {
  color: var(--muted);
  font-size: 13px;
}
.error {
  color: #dc2626;
  font-size: 13px;
}
.fav-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
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
  cursor: pointer;
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
.end-badge {
  display: inline-block;
  margin-left: 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--bg-card);
  background: var(--accent);
  border-radius: 3px;
  padding: 1px 6px;
  vertical-align: 2px;
}
.info-synopsis {
  margin: 0;
  font-size: 13px;
  color: var(--muted);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
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
.empty {
  margin: 22px 0 0;
  font-size: 13px;
  color: var(--muted);
}
</style>