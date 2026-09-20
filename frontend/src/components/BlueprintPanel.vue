<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { Blueprint, StyleProfile, TimelineEvent } from '../types'

const props = defineProps<{ storyId: string }>()
const bp = ref<Blueprint | null>(null)
const styles = ref<StyleProfile[]>([])
const timeline = ref<TimelineEvent[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const styleName = (id?: string) => {
  if (!id) return ''
  return styles.value.find((s) => s.id === id)?.name ?? id
}

const statusMap: Record<string, string> = { planted: '已埋', advanced: '推进中', paid_off: '已兑现' }
const statusText = (s: string) => statusMap[s] ?? s

const labelMap: Record<string, string> = {
  EVENT: '事件', ACTION: '行动', SCENE: '场景', MEETING: '相遇', FORESHADOW: '伏笔', CUSTOM: '自由',
}
const labelText = (l?: string | null) => (l ? (labelMap[l] ?? l) : '')

onMounted(async () => {
  loading.value = true
  error.value = null
  try {
    ;[bp.value, styles.value, timeline.value] = await Promise.all([
      api.getBlueprint(props.storyId), api.getStyles(),
      api.getTimeline(props.storyId).then((r) => r.timeline),
    ])
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="blueprint">
    <p v-if="loading" class="hint">加载设定…</p>
    <p v-else-if="error" class="err">{{ error }}</p>
    <template v-else-if="bp">
      <p v-if="styleName(bp.style)" class="style-tag">文风：{{ styleName(bp.style) }}</p>
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
          <div v-if="c.moves?.length" class="moves">动向：{{ c.moves.join(' → ') }}</div>
        </div>
      </details>

      <details v-if="bp.foreshadows?.length" class="blk">
        <summary>伏笔账本（{{ bp.foreshadows.length }}）</summary>
        <ul>
          <li v-for="f in bp.foreshadows" :key="f.id">
            <span class="chip" :class="'fs-' + f.status">{{ statusText(f.status) }}</span>
            <span>{{ f.text }}</span>
            <span v-if="f.origin" class="muted">（{{ f.origin }}）</span>
          </li>
        </ul>
      </details>

      <details class="blk">
        <summary>剧情时间线（{{ timeline.length }}）<span class="muted">· 随抽卡追加，非世界历史线</span></summary>
        <ol v-if="timeline.length" class="tl">
          <li v-for="ev in timeline" :key="ev.no">
            <span class="chip">{{ labelText(ev.label) }}</span><b>{{ ev.title || '自由决策' }}</b>
            <div class="muted">{{ ev.summary }}</div>
          </li>
        </ol>
        <p v-else class="muted">尚无剧情（每做一次决策追加一条）</p>
      </details>
    </template>
  </section>
</template>

<style scoped>
.blueprint {
  margin-top: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 6px 14px 10px;
  background: #fcfcfd;
}
.style-tag {
  margin: 8px 0 2px;
  font-size: 13px;
  color: #4f46e5;
  font-weight: 600;
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
.moves {
  color: #047857;
  font-size: 12px;
  margin-top: 2px;
}
.fs {
  color: #b45309;
}
.chip {
  display: inline-block;
  font-size: 12px;
  padding: 0 6px;
  border-radius: 4px;
  margin-right: 6px;
}
.fs-planted {
  background: #fef3c7;
  color: #b45309;
}
.fs-advanced {
  background: #dbeafe;
  color: #1d4ed8;
}
.fs-paid_off {
  background: #d1fae5;
  color: #047857;
}
.muted {
  color: #9ca3af;
}
.tl {
  list-style: none;
  padding-left: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}
.tl li {
  padding: 6px 8px;
  background: #fff;
  border-radius: 6px;
  border-left: 3px solid #c7d2fe;
}
.err {
  color: #dc2626;
}
.hint {
  color: #9ca3af;
}
</style>