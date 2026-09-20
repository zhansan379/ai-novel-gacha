<script setup lang="ts">
import { ref } from 'vue'
import { useDecisionStore } from '../stores/decision'
import type { Card, DecisionMode } from '../types'

const store = useDecisionStore()
const tab = ref<DecisionMode>('gacha_draw')

const MODES: { key: DecisionMode; label: string }[] = [
  { key: 'gacha_draw', label: '盲抽' },
  { key: 'gacha_pick', label: '明选' },
  { key: 'free', label: '自由输入' },
]

function rarityClass(r: Card['rarity']) {
  return `rarity rarity-${r.toLowerCase()}`
}

function kindLabel(kind: string) {
  const map: Record<string, string> = {
    draw: '盲抽', pick: '明选', free: '自由输入',
  }
  return map[kind] ?? kind
}
</script>

<template>
  <section class="decision-panel">
    <p v-if="store.error" class="error">{{ store.error }}</p>

    <!-- 非阻塞结果横幅：上一分歧已推进 + 质检（新卡池已在下方直接呈现） -->
    <div v-if="store.lastAction" class="result-bar">
      <span class="applied-note">
        已推进{{ kindLabel(store.lastAction.kind) }}<template v-if="store.lastAction.card">「{{ store.lastAction.card.title }}」</template>
      </span>
      <span v-if="store.lastConsistency && !store.lastConsistency.passed" class="quality warn">
        一致性：{{ store.lastConsistency.issues.length }} 处待确认
      </span>
      <span v-else-if="store.lastLint.some((i) => i.severity === 'block')" class="quality warn">
        去 AI 味：{{ store.lastLint.filter((i) => i.severity === 'block').length }} 处模板感需润色
      </span>
      <span v-else class="quality ok">质检通过（无 AI 味阻断项 · 一致性无冲突）</span>
      <button class="btn ghost undo" :disabled="store.loading" @click="store.undo">
        撤销上一步
      </button>
    </div>

    <!-- 下一分歧决策区：始终展示 -->
    <h3 class="panel-title">
      剧情分歧 · 决定故事去向<span v-if="store.decisionNo" class="node-no">（节点 {{ store.decisionNo }}）</span>
    </h3>
    <nav class="tabs">
      <button
        v-for="m in MODES"
        :key="m.key"
        :class="['tab', { active: tab === m.key }]"
        @click="tab = m.key"
      >
        {{ m.label }}
      </button>
    </nav>

    <!-- 盲抽 -->
    <div v-if="tab === 'gacha_draw'" class="mode-body">
      <p class="hint">在完全不知道结果的情况下随机揭晓一张命运卡。</p>
      <button class="btn primary big" :disabled="store.loading" @click="store.draw">
        {{ store.loading ? '抽卡中…' : '抽一枚命运卡' }}
      </button>
    </div>

    <!-- 明选 -->
    <div v-else-if="tab === 'gacha_pick'" class="mode-body">
      <p class="hint">展示所有命运卡，点选一张立即按该走向推进（点卡即生成）。</p>
      <div class="pick-grid">
        <button
          v-for="card in store.cards"
          :key="card.card_id"
          :disabled="store.loading"
          :class="['card', rarityClass(card.rarity), { chosen: store.revealed?.card_id === card.card_id }]"
          @click="store.applyCard(card.card_id)"
        >
          <span class="card-rarity">{{ card.rarity }}</span>
          <span class="card-label">{{ card.label }}</span>
          <h4>{{ card.title }}</h4>
          <p>{{ card.content }}</p>
        </button>
      </div>
    </div>

    <!-- 自由输入 -->
    <div v-else class="mode-body">
      <p class="hint">输入任意指令引导剧情（加事件 / 加角色 / 切场景 / 补设定…）。</p>
      <textarea
        v-model="store.customInstruction"
        rows="3"
        maxlength="500"
        placeholder="例：让主角在旧码头发现一张藏宝图……"
      />
      <button
        class="btn primary"
        :disabled="store.loading || !store.customInstruction.trim()"
        @click="store.apply"
      >
        {{ store.loading ? '生成中…' : '按我的输入推进' }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.decision-panel {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px;
  background: var(--bg-card);
}
.panel-title {
  margin: 0 0 12px;
}
.error {
  color: #b0452e;
  font-size: 13px;
  margin: 0 0 10px;
}
.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}
.tab {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-card);
  cursor: pointer;
  color: var(--muted);
}
.tab.active {
  background: var(--accent);
  color: #fffdf6;
}
.hint {
  color: var(--muted);
  font-size: 13px;
  margin-top: 0;
}
.mode-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.card {
  border: 2px solid #d1cbb8;
  border-radius: 10px;
  padding: 14px;
  text-align: left;
  background: #fffdf6;
  position: relative;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.18s ease;
}
.card:hover:not(:disabled) {
  transform: translateY(-3px);
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.08);
}
.card.reveal {
  animation: reveal 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) both; /* 卡牌揭示作为唯一辨识度动效 */
}
@keyframes reveal {
  from { transform: translateY(10px) scale(0.9); opacity: 0; }
  to { transform: none; opacity: 1; }
}
.card h4 {
  margin: 6px 0 4px;
  font-size: 16px;
}
.card p {
  margin: 0;
  color: #374151;
  font-size: 14px;
}
.card-rarity {
  position: absolute;
  top: 10px;
  right: 12px;
  font-weight: 800;
}
.card-label {
  font-size: 12px;
  color: #9ca3af;
  background: #f3f4f6;
  padding: 1px 6px;
  border-radius: 4px;
}
.rarity-n { border-color: #9ca3af; }
.rarity-r { border-color: #3b82f6; }
.rarity-sr { border-color: #a855f7; }
.rarity-ssr { border-color: #f59e0b; }
.rarity-n .card-rarity { color: #6b7280; }
.rarity-r .card-rarity { color: #3b82f6; }
.rarity-sr .card-rarity { color: #a855f7; }
.rarity-ssr .card-rarity { color: #f59e0b; }
.pick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}
.card.chosen {
  outline: 3px solid #10b981;
}
.btn {
  padding: 8px 18px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  align-self: flex-start;
}
.btn.primary {
  background: var(--accent);
  color: #fffdf6;
  transition: background-color 0.15s, transform 0.15s;
}
.btn.primary:hover:not(:disabled) {
  background: #75572f;
  transform: translateY(-2px);
}
.btn.big {
  font-size: 15px;
  padding: 12px 26px;
  font-weight: 600;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn.ghost {
  background: var(--bg-card);
  color: var(--muted);
  border: 1px solid var(--border);
}
.btn.ghost:hover:not(:disabled) {
  background: var(--accent-soft);
}
.applied-note {
  color: #059669;
  font-weight: 600;
  margin: 0;
}
.result-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  background: #f2efe4;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  margin: 0 0 14px;
}
.result-bar .quality {
  margin: 0;
  padding: 3px 10px;
}
.result-bar .undo {
  margin-left: auto;
  align-self: center;
  padding: 4px 12px;
  font-size: 13px;
}
.node-no {
  color: #9ca3af;
  font-weight: 400;
  font-size: 13px;
}
.quality {
  font-size: 13px;
  padding: 8px 10px;
  border-radius: 6px;
  margin: 4px 0;
}
.quality.ok {
  color: #059669;
  background: #ecfdf5;
}
.quality.warn {
  color: #b45309;
  background: #fffbeb;
}
textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-family: inherit;
  background: #fffdf6;
}
</style>