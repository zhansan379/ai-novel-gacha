<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { Blueprint } from '../types'

const props = defineProps<{ storyId: string }>()
const bp = ref<Blueprint | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

onMounted(load)
async function load() {
  loading.value = true
  error.value = null
  try {
    bp.value = await api.getBlueprint(props.storyId)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="blueprint">
    <p v-if="loading" class="hint">加载设定…</p>
    <p v-else-if="error" class="err">{{ error }}</p>
    <template v-else-if="bp">
      <details class="blk">
        <summary>世界观</summary>
        <p v-if="bp.world.geography" class="row"><b>地理：</b>{{ bp.world.geography }}</p>
        <p v-if="bp.world.power_system" class="row"><b>力量体系：</b>{{ bp.world.power_system }}</p>
        <p v-if="bp.world.rules?.length" class="row">
          <b>规则：</b><span v-for="(r, i) in bp.world.rules" :key="i" class="chip">{{ r }}</span>
        </p>
        <p v-if="bp.world.factions?.length" class="row"><b>势力：</b>{{ bp.world.factions.join('、') }}</p>
        <p v-if="bp.world.constraints?.length" class="row"><b>限制：</b>{{ bp.world.constraints.join('；') }}</p>
        <p v-if="!bp.world.geography && !bp.world.rules?.length" class="muted">暂无世界观设定</p>
      </details>

      <details class="blk">
        <summary>历史线（{{ bp.history.length }}）</summary>
        <ul v-if="bp.history.length">
          <li v-for="(h, i) in bp.history" :key="i">
            <b>{{ h.era }}</b>：{{ h.event }} → {{ h.impact }}
          </li>
        </ul>
        <p v-else class="muted">暂无</p>
      </details>

      <details class="blk">
        <summary>角色（{{ bp.characters.length }}）</summary>
        <div v-for="(c, i) in bp.characters" :key="i" class="char">
          <b>{{ c.name }}</b>
          <span class="tag" :class="c.role === 'protagonist' ? 'prot' : 'supp'">
            {{ c.role === 'protagonist' ? '主角' : '配角' }}
          </span>
          <div v-if="c.goal">目标：{{ c.goal }}</div>
          <div v-if="c.inner_need">内在需求：{{ c.inner_need }}</div>
          <div v-if="c.flaw">缺点：{{ c.flaw }}</div>
          <div v-if="c.trait" class="muted">特征：{{ c.trait }}</div>
        </div>
      </details>

      <details class="blk" open>
        <summary>卷 · 章大纲（{{ bp.outline.length }}）</summary>
        <ul>
          <li v-for="o in bp.outline" :key="o.no">
            <b>{{ o.type === 'act' ? '卷' : '章' }} {{ o.no }} · {{ o.title }}</b>
            <span v-if="o.goal">—— {{ o.goal }}</span>
            <span v-if="o.foreshadow" class="fs">（伏笔：{{ o.foreshadow }}）</span>
          </li>
        </ul>
      </details>
    </template>
  </section>
</template>

<style scoped>
.blueprint {
  margin-top: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 6px 14px;
  background: #fcfcfd;
}
.blk {
  padding: 8px 0;
  border-bottom: 1px dashed #eceff3;
}
.blk:last-child {
  border-bottom: none;
}
summary {
  cursor: pointer;
  font-weight: 600;
  margin-bottom: 4px;
}
.row {
  margin: 4px 0;
}
ul {
  margin: 4px 0;
  padding-left: 18px;
}
li {
  margin: 3px 0;
}
.chip {
  display: inline-block;
  background: #eef2f7;
  border-radius: 4px;
  padding: 1px 6px;
  margin-right: 6px;
}
.tag {
  font-size: 12px;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 4px;
}
.prot {
  background: #e0edff;
  color: #1d4ed8;
}
.supp {
  background: #f3e8ff;
  color: #7e22ce;
}
.char {
  margin: 6px 0;
  padding: 6px;
  background: #fff;
  border-radius: 6px;
}
.fs {
  color: #b45309;
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