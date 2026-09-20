<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import BlueprintPanel from '../components/BlueprintPanel.vue'

const route = useRoute()
const router = useRouter()
const storyId = route.params.id as string
</script>

<template>
  <section class="lore">
    <header class="lore-head">
      <button class="back" @click="router.back()">← 返回阅读</button>
      <div class="head-txt">
        <h2>世界观 · 历史线</h2>
        <p class="sub">地理、力量体系、势力、角色关系与剧情进度一览</p>
      </div>
    </header>
    <BlueprintPanel :story-id="storyId" />
  </section>
</template>

<style scoped>
.lore {
  max-width: 760px;
  margin: 0 auto;
}
.lore-head {
  display: flex;
  align-items: flex-start;
  gap: 18px;
  padding-bottom: 14px;
  margin-bottom: 6px;
  border-bottom: 1px solid var(--border);
}
.back {
  flex: none;
  min-width: 96px;
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-card);
  color: var(--muted);
  font-size: 14px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}
.back:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.head-txt h2 {
  margin: 0 0 4px;
  font-size: 22px;
  color: #3a3124;
}
.sub {
  margin: 0;
  color: #a89782;
  font-size: 13px;
}
</style>