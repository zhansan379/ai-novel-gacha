<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { api } from '../api/client'
import type { ECharts } from 'echarts/core'
import type { Blueprint, Faction } from '../types'

echarts.use([GraphChart, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps<{ storyId: string }>()

const el = ref<HTMLElement | null>(null)
const box = ref<HTMLElement | null>(null)
let chart: ECharts | null = null
let resizeObserver: ResizeObserver | null = null

const hasGraph = ref(false)
const noEdges = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)
const bpData = ref<Blueprint | null>(null)

const CATEGORIES = [
  { name: '角色', itemStyle: { color: '#1d4ed8' } },
  { name: '势力', itemStyle: { color: '#b45309' } },
  { name: '其他', itemStyle: { color: '#047857' } },
]

/** 势力归一：兼容旧版纯名字数组与新版 {name, description} 对象。 */
function normalFactions(bp: Blueprint): Faction[] {
  return (bp.world.factions ?? []).map((f) =>
    (typeof f === 'string' ? { name: f, description: '' } : f))
}

/** 抽取关系图谱涉及的实体集合（角色 + 势力 + 关系边里出现的新名字）。 */
function collectNodes(bp: Blueprint) {
  const names = new Set<string>()
  for (const c of bp.characters) if (c.name) names.add(c.name)
  const factions = new Set<string>(normalFactions(bp).map((f) => f.name))
  for (const r of bp.relations ?? []) if (r.a) names.add(r.a)
  for (const r of bp.relations ?? []) if (r.b) names.add(r.b)
  return { names, factions }
}

function buildOption(bp: Blueprint) {
  const { names, factions } = collectNodes(bp)
  const descMap = new Map(normalFactions(bp).filter((f) => f.description).map((f) => [f.name, f.description as string]))
  const nodes = Array.from(names).map((name) => ({
    name,
    symbolSize: factions.has(name) ? 26 : 20,
    category: factions.has(name) ? '势力' : '角色',
    desc: descMap.get(name),
  }))
  const links: Array<{ source: string; target: string; note?: string; label?: { show: boolean; formatter: string } }> = []
  for (const r of bp.relations ?? []) {
    if (!r.a || !r.b) continue
    const edge: { source: string; target: string; note?: string; label?: { show: boolean; formatter: string } } =
      { source: r.a, target: r.b, note: r.note }
    if (r.label) edge.label = { show: true, formatter: r.label }
    links.push(edge)
  }
  return {
    tooltip: {
      trigger: 'item',
      extraCssText: 'max-width: 300px; white-space: normal;',
      confine: true,
      formatter: (p: { dataType?: string; data?: { name?: string; note?: string; desc?: string } }) => {
        if (p.dataType === 'edge') return p.data?.note ?? ''
        const name = (p.data && p.data.name) || ''
        const desc = p.data?.desc || ''
        return desc ? `${name}\n${desc}` : name
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
    // 只要有已知节点就画；无关系边时退化为只展示孤立角色/势力，不凭空消失
    hasGraph.value = names.size > 0
    noEdges.value = !(bp.relations ?? []).length
    bpData.value = bp
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

/** 数据就绪后创建/更新图表。只在数据与 hasGraph 都成立时执行；用 flush:"post" 保证 el 已挂载。 */
watch([hasGraph, bpData], async () => {
  if (!hasGraph.value || !bpData.value) return
  await nextTick()
  if (!el.value) return
  chart = chart ?? echarts.init(el.value)
  chart.setOption(buildOption(bpData.value), true)
}, { flush: 'post' })

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
    <template v-else>
      <p v-if="noEdges" class="hint">暂无关系边，以下为已知角色/势力（随剧情推进会连出关系）</p>
      <div ref="box" class="kg-box">
        <div ref="el" class="kg-canvas" />
      </div>
    </template>
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