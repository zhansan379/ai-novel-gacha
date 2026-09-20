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

    <!-- 已提交：展示结果 + 进入下一分歧 -->
    <template v-if="store.lastAction">
      <h3 class="panel-title">剧情推进 · {{ kindLabel(store.lastAction.kind) }}</h3>
      <div
        v-if="store.lastAction.card"
        class="card"
        :class="rarityClass(store.lastAction.card.rarity)"
      >
        <span class="card-rarity">{{ store.lastAction.card.rarity }}</span>
        <span class="card-label">{{ store.lastAction.card.label }}</span>
        <h4>{{ store.lastAction.card.title }}</h4>
        <p>{{ store.lastAction.card.content }}</p>
      </div>
      <p v-else class="applied-note">已按你的自由输入推进剧情。</p>
      <button class="btn primary big" :disabled="store.loading" @click="store.next">
        {{ store.loading ? '生成中…' : '进入下一分歧' }}
      </button>
    </template>

    <!-- 待决策 -->
    <template v-else>
      <h3 class="panel-title">剧情分歧 · 决定故事去向</h3>
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
          {{ store.loading ? '抽卡中…' : '抽 卡' }}
        </button>
      </div>

      <!-- 明选 -->
      <div v-else-if="tab === 'gacha_pick'" class="mode-body">
        <p class="hint">展示所有命运卡，点选你想采用的走向。</p>
        <div class="pick-grid">
          <button
            v-for="card in store.cards"
            :key="card.card_id"
            :class="['card', rarityClass(card.rarity), { chosen: store.revealed?.card_id === card.card_id }]"
            @click="store.pickLocal(card.card_id)"
          >
            <span class="card-rarity">{{ card.rarity }}</span>
            <span class="card-label">{{ card.label }}</span>
            <h4>{{ card.title }}</h4>
            <p>{{ card.content }}</p>
          </button>
        </div>
        <button
          v-if="store.revealed"
          class="btn primary"
          :disabled="store.loading"
          @click="store.apply"
        >
          {{ store.loading ? '生成中…' : `采用「${store.revealed.title}」` }}
        </button>
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
    </template>
  </section>
</template>

<style scoped>
.decision-panel {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 18px;
  background: #fafafa;
}
.panel-title {
  margin: 0 0 12px;
}
.error {
  color: #dc2626;
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
  border: 1px solid #d1d5db;
  border-radius: 999px;
  background: #fff;
  cursor: pointer;
}
.tab.active {
  background: #1f2937;
  color: #fff;
}
.hint {
  color: #6b7280;
  font-size: 13px;
  margin-top: 0;
}
.mode-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.card {
  border: 2px solid #d1d5db;
  border-radius: 10px;
  padding: 14px;
  text-align: left;
  background: #fff;
  position: relative;
  cursor: pointer;
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
  background: #1f2937;
  color: #fff;
}
.btn.big {
  font-size: 16px;
  padding: 12px 28px;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.applied-note {
  color: #059669;
  font-weight: 600;
  margin: 6px 0;
}
textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 10px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-family: inherit;
}
</style>