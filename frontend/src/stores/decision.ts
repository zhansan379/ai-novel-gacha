import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api, consumeSSE } from '../api/client'
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
  const streamingText = ref('')

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

  /** 盲抽：服务端随机揭晓并流式生成正文。 */
  async function draw() {
    if (!storyId.value || decisionNo.value == null) return
    await _stream({ draw: true })
  }

  /** 采用当前选择（明选卡 / 自由输入指令），流式生成正文。 */
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
    const body = mode.value === 'free'
      ? { custom_instruction: customInstruction.value.trim() }
      : { card_id: revealed.value!.card_id }
    await _stream(body)
  }

  /** 调用流式端点：读 SSE 事件，逐 token 更新 streamingText，结束时落库并进入下一分歧。 */
  async function _stream(body: { draw?: boolean; card_id?: string; custom_instruction?: string }) {
    if (!storyId.value || decisionNo.value == null) return
    const no = decisionNo.value
    loading.value = true
    error.value = null
    streamingText.value = ''
    let revealedCard: Card | null = null
    try {
      const res = await api.streamDecision(storyId.value, no, body)
      if (!res.ok || !res.body) {
        let msg = `请求失败 (${res.status})`
        try {
          const j = await res.json()
          msg = j?.detail?.message ?? msg
        } catch { /* ignore */ }
        throw new Error(msg)
      }
      await consumeSSE(res, (ev) => {
        if (ev.event === 'passage_start') {
          const d = ev.data as { card?: Card }
          revealedCard = d.card ?? null
        } else if (ev.event === 'delta') {
          streamingText.value += (ev.data as { text: string }).text
        } else if (ev.event === 'passage_end') {
          const d = ev.data as {
            passage: string; lint: LintIssue[]; consistency: ConsistencyResult; next_decision_no: number
          }
          passages.value = [...passages.value, d.passage]
          lastAction.value = {
            kind: body.draw ? 'draw' : (body.card_id ? 'pick' : 'free'),
            card: revealedCard,
            passage: d.passage,
          }
          lastLint.value = d.lint ?? []
          lastConsistency.value = d.consistency ?? null
          nextDecisionNo.value = d.next_decision_no
          cards.value = []
          decisionNo.value = null
          streamingText.value = ''
        }
      })
    } catch (e) {
      error.value = errMsg(e)
    } finally {
      loading.value = false
      streamingText.value = ''
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
    streamingText.value = ''
  }

  return {
    storyId, synopsis, passages, decisionNo, cards, mode, revealed, customInstruction,
    loading, error, lastAction, nextDecisionNo, lastLint, lastConsistency, streamingText,
    create, load, draw, apply, next, pickLocal, reset,
  }
})