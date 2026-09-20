<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useDecisionStore } from '../stores/decision'

const router = useRouter()
const store = useDecisionStore()
const premise = ref('')

async function createStory() {
  if (store.loading) return
  await store.create(premise.value || '一个少年在雨夜的旧城、被迫背负一个不为人知的秘密')
  if (store.storyId) {
    router.push({ name: 'story', params: { id: store.storyId } })
  }
}
</script>

<template>
  <section class="home">
    <h1>命运抽卡 · AI 互动小说</h1>
    <p class="sub">
      输入一句灵感或题材，系统为你搭建世界观与大纲；每个剧情分歧点，你可以
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

    <p v-if="store.error" class="error">{{ store.error }}</p>
    <p class="note">当前为 MVP：抽卡 → 生成正文闭环已可跑通（未配置 Key 时用本地 mock 生成）。</p>
  </section>
</template>

<style scoped>
.home {
  text-align: center;
  padding: 40px 0;
}
.sub {
  max-width: 640px;
  margin: 0 auto 28px;
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
.error {
  color: #dc2626;
}
.note {
  margin-top: 40px;
  color: #9ca3af;
  font-size: 13px;
}
</style>