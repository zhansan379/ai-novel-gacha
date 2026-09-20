<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useDecisionStore } from '../stores/decision'
import DecisionPanel from '../components/DecisionPanel.vue'

const route = useRoute()
const store = useDecisionStore()

onMounted(() => {
  // 进入故事页即触发第一个分歧点（骨架阶段用内置占位卡池）
  store.openNewDecision()
})
</script>

<template>
  <section class="story">
    <header class="story-head">
      <h2>故事 #{{ route.params.id }}</h2>
      <p class="phase">现状：前置搭建（世界观 / 历史 / 大纲）与会话生成待接入 LLM，先验证核心抽卡决策闭环。</p>
    </header>

    <div class="layout">
      <div class="prose">
        <h3>正文</h3>
        <div class="placeholder">
          占位正文区：接入 LLM 后，这里会流式展示生成的小说内容。
        </div>
      </div>
      <DecisionPanel v-if="store.hasDecision" />
    </div>
  </section>
</template>

<style scoped>
.story-head h2 {
  margin: 0 0 6px;
}
.phase {
  color: #6b7280;
  font-size: 13px;
}
.layout {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 20px;
  margin-top: 16px;
}
.prose h3 {
  margin-top: 0;
}
.placeholder {
  border: 1px dashed #d1d5db;
  border-radius: 10px;
  padding: 40px 20px;
  color: #9ca3af;
  text-align: center;
}
@media (max-width: 720px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
</style>