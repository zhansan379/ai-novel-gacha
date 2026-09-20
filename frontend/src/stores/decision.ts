import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '../api/client'
import type { Card, ConsistencyResult, DecisionMode, LintIssue } from '../types'

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

interface ActionResult {
  kind: 'draw' | 'pick' | 'free'
  card: Card | null
  passage: string
}

export const useDecisionStore = defineStore('decision', () => {
  // 故事状态
  const storyId = ref<string | null>(null)
  const synopsis = ref('')
  const passages = ref<string[]>([])

  // 当前决策
  const decisionNo = ref<number | null>(null)
  const cards = ref<Card[]>([])
  const mode = ref<DecisionMode>('gacha_draw')
  const revealed = ref<Card | null>(null)
  const customInstruction = ref('')

  // 流程控制
  const loading = ref(false)
  const error = ref<string | null>(null)
  const lastAction = ref<ActionResult | null>(null)
  const nextDecisionNo = ref<number | null>(null)
  const lastLint = ref<LintIssue[]>([])
  const lastConsistency = ref<ConsistencyResult | null>(null)

  /** 用灵感开一本新书（后端完成初始卡池 + 开篇）。 */
  async function create(premise: string, styleProfileId?: string) {
    const text = premise.trim()
    if (!text) return
    loading.value = true
    error.value = null
    try {
      const s = await api.createStory(text, styleProfileId)
      storyId.value = s.story_id
      synopsis.value = s.synopsis
      passages.value = [s.opening]
      decisionNo.value = s.decision_no
      cards.value = s.cards
      _resetDecisionLocalState()
    } catch (e) {
      error.value = errMsg(e)
    } finally {
      loading.value = false
    }
  }

  /** 加载已有故事（刷新/分享链接进入）。 */
  async function load(existingId: string) {
    loading.value = true
    error.value = null
    try {
      const s = await api.getStory(existingId)
      storyId.value = existingId
      synopsis.value = s.synopsis
      passages.value = s.passages
      await loadCards(existingId, s.next_decision_no)
    } catch (e) {
      error.value = errMsg(e)
    } finally {
      loading.value = false
    }
  }

  async function loadCards(sid: string, no: number) {
    const c = await api.getCards(sid, no)
    decisionNo.value = c.decision_no
    cards.value = c.cards
    _resetDecisionLocalState()
  }

  function _resetDecisionLocalState() {
    revealed.value = null
    customInstruction.value = ''
    lastAction.value = null
    nextDecisionNo.value = null
    lastLint.value = []
    lastConsistency.value = null
    error.value = null
  }

  /** 盲抽一次即完成抽取 + 生成正文，并进入"下一分歧"待命。 */
  async function draw() {
    if (!storyId.value || decisionNo.value == null) return
    loading.value = true
    error.value = null
    try {
      const res = await api.blindDraw(storyId.value, decisionNo.value)
      passages.value = [...passages.value, res.passage]
      lastAction.value = { kind: 'draw', card: res.card, passage: res.passage }
      lastLint.value = res.lint
      lastConsistency.value = res.consistency
      nextDecisionNo.value = res.next_decision_no
      cards.value = []
      decisionNo.value = null
    } catch (e) {
      error.value = errMsg(e)
    } finally {
      loading.value = false
    }
  }

  /** 采用当前选择（明选卡 / 自由输入指令），并进入"下一分歧"待命。 */
  async function apply() {
    if (!storyId.value || decisionNo.value == null) return
    if (mode.value === 'gacha_pick' && !revealed.value) {
      error.value = '请先选择一张卡'
      return
    }
    if (mode.value === 'free' && !customInstruction.value.trim()) {
      error.value = '请输入剧情指令'
      return
    }
    loading.value = true
    error.value = null
    try {
      const body = mode.value === 'free'
        ? { custom_instruction: customInstruction.value.trim() }
        : { card_id: revealed.value!.card_id }
      const res = await api.apply(storyId.value, decisionNo.value, body)
      passages.value = [...passages.value, res.passage]
      lastAction.value = { kind: mode.value === 'free' ? 'free' : 'pick', card: revealed.value, passage: res.passage }
      lastLint.value = res.lint
      lastConsistency.value = res.consistency
      nextDecisionNo.value = res.next_decision_no
      cards.value = []
      decisionNo.value = null
    } catch (e) {
      error.value = errMsg(e)
    } finally {
      loading.value = false
    }
  }

  /** 进入下一个分歧点，加载新的卡池。 */
  async function next() {
    if (!storyId.value || nextDecisionNo.value == null) return
    loading.value = true
    try {
      await loadCards(storyId.value, nextDecisionNo.value)
    } catch (e) {
      error.value = errMsg(e)
    } finally {
      loading.value = false
    }
  }

  function pickLocal(cardId: string) {
    revealed.value = cards.value.find((c) => c.card_id === cardId) ?? null
  }

  function reset() {
    storyId.value = null; synopsis.value = ''; passages.value = []
    decisionNo.value = null; cards.value = []; revealed.value = null
    customInstruction.value = ''; loading.value = false; error.value = null
    lastAction.value = null; nextDecisionNo.value = null
    lastLint.value = []; lastConsistency.value = null
  }

  return {
    storyId, synopsis, passages, decisionNo, cards, mode, revealed, customInstruction,
    loading, error, lastAction, nextDecisionNo, lastLint, lastConsistency,
    create, load, draw, apply, next, pickLocal, reset,
  }
})