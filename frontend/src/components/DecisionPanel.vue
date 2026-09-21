<script setup lang="ts">
import { useDecisionStore } from '../stores/decision'
import type { Card } from '../types'

const store = useDecisionStore()

function rarityClass(r: Card['rarity']) {
  return `rarity rarity-${r.toLowerCase()}`
}

function kindLabel(kind: string) {
  const map: Record<string, string> = {
    draw: '盲抽', pick: '明选', free: '自由输入',
  }
  return map[kind] ?? kind
}

function labelCn(label: string) {
  const map: Record<string, string> = {
    EVENT: '事件', ACTION: '行动', SCENE: '场景', MEETING: '相遇', FORESHADOW: '伏笔',
  }
  return map[label] ?? label
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

    <!-- 统一决策区：点卡即生成 / 随机盲抽 / 自由输入，三者并存不再分页 -->
    <div class="pick-panel">
      <div class="pick-head">
        <span class="pick-count">{{ store.cards.length }} 张命运卡 · 点选即按该走向推进</span>
        <span v-if="store.cardsLoading && store.cards.length === 0" class="hint cards-loading">
          生成下一拍卡池…
        </span>
        <button
          class="btn primary draw-btn"
          :disabled="store.loading || store.cardsLoading"
          @click="store.draw"
        >
          {{ store.loading || store.cardsLoading ? '抽卡中…' : '随机盲抽一张' }}
        </button>
      </div>

      <div
        class="pick-grid"
        :style="{ gridTemplateColumns: `repeat(${store.cards.length}, minmax(150px, 220px))` }"
      >
        <button
          v-for="card in store.cards"
          :key="card.card_id"
          :disabled="store.loading || store.cardsLoading"
          :class="['card', rarityClass(card.rarity), { chosen: store.revealed?.card_id === card.card_id }]"
          @click="store.applyCard(card.card_id)"
        >
          <span class="card-rarity">{{ card.rarity }}</span>
          <h4>{{ card.title }}</h4>
          <p>{{ card.content }}</p>
          <span class="card-label">{{ labelCn(card.label) }}</span>
        </button>
      </div>
    </div>

    <!-- 自由输入 -->
    <div class="free-row">
      <p class="hint">或输入任意指令引导剧情（加事件 / 加角色 / 切场景 / 补设定…）。</p>
      <textarea
        v-model="store.customInstruction"
        rows="2"
        maxlength="500"
        placeholder="例：让主角在旧码头发现一张藏宝图……"
      />
      <button
        class="btn primary"
        :disabled="store.loading || store.cardsLoading || !store.customInstruction.trim()"
        @click="store.apply"
      >
        {{ store.loading || store.cardsLoading ? '生成中…' : '按我的输入推进' }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.decision-panel {
  padding: 2px;
}
.error {
  color: #b0452e;
  font-size: 13px;
  margin: 0 0 10px;
}
.hint {
  color: var(--muted);
  font-size: 13px;
  margin-top: 0;
}
.cards-loading {
  margin-left: auto;
  font-style: italic;
}
.pick-panel {
  margin-top: 4px;
}
.pick-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.pick-count {
  color: var(--muted);
  font-size: 13px;
}
.draw-btn {
  flex-shrink: 0;
}
.free-row {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px dashed var(--border);
}
.card {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 240px;
  border: 2px solid #d1cbb8;
  border-radius: 0;
  padding: 14px 15px 13px;
  text-align: left;
  background: var(--bg-card);
  position: relative;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.18s ease;
}
.card:hover:not(:disabled) {
  transform: translateY(-4px);
  box-shadow: 0 10px 22px rgba(0, 0, 0, 0.1);
}
.card.reveal {
  animation: reveal 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) both; /* 卡牌揭示作为唯一辨识度动效 */
}
@keyframes reveal {
  from { transform: translateY(10px) scale(0.9); opacity: 0; }
  to { transform: none; opacity: 1; }
}

/* 内置卡面材质（纯 CSS，无需即时生成资源）：
   素纸 N / 银箔 R / 烫金 SR / 镭射彩虹 SSR —— 每档一道扫过光泽 */
.card::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.25s ease;
}
.card:hover:not(:disabled)::before { opacity: 1; }

