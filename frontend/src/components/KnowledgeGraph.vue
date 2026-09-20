<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { api } from '../api/client'
import type { ECharts } from 'echarts/core'
import type { Blueprint, RelationEdge } from '../types'

echarts.use([GraphChart, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps<{ storyId: string }>()

const el = ref<HTMLElement | null>(null)
const box = ref<HTMLElement | null>(null)
let chart: ECharts | null = null
let resizeObserver: ResizeObserver | null = null

const hasGraph = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)

const CATEGORIES = [
  { name: '角色', itemStyle: { color: '#1d4ed8' } },
  { name: '势力', itemStyle: { color: '#b45309' } },
  { name: '其他', itemStyle: { color: '#047857' } },
]

/** 抽取关系图谱涉及的实体集合（角色 + 势力 + 关系边里出现的新名字）。 */
function collectNodes(bp: Blueprint) {
  const names = new Set<string>()
  for (const c of bp.characters) if (c.name) names.add(c.name)
  const factions = new Set<string>(bp.world.factions ?? [])
  for (const r of bp.relations ?? []) if (r.a) names.add(r.a)
  for (const r of bp.relations ?? []) if (r.b) names.add(r.b)
  return { names, factions }
}

function buildOption(bp: Blueprint) {
  const { names, factions } = collectNodes(bp)
  const nodes = Array.from(names).map((name) => ({
    name,
    symbolSize: factions.has(name) ? 26 : 20,
    category: factions.has(name) ? '势力' : '角色',
  }))
  const links: Array<{ source: string; target: string; label?: { show: boolean; formatter: string } }> = []
  for (const r of bp.relations ?? []) {
    if (!r.a || !r.b) continue
    const edge: { source: string; target: string; label?: { show: boolean; formatter: string } } =
      { source: r.a, target: r.b }
    if (r.label) edge.label = { show: true, formatter: r.label }
    links.push(edge)
  }
  return {
    tooltip: {
      trigger: 'item',
      formatter: (p: { dataType?: string; data?: { name?: string; note?: string }; value?: unknown; category?: unknown }) => {
        if (p.dataType === 'edge') return ''
        const matching = (bp.relations ?? [])
          .map((r: RelationEdge) => (p.data && (p.data.name === r.a || p.data.name === r.b)) ? r : null)
          .filter((r: RelationEdge | null): r is RelationEdge => !!r)
        if (!matching.length) return (p.data && p.data.name) || ''
        const lines = matching.map((r) => `${r.a} ${r.label ?? '与'} ${r.b}` + (r.note ? `\n　·${r.note}` : ''))
        return `${(p.data && p.data.name) || ''}\n${lines.join('\n')}`
      },
    },
    legend: { data: CATEGORIES.map((c) => c.name), bottom: 4, textStyle: { color: '#6b7280', fontSize: 12 } },
    series: [{
      type: 'graph',
      layout: 'force',
      data: nodes,
      links,
      categories: CATEGORIES,
      roam: true,
      draggable: true,
      force: { repulsion: 180, edgeLength: 110, gravity: 0.12 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 3 } },
      label: { show: true, position: 'bottom', fontSize: 12, color: '#374151' },
      lineStyle: { color: '#c7d2fe', width: 2, curveness: 0.05 },
    }],
    animation: true,
  }
}

async function render() {
  loading.value = true
  error.value = null
  try {
    const bp = await api.getBlueprint(props.storyId)
    const { names } = collectNodes(bp)
    hasGraph.value = names.size > 0 && !!bp.relations?.length
    if (!hasGraph.value) return
    await nextTick()
    if (!el.value) return
    chart = chart ?? echarts.init(el.value)
    chart.setOption(buildOption(bp), true)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await render()
  if (box.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(box.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})

watch(() => props.storyId, render)
</script>

<template>
  <section class="kg">
    <header class="kg-head">
      <h3>关系图谱</h3>
      <span class="hint">人物与势力之间的已知关系（随剧情推进更新）</span>
    </header>
    <p v-if="loading" class="hint">加载关系图谱…</p>
    <p v-else-if="error" class="err">{{ error }}</p>
    <p v-else-if="!hasGraph" class="hint">暂无关系数据（推进剧情后会逐步生成关系边）</p>
    <div v-else ref="box" class="kg-box">
      <div ref="el" class="kg-canvas" />
    </div>
  </section>
</template>

<style scoped>
.kg {
  margin-top: 16px;
  border: 1px solid var(--border);
  padding: 12px 14px 10px;
  background: var(--bg-card);
}
.kg-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 8px;
}
.kg-head h3 {
  margin: 0;
  font-size: 16px;
  color: #3a3124;
}
.hint {
  color: #9ca3af;
  font-size: 12px;
}
.err {
  color: #dc2626;
}
.kg-box {
  position: relative;
  width: 100%;
  height: 420px;
}
.kg-canvas {
  position: absolute;
  inset: 0;
}
</style>