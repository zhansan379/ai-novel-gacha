import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api, consumeSSE, waitForCreateTask } from '../api/client'
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
  const title = ref('')
  const synopsis = ref('')
  const passages = ref<string[]>([])

  // 当前决策
  const decisionNo = ref<number | null>(null)
  const cards = ref<Card[]>([])
  const mode = ref<DecisionMode>('gacha_draw')
  const revealed = ref<Card | null>(null)
  const customInstruction = ref('')

  // 抽卡浮层开关：跨页面/组件共享（侧栏"抽卡"与正文底部按钮共用）
  const drawOpen = ref(false)
  function toggleDraw() {
    drawOpen.value = !drawOpen.value
  }
  function closeDraw() {
    drawOpen.value = false
  }

  // 收藏/标记当前页（按 story_id 持久化到 localStorage）
  const BOOKMARK_KEY = 'choice_novel:bookmarks'
  const bookmarked = ref(false)
  function _loadBookmarks(): string[] {
    try { return JSON.parse(localStorage.getItem(BOOKMARK_KEY) || '[]') as string[] }
    catch { return [] }
  }
  function syncBookmark() {
    bookmarked.value = !!storyId.value && _loadBookmarks().includes(storyId.value)
  }
  /** 当前收藏的所有 story_id（保持收藏先后顺序）。 */
  function getBookmarkedIds(): string[] {
    return _loadBookmarks()
  }
  /** 新增/移除某本书的收藏，并同步当前阅读页书签态。 */
  function setBookmarked(id: string, on: boolean) {
    const arr = _loadBookmarks()
    const has = arr.includes(id)
    if (on && !has) arr.push(id)
    else if (!on && has) arr.splice(arr.indexOf(id), 1)
    localStorage.setItem(BOOKMARK_KEY, JSON.stringify(arr))
    if (id === storyId.value) bookmarked.value = on
  }
  function toggleBookmark() {
    if (!storyId.value) return
    setBookmarked(storyId.value, !bookmarked.value)
  }

  // 流程控制