.card h4 {
  margin: 4px 0 6px;
  font-size: 16px;
  line-height: 1.35;
  position: relative;
  z-index: 1;
  text-align: center;
  color: var(--text);
}
.card p {
  margin: 0 0 12px;
  color: var(--text);
  font-size: 14px;
  flex: 1;
  position: relative;
  z-index: 1;
}
.card-rarity {
  font-size: 17px;
  font-weight: 800;
  letter-spacing: 2px;
  margin: 2px 0 8px;
  text-align: center;
  position: relative;
  z-index: 1;
}
.card-label {
  align-self: flex-start;
  font-size: 12px;
  letter-spacing: 1px;
  color: var(--muted);
  background: var(--accent-soft);
  padding: 2px 8px;
  border-radius: 0;
  position: relative;
  z-index: 1;
}

/* 素纸 N：最克制的纸面反光 */
.rarity-n { border-color: #9ca3af; }
.rarity-n::before {
  opacity: 0.3;
  background: linear-gradient(115deg, transparent 35%, rgba(255, 255, 255, 0.55) 48%, transparent 62%);
  background-size: 220% 220%;
  animation: sheen-sweep 4.5s ease-in-out infinite;
}

/* 银箔 R：冷银扫光（仿镭射卡银箔层） */
.rarity-r { border-color: #7d9bbf; }
.rarity-r::before {
  opacity: 0.5;
  background: linear-gradient(115deg, transparent 30%, rgba(215, 230, 245, 0.9) 42%, rgba(160, 190, 220, 0.7) 50%, transparent 64%);
  background-size: 220% 220%;
  animation: sheen-sweep 3.4s ease-in-out infinite;
}

/* 烫金 SR：暖金扫光 + 内侧金描边 */
.rarity-sr { border-color: #c9a227; box-shadow: inset 0 0 0 3px rgba(201, 162, 39, 0.18); }
.rarity-sr::before {
  opacity: 0.5;
  background: linear-gradient(115deg, transparent 28%, rgba(255, 224, 130, 0.92) 44%, rgba(255, 180, 60, 0.6) 52%, transparent 62%);
  background-size: 220% 220%;
  animation: sheen-sweep 3s ease-in-out infinite;
}

/* 镭射彩虹 SSR：卡面流转彩虹底 + 高光扫过 */
.rarity-ssr {
  border-color: rgba(124, 77, 255, 0.5);
  background:
    radial-gradient(120% 120% at 18% 0%, #fffdf6 0%, rgba(255, 255, 255, 0.25) 55%),
    linear-gradient(115deg, #ff8cc0, #ffd166, #7cffb2, #80d6ff, #b39dff);
  background-size: 160% 160%;
  animation: holo-back 2.8s linear infinite alternate;
}
.rarity-ssr::before {
  opacity: 0.45;
  background: linear-gradient(115deg, transparent 20%, rgba(255, 255, 255, 0.9) 40%, rgba(255, 80, 200, 0.3) 50%, transparent 70%);
  background-size: 260% 260%;
  animation: sheen-sweep 2.6s ease-in-out infinite;
}
/* SSR 卡面为固定亮彩虹底，标题/正文始终用深色，避免夜间模式变白字后看不清 */
.rarity-ssr h4,
.rarity-ssr p {
  color: #33264d;
}

.rarity-n .card-rarity { color: #6b7280; }
.rarity-r .card-rarity { color: #4a6c93; }
.rarity-sr .card-rarity { color: #a87d0f; }
.rarity-ssr .card-rarity { color: #8b5cf6; }

@keyframes sheen-sweep {
  0%, 100% { background-position: 130% 0; }
  50% { background-position: -30% 0; }
}
@keyframes holo-back {
  0% { background-position: 0% 0%; }
  100% { background-position: 100% 100%; }
}
.pick-grid {
  display: grid;
  width: max-content;
  max-width: 100%;
  justify-content: center;
  gap: 16px;
}
.card.chosen {
  outline: 3px solid #10b981;
}
.btn {
  padding: 8px 18px;
  border: none;
  border-radius: 0;
  cursor: pointer;
  align-self: flex-start;
}
.btn.primary {
  background: var(--accent);
  color: var(--on-accent);
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
  background: var(--accent-soft);
  border: 1px solid var(--border);
  border-radius: 0;
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
.quality {
  font-size: 13px;
  padding: 8px 10px;
  border-radius: 0;
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
  border-radius: 0;
  font-family: inherit;
  background: var(--bg-card);
  color: var(--text);
}
</style>