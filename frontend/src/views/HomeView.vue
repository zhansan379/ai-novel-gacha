<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const premise = ref('')

function createStory() {
  router.push({ name: 'story', params: { id: 'demo' } })
}
</script>

<template>
  <section class="home">
    <h1>命运抽卡 · AI 互动小说</h1>
    <p class="sub">
      输入一句灵感或题材，系统为你搭建世界观、角色与大纲；每个剧情分歧点，你可以
      <strong>抽一张命运卡</strong> 或用 <strong>自由输入</strong> 决定故事去向。
    </p>

    <div class="cta">
      <input
        v-model="premise"
        class="premise-input"
        maxlength="200"
        placeholder="例：一个失忆的杀手想找回身份……（留空则随机开书）"
      />
      <button class="btn primary big" @click="createStory">开 书</button>
    </div>

    <p class="note">当前为 MVP 骨架：决策/抽卡 UI 已可交互（内置占位卡池），正文生成待接入 LLM。</p>
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
.note {
  margin-top: 40px;
  color: #9ca3af;
  font-size: 13px;
}
</style>