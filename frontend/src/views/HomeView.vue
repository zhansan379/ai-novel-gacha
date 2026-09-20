<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useDecisionStore } from '../stores/decision'
import type { StyleProfile } from '../types'

const router = useRouter()
const store = useDecisionStore()
const premise = ref('')
const styles = ref<StyleProfile[]>([])
const selectedStyle = ref<string>('')

onMounted(async () => {
  try {
    styles.value = await api.getStyles()
    selectedStyle.value = styles.value[0]?.id ?? ''
  } catch {
    styles.value = []
  }
})

async function createStory() {
  if (store.loading) return
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
    <h1>命运抽卡 · AI 互动小说</h1>
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
      <button class="btn primary big" :disabled="store.loading" @click="createStory">
        {{ store.loading ? '开书中…' : '开 书' }}
      </button>
    </div>

    <div class="style-row">
      <label class="style-label" for="style">文风：</label>
      <select v-model="selectedStyle" id="style" class="style-select">
        <option v-for="s in styles" :key="s.id" :value="s.id">{{ s.name }}</option>
      </select>
      <span class="style-desc">{{ styles.find((s) => s.id === selectedStyle)?.description }}</span>
    </div>

    <p v-if="store.error" class="error">{{ store.error }}</p>
    <p class="note">MVP：开书 → 设定/大纲 → 抽卡 → 正文 → 质检已可跑通（无 Key 用本地 mock）。</p>
  </section>
</template>

<style scoped>
.home {
  text-align: center;
  padding: 40px 0;
}
.sub {
  max-width: 640px;
  margin: 0 auto 24px;
  color: #4b5563;
}
.cta {
  display: flex;
  gap: 12px;
  justify-content: center;
}
.premise-input {
  width: min(520px, 70vw);
  padding: 12px 14px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 15px;
}
.btn {
  padding: 12px 24px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
}
.btn.primary {
  background: #1f2937;
  color: #fff;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.style-row {
  margin-top: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #6b7280;
  font-size: 14px;
}
.style-select {
  padding: 6px 10px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
}
.style-desc {
  max-width: 420px;
  text-align: left;
  color: #9ca3af;
  font-size: 13px;
}
.error {
  color: #dc2626;
}
.note {
  margin-top: 34px;
  color: #9ca3af;
  font-size: 13px;
}
</style>