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
export type StoryStatus = 'active' | 'completed'

export interface Chapter {
  no: number
  title: string
  passage_from: number
  passage_to: number
  is_final: boolean
  status: 'open' | 'closed'
}
export interface ChaptersResponse {
  story_id: string
  chapters: Chapter[]
  status: StoryStatus
}
export interface StoryCreated {
  story_id: string
  synopsis: string
  opening: string
  decision_no: number
  cards: Card[]
  style_profile_id: string
}

/** POST /stories 立即返回：开书任务已受理。 */
export interface CreateTaskAccepted {
  task_id: string
  status: string
}

/** GET /stories/tasks/{id} 轮询结果：done 时带 result(StoryCreated)，error 时带 error。 */
export interface CreateTaskStatus {
  task_id: string
  status: 'pending' | 'running' | 'done' | 'error'
  stage?: string | null
  result?: StoryCreated | null
  error?: { code: string; message: string } | null
}

export interface StoryListItem {
  story_id: string
  premise: string
  synopsis: string
  next_decision_no: number
  status?: StoryStatus
}
export interface StoryList { stories: StoryListItem[] }

/** 整本故事的可移植快照（导出/导入往返格式）。 */
export interface StorySnapshot {
  story_id: string
  premise: string
  synopsis: string
  next_decision_no: number
  style_profile_id: string
  passages: unknown[]
  decisions: unknown[]
  world: unknown
  history: unknown[]
  characters: unknown[]
  foreshadows: unknown[]
  timeline: unknown[]
}

export interface StyleProfile {
  id: string
  name: string
  description: string
  temperature: number
  forbidden: string[]
}

export interface ModelsConfig {
  provider: string
  model: string
  base_url: string
  configured: boolean
  api_key_set: boolean
  mode: 'openai-compat' | 'unconfigured'
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
  next_decision_no: number | null
  story_end?: boolean
  chapter?: Chapter | null
}

export interface ApplyResponse {
  decision_no: number
  mode: 'gacha_pick' | 'free'
  direction_spec: DirectionSpec
  passage: string
  lint: LintIssue[]
  consistency: ConsistencyResult
  next_decision_no: number | null
  story_end?: boolean
  chapter?: Chapter | null
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
  timeline?: TimelineEvent[]
  chapters?: Chapter[]
  status?: StoryStatus
}

export interface TimelineEvent {
  no: number
  decision_no: number
  mode: string
  card_id?: string | null
  label?: string | null
  title?: string | null
  summary: string
}
export interface TimelineResponse { story_id: string; timeline: TimelineEvent[] }

// ---- 前置构建蓝图 ----
export interface Faction {
  name: string
  description?: string
}
export interface WorldSetting {
  rules?: string[]
  geography?: string
  power_system?: string
  /** 兼容旧版纯名字数组：每项可能是 string(旧) 或 {name, description}(新)。 */
  factions?: Array<Faction | string>
  constraints?: string[]
}
export interface HistoryEvent { era: string; event: string; impact: string }
export interface CharacterCard {
  name: string; role: string; goal?: string; inner_need?: string; flaw?: string; trait?: string
  moves?: string[]
}
export interface ForeshadowItem { id: string; text: string; origin: string; status: 'planted' | 'advanced' | 'paid_off' }
export interface RelationEdge { a: string; b: string; label?: string; note?: string }
export interface AppearanceItem { name: string; count: number; first_no?: number }
export interface Blueprint {
  story_id: string
  world: WorldSetting
  history: HistoryEvent[]
  characters: CharacterCard[]
  appearances?: AppearanceItem[]
  style?: string
  genre?: string
  foreshadows?: ForeshadowItem[]
  relations?: RelationEdge[]
  grounding?: string[]
}