const loading = ref(false)
const error = ref<string | null>(null)
// 下一拍卡池加载中（独立的轻量指示；不再复用正文主"抽卡中…"状态）
const cardsLoading = ref(false)
  const lastAction = ref<ActionResult | null>(null)
  const nextDecisionNo = ref<number | null>(null)
  const lastLint = ref<LintIssue[]>([])
  const lastConsistency = ref<ConsistencyResult | null>(null)
  const streamingText = ref('')

  // 异步开书：独立于 loading（避免卡住抽卡/撤销按钮），进程内轮询真实阶段，刷新可从 localStorage 恢复
  const PENDING_CREATE_KEY = 'choice_novel:pending_create'
  const creating = ref(false)
  const creatingTaskId = ref<string | null>(null)
  const createStage = ref('')
  function _savePendingCreate(taskId: string, premise: string) {
    try { localStorage.setItem(PENDING_CREATE_KEY, JSON.stringify({ task_id: taskId, premise })) } catch { /* ignore */ }
  }
  function _clearPendingCreate() {
    try { localStorage.removeItem(PENDING_CREATE_KEY) } catch { /* ignore */ }
  }

  /** 用灵感开一本新书：提交后台任务 → 持久化 task_id → 轮询真实进度 → done 后写入开篇与首轮卡池。 */
  async function create(premise: string, styleProfileId?: string) {
    const text = premise.trim()
    if (!text) return
    creating.value = true
    creatingTaskId.value = null
    createStage.value = ''
    title.value = text
    error.value = null
    try {
      const task = await api.createStory(text, styleProfileId)
      creatingTaskId.value = task.task_id
      _savePendingCreate(task.task_id, text)
      const st = await waitForCreateTask(task.task_id, {
        onStatus: (s) => { createStage.value = s.stage ?? '' },
      })
      if (st.status === 'error') {
        throw new Error(st.error?.message ?? '开书失败')
      }
      _applyCreateResult(st.result!)
      _clearPendingCreate()
    } catch (e) {
      // 404（服务重启丢失）等：清掉遗留任务记录，避免下次刷新再空轮询
      _clearPendingCreate()
      error.value = errMsg(e)
    } finally {
      creating.value = false
      creatingTaskId.value = null
      createStage.value = ''
    }
  }

  function _applyCreateResult(s: { story_id: string; synopsis: string; opening: string; decision_no: number; cards: Card[]; style_profile_id?: string }) {
    storyId.value = s.story_id
    title.value = title.value || s.story_id
    synopsis.value = s.synopsis
    passages.value = [s.opening]
    decisionNo.value = s.decision_no
    cards.value = s.cards
    syncBookmark()
    _resetDecisionLocalState()
  }

  /** 刷新/重进首页时恢复仍在进行中的开书任务（localStorage 里的 task_id）。 */
  async function resumePendingCreate() {
    if (creating.value) return
    let rec: { task_id?: string; premise?: string } | null = null
    try { rec = JSON.parse(localStorage.getItem(PENDING_CREATE_KEY) || 'null') } catch { rec = null }
    const taskId = rec?.task_id
    if (!taskId || !rec) return
    creating.value = true
    creatingTaskId.value = taskId
    createStage.value = ''
    if (rec.premise) title.value = rec.premise
    error.value = null
    try {
      const st = await waitForCreateTask(taskId, {
        onStatus: (s) => { createStage.value = s.stage ?? '' },
      })
      if (st.status === 'error') {
        throw new Error(st.error?.message ?? '开书失败')
      }
      _applyCreateResult(st.result!)
      _clearPendingCreate()
    } catch (e) {
      _clearPendingCreate()
      error.value = errMsg(e)
    } finally {
      creating.value = false
      creatingTaskId.value = null
      createStage.value = ''
    }
  }

  /** 加载已有故事（刷新/分享链接进入）。 */
  async function load(existingId: string) {
    loading.value = true
    error.value = null
    try {
      const s = await api.getStory(existingId)
      storyId.value = existingId
      title.value = s.premise
      synopsis.value = s.synopsis
      passages.value = s.passages
      syncBookmark()
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

  /** 采用当前选择（已点卡 / 已输入指令），流式生成正文。 */
  async function apply() {
    if (!storyId.value || decisionNo.value == null) return
    const text = customInstruction.value.trim()
    if (text) {
      await _stream({ custom_instruction: text })   // 有自由输入 → 按输入推进
      return
    }
    if (!revealed.value) {
      error.value = '请先选择一张卡'
      return
    }
    await _stream({ card_id: revealed.value!.card_id })
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
          streamingText.value = ''
          // 正文已落地，立刻解锁抽卡/推进（下一卡池由 cardsLoading 单独承接）
          loading.value = false
        } else if (ev.event === 'passage_error') {
          // 生成收尾失败（如下一分歧卡不合规）：展示错误，该步已在服务端回滚，可重试
          streamingText.value = ''
          throw new Error((ev.data as { message: string }).message ?? '生成失败，该步已回滚')
        }
      })
      // 自动进入下一分歧：直接加载新卡池（GET /cards 惰性生成），
      // 期间以独立的 cardsLoading 提示，不占用正文主 loading
      const nxt = nextDecisionNo.value
      if (nxt != null && storyId.value) {
        const keep = {
          lastAction: lastAction.value, lastLint: lastLint.value,
          lastConsistency: lastConsistency.value,
        }
        cardsLoading.value = true
        try {
          await loadCards(storyId.value, nxt)
          // loadCards 会清空结果态，这里把"上一分歧结果"恢复，用于结果横幅
          lastAction.value = keep.lastAction
          lastLint.value = keep.lastLint
          lastConsistency.value = keep.lastConsistency
        } finally {
          cardsLoading.value = false
        }
      }
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
    cardsLoading.value = true
    try {
      await loadCards(storyId.value, nextDecisionNo.value)
    } catch (e) {
      error.value = errMsg(e)
    } finally {
      loading.value = false
      cardsLoading.value = false
    }
  }

  function pickLocal(cardId: string) {
    revealed.value = cards.value.find((c) => c.card_id === cardId) ?? null
  }

  /** 明选：点卡即提交并生成（不再需要先选再点"采用"）。 */
  async function applyCard(cardId: string) {
    pickLocal(cardId)
    await apply()
  }

  /** 撤销上一步：回退最后一段正文/时间线，还原伏笔与角色，回到上一分歧重新选择。 */
  async function undo() {
    if (!storyId.value) return
    loading.value = true
    error.value = null
    try {
      await api.undoLast(storyId.value)
      await load(storyId.value)        // 同步正文/下一分歧卡池
      lastAction.value = null          // 清掉已撤销那步的结果横幅
      lastLint.value = []
      lastConsistency.value = null
    } catch (e) {
      error.value = errMsg(e)
    } finally {
      loading.value = false
    }
  }

  function reset() {
    storyId.value = null; title.value = ''; synopsis.value = ''; passages.value = []
    bookmarked.value = false
    decisionNo.value = null; cards.value = []; revealed.value = null
    customInstruction.value = ''; loading.value = false; error.value = null
    cardsLoading.value = false
    lastAction.value = null; nextDecisionNo.value = null
    lastLint.value = []; lastConsistency.value = null
    streamingText.value = ''
    _clearPendingCreate(); creating.value = false; creatingTaskId.value = null; createStage.value = ''
  }

  return {
    storyId, title, synopsis, passages, decisionNo, cards, mode, revealed, customInstruction,
    loading, cardsLoading, error, lastAction, nextDecisionNo, lastLint, lastConsistency, streamingText,
    creating, creatingTaskId, createStage,
    drawOpen, toggleDraw, closeDraw,
    bookmarked, toggleBookmark, getBookmarkedIds, setBookmarked,
    create, resumePendingCreate, load, draw, apply, applyCard, undo, next, pickLocal, reset,
  }
})