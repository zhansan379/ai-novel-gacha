<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useDecisionStore } from '../stores/decision'
import BlueprintPanel from '../components/BlueprintPanel.vue'
import DecisionPanel from '../components/DecisionPanel.vue'

const route = useRoute()
const store = useDecisionStore()

onMounted(async () => {
  const id = route.params.id as string | undefined
  // 本会话刚创建（Home 已 set storyId）→ 直接使用；否则按 id 载入已有故事
  if (id && store.storyId !== id) {
    await store.load(id)
  }
})
</script>

<template>
  <section class="story">
    <header class="story-head">
      <h2>故事</h2>
      <p v-if="store.loading" class="phase">加载中…</p>
    </header>

    <blockquote v-if="store.synopsis" class="synopsis">{{ store.synopsis }}</blockquote>

    <BlueprintPanel v-if="store.storyId" :story-id="store.storyId" />

    <div class="layout">
      <div class="prose">
        <article v-for="(p, i) in store.passages" :key="i" class="passage">
          <p>{{ p }}</p>
        </article>
        <div v-if="store.streamingText || (store.loading && !store.lastAction)" class="streaming">
          <span v-if="store.streamingText" class="caret">{{ store.streamingText }}</span>
          <span v-else class="hint">正文生成中…</span>
        </div>
        <p v-if="store.error" class="error">{{ store.error }}</p>
      </div>
      <DecisionPanel />
    </div>
  </section>
</template>

<style scoped>
.story-head h2 {
  margin: 0 0 6px;
}
.phase {
  color: #9ca3af;
  font-size: 13px;
}
.synopsis {
  margin: 0 0 16px;
  padding: 12px 16px;
  border-left: 4px solid #1f2937;
  background: #f7f7f8;
  color: #4b5563;
}
.layout {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 20px;
  align-items: start;
}
.passage {
  line-height: 1.9;
  color: #374151;
  text-indent: 2em;
  margin-bottom: 14px;
  white-space: pre-wrap;
}
.streaming {
  line-height: 1.9;
  color: #4b5563;
  text-indent: 2em;
  white-space: pre-wrap;
  border-left: 3px solid #10b981;
  padding-left: 10px;
  min-height: 2em;
}
.streaming .caret::after {
  content: '▍';
  color: #10b981;
  animation: blink 1s steps(2) infinite;
}
.streaming .hint {
  color: #9ca3af;
}
@keyframes blink {
  50% { opacity: 0; }
}
.error {
  color: #dc2626;
}
@media (max-width: 760px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
</style>