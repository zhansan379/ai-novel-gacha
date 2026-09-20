<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { api } from '../api/client'
import CollapsePanel from './CollapsePanel.vue'

// 展示运行时检索结果：生成前按前提/剧情方向，从内置知识库（向量检索）与联网检索
// 命中的真实事实，随生成注入上下文。每条 grounding 行形如「• 刘强东：…」或
// 「• 网络检索『token』：…」，据此区分来源。
const props = defineProps<{ storyId: string }>()

const loading = ref(false)
const error = ref<string | null>(null)
const lines = ref<string[]>([])

const split = (g: string[]) => {
  const kb: string[] = []
  const web: string[] = []
  for (const raw of g) {
    const txt = raw.replace(/^[•·]\s*/, '').trim()
    if (!txt) continue
    if (txt.startsWith('网络检索')) web.push(txt)
    else kb.push(txt)
  }
  return { kb, web }
}

const grouped = computed(() => split(lines.value))
const total = computed(() => grouped.value.kb.length + grouped.value.web.length)
const kbCount = computed(() => grouped.value.kb.length)
const webCount = computed(() => grouped.value.web.length)

onMounted(async () => {
  loading.value = true
  error.value = null
  try {
    const bp = await api.getBlueprint(props.storyId)
    lines.value = bp.grounding ?? []
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="grounding">
    <p v-if="loading" class="hint">加载检索结果…</p>
    <p v-else-if="error" class="err">{{ error }}</p>
    <CollapsePanel v-else class="blk" :title="`事实基座 · 运行时检索（${total}）`">
      <template #hint>· 生成前按前提/剧情方向实时检索并注入，约束尊重史实</template>
      <template v-if="total">
        <div v-if="kbCount" class="group">
          <div class="g-title">知识库检索 <span class="count">{{ kbCount }}</span></div>
          <p v-for="(t, i) in grouped.kb" :key="'k' + i" class="fact">{{ t }}</p>
        </div>
        <div v-if="webCount" class="group">
          <div class="g-title">网络搜索 <span class="count">{{ webCount }}</span></div>
          <p v-for="(t, i) in grouped.web" :key="'w' + i" class="fact">{{ t }}</p>
        </div>
      </template>
      <p v-else class="muted">暂无检索到真实事实（纯架空故事不注入）</p>
    </CollapsePanel>
  </section>
</template>

<style scoped>
.grounding {
  margin-top: 16px;
  border: 1px solid var(--border);
  border-radius: 0;
  padding: 6px 14px 10px;
  background: var(--bg-card);
}
.blk {
  padding: 8px 0;
}
.group {
  margin: 8px 0 2px;
}
.g-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #4f46e5;
}
.count {
  font-weight: 400;
  color: #9ca3af;
}
.fact {
  margin: 4px 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text);
}
.muted {
  color: #9ca3af;
}
.err {
  color: #dc2626;
}
.hint {
  color: #9ca3af;
}
</style>