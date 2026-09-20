import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { Card, CardPool, DecisionMode } from '../types'

// 占位卡池：接入 LLM 前用于驱动决策 UI；未来由 POST /decisions/{no}/cards 提供。
const MOCK_POOL: CardPool = {
  decision_no: 0,
  pool_version: 1,
  cards: [
    {
      card_id: 'm-1', title: '夜雨敲门', rarity: 'R', weight: 40, label: 'EVENT',
      content: '雨夜有人敲响旅店的门，指名要找主角。是故人重逢，还是暗处的追兵？',
    },
    {
      card_id: 'm-2', title: '破落画师', rarity: 'SR', weight: 25, label: 'MEETING',
      content: '街角的落魄画师，总在画同一座不存在的城。他认出主角身上的一件旧物。',
      risk_balance: { tension: 6, suggested_turn: '画师揭晓一件关于主角过去的线索' },
    },
    {
      card_id: 'm-3', title: '一封密信', rarity: 'N', weight: 60, label: 'FORESHADOW',
      content: '主角收到一封没有落款、笔迹却异常熟悉的信，落款日期是明天。',
    },
    {
      card_id: 'm-4', title: '天光乍亮', rarity: 'R', weight: 35, label: 'SCENE',
      content: '清晨的城门口出现异象。人群骚动，守城的兵士在盘查每一个过客。',
    },
  ],
}

export const useDecisionStore = defineStore('decision', () => {
  const cardPool = ref<CardPool | null>(null)
  const mode = ref<DecisionMode>('gacha_draw')
  const revealed = ref<Card | null>(null)
  const customInstruction = ref('')
  const applied = ref(false)

  const activePool = computed(() => cardPool.value)
  const hasDecision = computed(() => cardPool.value !== null)

  /** 触发一个新分歧点（后端返回卡池时调用并传入 pool）。 */
  function openNewDecision(pool: CardPool = MOCK_POOL) {
    cardPool.value = {
      ...pool,
      decision_no: (cardPool.value?.decision_no ?? 0) + 1,
    }
    revealed.value = null
    customInstruction.value = ''
    applied.value = false
  }

  /** 盲抽：按 weight 加权随机揭晓一张。 */
  function drawCard() {
    const cards = cardPool.value?.cards
    if (!cards || cards.length === 0) return
    const total = cards.reduce((sum, c) => sum + c.weight, 0)
    let r = Math.random() * total
    for (const card of cards) {
      r -= card.weight
      if (r <= 0) {
        revealed.value = card
        return
      }
    }
    revealed.value = cards[cards.length - 1]!
  }

  /** 明选：选定一张卡。 */
  function pickCard(cardId: string) {
    revealed.value = cardPool.value?.cards.find((c) => c.card_id === cardId) ?? null
  }

  /** 确认当前决策（盲抽揭晓卡 / 明选卡 / 自由输入指令）。 */
  function confirm() {
    applied.value = true
  }

  return {
    cardPool, mode, revealed, customInstruction, applied,
    activePool, hasDecision,
    openNewDecision, drawCard, pickCard, confirm,
  }
})