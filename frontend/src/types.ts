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