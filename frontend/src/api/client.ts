/**
 * 后端 API 客户端（经 Vite proxy 转发到 :8000/v1）。
 * 类型与《接口契约》一致，远期由 OpenAPI 生成替换。
 */
import type {
  ApplyResponse, Blueprint, CardsResponse, DrawResponse, StoryCreated, StorySummary,
} from '../types'

const BASE = '/v1'

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

export const api = {
  createStory: (premise: string) =>
    req<StoryCreated>('/stories', { method: 'POST', body: JSON.stringify({ premise }) }),

  getStory: (storyId: string) => req<StorySummary>(`/stories/${storyId}`),

  getBlueprint: (storyId: string) => req<Blueprint>(`/stories/${storyId}/blueprint`),

  getCards: (storyId: string, decisionNo: number) =>
    req<CardsResponse>(`/stories/${storyId}/decisions/${decisionNo}/cards`),

  blindDraw: (storyId: string, decisionNo: number) =>
    req<DrawResponse>(`/stories/${storyId}/decisions/${decisionNo}/gacha`, { method: 'POST', body: '{}' }),

  apply: (storyId: string, decisionNo: number, body: { card_id?: string; custom_instruction?: string }) =>
    req<ApplyResponse>(`/stories/${storyId}/decisions/${decisionNo}/apply`, { method: 'POST', body: JSON.stringify(body) }),
}