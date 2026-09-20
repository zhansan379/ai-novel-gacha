/**
 * 后端 API 客户端（经 Vite proxy 转发到 :8000/v1）。
 * 类型与《接口契约》一致，远期由 OpenAPI 生成替换。
 */
import type {
  ApplyResponse, Blueprint, CardsResponse, DrawResponse, StoryCreated, StorySummary, StyleProfile,
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

export const api = {
  createStory: (premise: string, styleProfileId?: string) =>
    req<StoryCreated>('/stories', {
      method: 'POST',
      body: JSON.stringify({ premise, style_profile_id: styleProfileId }),
    }),

  getStyles: async () => {
    const res = await req<{ styles: StyleProfile[] }>('/styles')
    return res.styles
  },

  getStory: (storyId: string) => req<StorySummary>(`/stories/${storyId}`),

  getBlueprint: (storyId: string) => req<Blueprint>(`/stories/${storyId}/blueprint`),

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
}