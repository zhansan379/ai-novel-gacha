/**
 * 后端 API 客户端（经 Vite proxy 转发到 :8000/v1）。
 * 类型与《接口契约》一致，远期由 OpenAPI 生成替换。
 */
import type {
  ApplyResponse, Blueprint, CardsResponse, Chapter, ChaptersResponse, CreateTaskAccepted,
  CreateTaskStatus, DrawResponse, ModelsConfig, StoryList, StorySnapshot, StorySummary, StyleProfile,
  TimelineResponse,
} from '../types'

const BASE = '/v1'

export { BASE }

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let msg = `请求失败 (${res.status})`
    try {
      const j = await res.json()
      msg = j?.detail?.message ?? j?.detail ?? msg
    } catch {
      /* 保持默认 msg */
    }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

export interface SSEEvent {
  event: string
  data: unknown
}

/** 读取 SSE 流，逐个回调事件。 */
export async function consumeSSE(res: Response, onEvent: (ev: SSEEvent) => void): Promise<void> {
  if (!res.body) throw new Error('无可读流')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const frame = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      let event = 'message'
      let data = ''
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data = line.slice(5).trim()
      }
      if (!data) continue
      let parsed: unknown
      try {
        parsed = JSON.parse(data)
      } catch {
        continue
      }
      onEvent({ event, data: parsed })
    }
  }
}

/** 轮询开书任务直到终态（done/error）。任务丢失会抛错（如服务重启后 404）。 */
export async function waitForCreateTask(
  taskId: string,
  opts: { pollMs?: number; onStatus?: (s: CreateTaskStatus) => void } = {},
): Promise<CreateTaskStatus> {
  const pollMs = opts.pollMs ?? 1500
  for (;;) {
    const s: CreateTaskStatus = await api.getCreateTaskStatus(taskId)
    opts.onStatus?.(s)
    if (s.status === 'done' || s.status === 'error') return s
    await new Promise((r) => setTimeout(r, pollMs))
  }
}

export const api = {
  /** 开书：提交后台异步任务，立即返回 task_id；完成后经轮询 getCreateTaskStatus 取结果。 */
  createStory: (premise: string, styleProfileId?: string) =>
    req<CreateTaskAccepted>('/stories', {
      method: 'POST',
      body: JSON.stringify({ premise, style_profile_id: styleProfileId }),
    }),

  getCreateTaskStatus: (taskId: string) =>
    req<CreateTaskStatus>(`/stories/tasks/${taskId}`),

  getStyles: async () => {
    const res = await req<{ styles: StyleProfile[] }>('/styles')
    return res.styles
  },

  /** 文风对比：同一段素材用若干文风各自生成（真实调用 LLM）。 */
  compareStyles: (text: string, styleIds: string[]) =>
    req<{ results: Array<{ style_id: string; name: string; output: string | null; error: string | null }> }>(
      '/styles/compare',
      { method: 'POST', body: JSON.stringify({ text, style_ids: styleIds }) },
    ),

  getStory: (storyId: string) => req<StorySummary>(`/stories/${storyId}`),

  getStories: () => req<StoryList>('/stories'),

  exportStory: (storyId: string) => req<StorySnapshot>(`/stories/${storyId}/export`),

  importStory: (snapshot: object) =>
    req<{ story_id: string; premise: string; synopsis: string }>('/stories/import', {
      method: 'POST',
      body: JSON.stringify({ snapshot }),
    }),

  deleteStory: async (storyId: string) => {
    const res = await fetch(`${BASE}/stories/${storyId}`, { method: 'DELETE' })
    if (!res.ok) {
      let msg = `删除失败 (${res.status})`
      try {
        const j = await res.json()
        msg = j?.detail?.message ?? j?.detail ?? msg
      } catch {
        /* 保持默认 msg */
      }
      throw new Error(msg)
    }
  },

  getBlueprint: (storyId: string) => req<Blueprint>(`/stories/${storyId}/blueprint`),

  getTimeline: (storyId: string) => req<TimelineResponse>(`/stories/${storyId}/timeline`),

  getChapters: (storyId: string) => req<ChaptersResponse>(`/stories/${storyId}/chapters`),

  renameChapter: (storyId: string, chapterNo: number, title: string) =>
    req<Chapter>(`/stories/${storyId}/chapters/${chapterNo}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),

  undoLast: (storyId: string) =>
    req<{ undo: boolean; next_decision_no: number }>(`/stories/${storyId}/undo`, {
      method: 'POST', body: '{}',
    }),

  getCards: (storyId: string, decisionNo: number) =>
    req<CardsResponse>(`/stories/${storyId}/decisions/${decisionNo}/cards`),

  blindDraw: (storyId: string, decisionNo: number) =>
    req<DrawResponse>(`/stories/${storyId}/decisions/${decisionNo}/gacha`, { method: 'POST', body: '{}' }),

  apply: (storyId: string, decisionNo: number, body: { card_id?: string; custom_instruction?: string }) =>
    req<ApplyResponse>(`/stories/${storyId}/decisions/${decisionNo}/apply`, { method: 'POST', body: JSON.stringify(body) }),

  /** 发起正文流式生成（SSE），返回 Response 供调用方读取事件流。 */
  streamDecision: (storyId: string, decisionNo: number,
    body: { draw?: boolean; card_id?: string; custom_instruction?: string }) =>
    fetch(`${BASE}/stories/${storyId}/decisions/${decisionNo}/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  getModelsConfig: () => req<ModelsConfig>('/models/config'),

  saveModelsConfig: (body: { provider: string; model: string; base_url?: string; api_key?: string }) =>
    req<ModelsConfig>('/models/config', { method: 'POST', body: JSON.stringify(body) }),

  clearModelsConfig: () => req<ModelsConfig>('/models/config/clear', { method: 'POST' }),
}