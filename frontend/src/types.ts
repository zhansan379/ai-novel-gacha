/**
 * 客户端领域类型（与《接口契约》字段/取值一致）。
 * 远期接入后端后由 OpenAPI 自动生成替换，暂手写以保证前后端解耦。
 */
export type Rarity = 'N' | 'R' | 'SR' | 'SSR'
export type CardLabel = 'EVENT' | 'ACTION' | 'SCENE' | 'MEETING' | 'FORESHADOW'

export interface RiskBalance {
  tension: number // 1~10
  suggested_turn: string
}

export interface Card {
  card_id: string
  title: string
  content: string
  label: CardLabel
  rarity: Rarity
  weight: number // 1~100
  risk_balance?: RiskBalance
}

export interface CardPool {
  decision_no: number
  pool_version: number
  cards: Card[]
}

export type DecisionMode = 'gacha_draw' | 'gacha_pick' | 'free'

export interface DirectionSpec {
  kind: 'EVENT' | 'ACTION' | 'SCENE' | 'MEETING' | 'FORESHADOW' | 'CUSTOM'
  summary: string
  target_character_id?: string
  scene?: string
  constraints?: string[]
  risk_flag?: boolean
}

// ---- 后端 API 响应（与《接口契约》一致；远期 OpenAPI 生成替换）----
export interface StoryCreated {
  story_id: string
  synopsis: string
  opening: string
  decision_no: number
  cards: Card[]
}

export interface CardsResponse {
  decision_no: number
  pool_version: number
  cards: Card[]
}

export interface DrawResponse {
  decision_no: number
  mode: 'gacha_draw'
  card: Card
  direction_spec: DirectionSpec
  passage: string
  lint: LintIssue[]
  consistency: ConsistencyResult
  next_decision_no: number
}

export interface ApplyResponse {
  decision_no: number
  mode: 'gacha_pick' | 'free'
  direction_spec: DirectionSpec
  passage: string
  lint: LintIssue[]
  consistency: ConsistencyResult
  next_decision_no: number
}

export interface LintIssue {
  rule: string
  severity: 'block' | 'warn'
  fragment: string
  reason: string
  suggestion: string
}

export interface ConsistencyIssue {
  type: string
  severity: string
  fragment?: string
  reason: string
}

export interface ConsistencyResult {
  passed: boolean
  issues: ConsistencyIssue[]
}

export interface StorySummary {
  story_id: string
  premise: string
  synopsis: string
  passages: string[]
  next_decision_no: number
}