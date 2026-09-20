# AI 小说生成系统 设计文档

> 文档版本：v1.0　|　日期：2026-09-20
> 关联需求：`AI 小说生成系统-需求文档.md`
> 设计依据：基于 11 个开源小说生成项目的工程经验（见《小说生成开源项目调研报告.md》）

---

## 1. 设计目标
- 支撑「抽卡 / 自由输入 → 决定剧情走向 → 生成连贯长篇」的核心玩法。
- 复用开源生态最成熟的工程范式，不做重复造轮子：
  - **多级上下文注入 + 自动压缩**（参考 OpenFic / AI-Novel-Writer / denova / kimi-writer）
  - **状态卡（结构化 Story State）**（参考 oh-story-claudecode / denova / NovelClaw）
  - **多 Agent 生产链**（参考 oh-story / denova / neuro-book / AI-Novel-Writing-Assistant）
  - **去 AI 味规则 lint**（参考 neuro-book llmlint / storyforge anti-ai-adapter）
  - **同一模型接入 + BYOK**（参考全系项目均走 OpenAI 兼容协议）
  - **本地优先 + 可选云端**（参考 AI-Novel-Writer / storyforge）

---

## 2. 总体架构

```
 ┌────────────────────────────────────────────────────────────┐
 │                         前端 Web (Vue 3 + Vite + Pinia)    │
 │  项目列表 │ 故事读写页(流式) │ 决策页(抽卡/输入) │ 设定/图鉴 │
 └──────────────▲─────────────────────────────────────────────┘
                │ HTTP (REST) + SSE (流式) / WebSocket (决策实时)
 ┌──────────────┴─────────────────────────────────────────────┐
 │                    API 层 (FastAPI)                         │
 │        /projects /stories /chapters /decisions /cards       │
 │        /gacha /generate/stream /undo /branch /revision      │
 └──────────────▲─────────────────────────────────────────────┘
                │
 ┌──────────────┴─────────────────────────────────────────────┐
 │                 AI 编排层 (LangGraph)                        │
 │                                                            │
 │  Orchestrator                                                │
 │   ├── DirectionGenerator      → 分歧点生成候选卡池(3-5张)     │
 │   ├── IntentRouter            → 「自由输入」意图理解           │
 │   ├── WriterAgent             → 生成下一段正文(流式)          │
 │   ├── ConsistencyChecker      → 一致性/伏笔/时间线校验        │
 │   ├── FixerAgent              → 定向修复                     │
 │   ├── DeslopLint              → 去 AI 味规则扫描             │
 │   └── Summarizer              → 章节摘要/压缩                 │
 └──────────────┬─────────────────────────────────────────────┘
                │
 ┌──────────────▼───────────┐  ┌──────────────────────────────┐
 │       状态库 StateStore  │  │  向量库 VectorStore (可选)     │
 │  Story │ Character │     │  │  LanceDB / Qdrant / SQLite FTS│
 │  Timeline │ Foreshadow │  │  │  关键设定/伏笔检索 (RAG)      │
 │  CardPool │ DecisionLog │  │  └──────────────────────────────┘
 │  (SQLite + 文件系统)     │       ▲
 └──────────────▲───────────┘       │
                │                  RAG 检索
 ┌──────────────┴───────────┐  ┌──────────────────────────────┐
 │    多模型接入层 LLM Gateway│  │       存储层 Store            │
 │  OpenAI-compatible:       │  │  SQLite(状态) + 正文文件(本地)│
 │  DeepSeek/OpenAI/Ollama/…│  │  + 对象存储(云端模式可选)      │
 │  按任务路由 + token 预算   │  └──────────────────────────────┘
 └──────────────────────────┘
```

**分层目的**：决策引擎与正文生成解耦（决策只产出"方向"这个变量，生成器消费它），保证「抽卡」改动不影响底层生成与存储；LLM 用 Gateway 统一屏蔽服务商差异；状态库与正文分离，兼顾一致性与可读。

---

## 3. 技术选型（含选型理由）

| 组件 | 选型 | 参考开源项目 | 理由 |
|------|------|--------------|------|
| 后端框架 | Python 3.12 + FastAPI | OpenFic / NovelClaw | Async 天然适合流式与 SSE；生态围绕 LLM 成熟 |
| AI 编排 | LangGraph / LangChain | OpenFic / AI-Novel-Writing-Assistant | 原生支持图式生产链、checkpoint、ReAct、子 Agent 并行 |
| 前端 | Vue 3 + Vite + Pinia + TipTap（@tiptap/vue-3，或换 Milkdown） | neuro-book（同领域 Vue 先例）/ storyforge | Vue 生态成熟，Pinia 状态、组合式 API、TipTap 有官方 Vue 绑定，易做流式/抽卡动画；**neuro-book 已用 Vue3+Nuxt+TipTap/Milkdown 实证小说编辑场景** |
| 桌面（可选） | Electron 或 Tauri | AI-Novel-Writer | 本地优先场景可选 |
| 状态库 | SQLite（Prisma/SQLModel）+ 文件系统 | denova / oh-story | 轻量、无运维、事务可靠；正文用文件便于人类可读 |
| 向量/RAG | LanceDB（IVF-HNSW + FTS 混合），可选 Qdrant | OpenFic / AI-Novel-Writer | 本地嵌入免云、混合检索兼顾精确召回；提供 FTS 退化 |
| 模型接入 | OpenAI 兼容协议统一抽象 + BYOK | 全系 | 兼容 DeepSeek/OpenAI/Ollama/Groq/OpenRouter 等，成本分任务路由 |
| 上下文 | 自研 L0/L1/L2 + 自动压缩 + 状态卡 | AI-Novel-Writer / OpenFic | 分层注入 + token 预算，见 §7 |
| 去 AI 味 | 规则库 lint（脚本级）+ LLM 语境复核 | neuro-book llmlint / storyforge | 秒级全稿扫描 + 语境判定，避免只靠模型主观 |
| 部署 | Docker Compose 本地 + 可选云 | storyforge / OpenFic | 一键起，BYOK |

---

## 4. 模块划分与职责

| 模块 | 职责 | 对应需求 |
|------|------|----------|
| `frontend` | UI、流式渲染、抽卡动画、决策交互、分支视图 | FR-11 |
| `api` | REST + SSE/WS 端点、鉴权、请求校验（Zod/Pydantic） | 全部 |
| `orchestrator` | 生产链状态机、Agent 调度、暂停/恢复/检查点 | FR-2/FR-9 |
| `direction-generator` | 分歧点候选方向（卡池）生成 | FR-3/FR-4 |
| `gacha-engine` | 抽卡（盲抽/明选、稀有度、权重、揭晓演出数据） | FR-4 |
| `intent-router` | 自由输入 → 意图/命令解析与回填 | FR-5 |
| `writer-agent` | 正文生成（绘图/流式） | FR-2 |
| `consistency-checker` | 状态卡 diff、吃书检测、伏笔回收、时间线校验 | FR-6 |
| `fixer-agent` | 审稿发现问题的定向修复 | FR-12 |
| `deslop` | 去 AI 味规则扫描 + 修复建议 | FR-7 |
| `summarizer` | 章节摘要、自动压缩 | FR-8 |
| `state-store` | Story/Character/Outline/Decision 持久化 | FR-6/FR-9 |
| `vector-store` | 设定与伏笔检索（RAG） | FR-8 |
| `llm-gateway` | 多服务商适配、任务路由、温度/token 预算、用量统计 | FR-10 |

---

## 5. 核心流程设计

### 5.1 故事初始化流程（FR-1）
```
灵感一句话 → [DirectionGenerator] 生成 3 套 整本方向+标题
  → 用户选一套（或重roll）
  → [DirectionGenerator] 生成 世界观设定 + 初始角色(主角/配角) + 主线一句话
  → 写入 state-store(Story/Character/Outline) + 生成初始 CardPool
  → 进入正文生成
```

### 5.2 正文生成流程（无决策的推进，FR-2）
```
编排循环：
(curState S, 当前章) → [WriterAgent] 生成下一段正文(流式输出给前端)
  → [ConsistencyChecker] 对产出做状态 diff → [DeslopLint] 去 AI 味扫描
  → 存在阻断问题 → [FixerAgent] 修复 或 要求重写（≤3 次）
  → 更新 S（角色状态/伏笔/时间线/正文）
  → 满足章节长度/剧情收敛 → 结束本章 → [Summarizer] 生成章摘要
```

### 5.3 决策流程（核心，FR-3/4/5）—— 时序
```
① 检测到「分歧点 D」出现在正文末尾（依据剧情张力/推进信号或周期）
② [DirectionGenerator] 输入 (S, D, 文风) → 产出 卡池 Cards=3~5 张
      每张卡 = {id, title, 卡面文案, 后果标签[机遇/危机/角色/转折/伏笔],
               稀有度(N/R/SR/SSR), 权重, 方向描述 direction_spec}
③ 前端进入「决策页」：
     模式A 盲抽：用户点抽 → gacha-engine 按权重 + 稀有度概率 roll 出一张 → 揭晓演出
     模式B 明选：同时展示卡片，用户点选一张
     模式C 自由输入：用户输入指令 → [IntentRouter] 意图理解 → 可能回填/改写某张卡后采用
④ 采用方向 dir = 抽到的卡(spec) 或 用户指令 或 改写后的卡
⑤ [WriterAgent] 以 (S, D, dir) 生成下一段正文 → 走 5.2 的一致性/去AI味校验
⑥ [DecisionLog] 记录本次决策(卡id/模式/方向dir/时间/分支标记)——供回溯与分支使用
⑦ S ← S' ，继续正文推进
```

### 5.4 抽卡引擎设计（FR-4）
- **卡池生成 Prompt**：给模型「当前故事状态摘要 + 上一段正文 + 文风 + 允许卡类型」，要求输出 JSON 数组（强 schema，多卡尝试冷却）。
- **权重模型**：稀有度基础权重（N:70 / R:25 / SR:5 / SSR:1 之类，可配）；可叠加角色倾向修正（P2 收集角色卡后按性格权重打折）。
- **盲抽随机性**：真正随机数（服务端，防刷），ML 不介入抽取，只在"生成卡"时介入。
- **风险评估（稀缺卡）**：SSR 卡生成时强制要求 `risk_balance` 字段（张力 + 建议的后续转折），降低"抽到神卡但剧情断线"。
- **兜底（自然接续）**：若抽到的卡与后续写出的正文产生冲突，由 ConsistencyChecker + FixerAgent 自动 reconcile，并在 UI 用一个轻提示告知"剧情已自然接续"。

### 5.5 自由输入意图路由（FR-5）
意图分类（IntentRouter）：
| 意图 | 示例输入 | 处理 |
|------|----------|------|
| `add_event` | "让主角发现一张藏宝图" | 注入事件 → 生成对应场景 |
| `add_character` | "出现一个会算命的猫" | 建角色卡 + 出场场景 |
| `change_scene` | "切到城市夜景的街角" | 场景/环境覆盖 |
| `add_setting` | "这个世界有禁魔湖" | 写世界观 + 伏笔可选 |
| `add_character_trait` | "让女主更毒舌" | 更新 CharacterState |
| `set_endpoint` | "我要走向悲剧结局" | 改主线/收束方向 |
| `ambiguous/off_topic` | 无法分类 | 返回候选卡风格的澄清选项，允许强行走 |

统一输出：`direction_spec`（与抽卡卡片的相比更结构化指令），给 WriterAgent 消费。

---

## 6. 数据模型（核心表）

```
Project(id, user, title, created_at, version)
 ├─ Story(id, project_id, premise, genre, synopsis, style_profile_id, status)
 ├─ Outline(id, story_id, node_type[vol/act/chapter], title, order, goal)
 ├─ Chapter(id, story_id, outline_id, no, title, summary, word_count)
 ├─ Passage(id, chapter_id, seq, content, decision_id?, status[generated/final])
 ├─ Branch(id, story_id, decision_id, name, created_at)   -- 回退后新分支
 ├─ Character(id, story_id, name, role, traits, state(json), image?, arc)
 ├─ CardPool(id, story_id, decision_id, cards(json[]))     -- 卡池快照
 ├─ Decision(id, story_id, passage_id, decision_no, mode[gacha_pick/gacha_draw/free],
 │           card_id?, direction_spec(json), result_summary, created_at)
 ├─ Foreshadow(id, story_id, desc, planted_at, status[planted/advanced/paid_off],
 │           resolved_passage_id?)
 ├─ TimelineEvent(id, story_id, event, day?, order_tick, source)
 ├─ WorldState(id, story_id, state(json), revision)        -- 事件溯源 + 版本
 ├─ StyleProfile(id, name, system_prompt_ref, anti_ai_rules, temperature)
 └─ UsageLog(id, project_id, task, model, in_tokens, out_tokens, cost_usd, at)
```

要点：
- **Story State 采用"导入/追加"式**：每次生成把产生的新事实/变更写入 WorldState/CharacterState，并保留 revision 以便回退后重建。
- **DecisionLog + Passage 关联**：实现 FR-9 的分支/回溯——从某个 decision 起派生新分支，其后段落副本化。
- **CardPool 快照**：存决策时的完整卡组，便于"图鉴"收集与复现。

---

## 7. 上下文与记忆管理（FR-8）

采用**三级上下文 + 状态卡 + 自动压缩**（综合开源最佳实践）：

- **L0 常驻（~500–1000 token）**：项目/故事总览：书名、类型、当前主线一句话、核心角色一句话列表、当前章节号。
- **L1 编辑器/正文感知（~1000–3000 token）**：当前章节已生成正文（为 WriterAgent 复制文风与上下文）；决策页时则替换为"上一段正文 + 当前分歧点描述"。
- **L2 按需拉取（Tool/RAG）**：WriterAgent 通过工具按需读：当前章 Outline、相关角色完整 State、相关伏笔、关键设定（经 VectorStore 或按 id 精确取）。
- **状态卡（结构化 S）**：维护一份"当前世界/角色/伏笔/时间线"的紧凑 JSON 状态卡（参考 oh-story 上限 12KB、不进正文 prompt），每次生成后由 ConsistencyChecker 回写。
- **自动压缩**：当累计上下文接近窗口上限（如 85–90%）时，触发 Summarizer 把"最早章节"压成摘要（参考 kimi-writer 阈值/OpenFic AUTO_TRIGGER_RATIO）。
- **RAG 检索用例**：跨很长篇章后，WriterAgent 需要"真正早先的某个设定/伏笔"时用文本相似检索召回（LanceDB 混合索引），并在 prompt 中标注来源。

---

## 8. 去 AI 味模块（FR-7，参考 llmlint / anti-ai-adapter）
- **规则库**：内置若干类规则——
  - 填充词/口头禅、机械过渡（"然而/与此同时/值得一提的是"）、公式化设问、二元对比、空泛总结、呆板句式重复、过度解释内心的"AI 腔"。
- **两级扫描**：静态规则秒级全稿扫描（命中即分级：阻断级/建议级）+ 少量 LLM 语境复核（判断该处是否真有 AI 味，避免误伤）。
- **输出**：定位 + 原因 + 替换建议（可供 FixerAgent 或用户确认采纳）。
- **文风预设**：StyleProfile（如"金庸武侠/都市爽文/沉稳克制冷叙事"）注入 system prompt，控制词汇、对话风格、叙事距离（参考 storyforge writing-styles）。

---

## 9. API 与流式设计（摘要）
- 原则：REST（事务型，同步）+ SSE（正文流式生成）。
- 关键端点：
  - `POST /stories`（创建/初始化）
  - `POST /stories/{id}/generate/stream`（正文流式，SSE，携带可选 direction）
  - `POST /stories/{id}/decisions/{no}/cards`（生成卡池）→ `POST .../decisions/{no}/apply`（采用卡/输入）
  - `GET /stories/{id}/state`（状态卡视图：角色/伏笔/时间线）
  - `POST /stories/{id}/decisions/{no}/undo|branch`（回退/建分支）
  - `POST /stories/{id}/passages/{id}/revision`（审稿-修复）
  - `GET /projects/{id}/usage`（token 用量）
- 错误/降级：模型限流 → 自动缓存重试并降级到低档模型；偶发失败返回"可恢复候选"（正文存草稿）。

---

## 10. 部署与运行
- **本地（默认）**：Docker Compose 一键起（API + 前端 + SQLite 挂卷），或源码 `uv` + `npm dev`；用户界面填 API Key（BYOK）。
- **远程模式（可选）**：挂对象存储存正文；把 VectorStore 换成托管 Qdrant；多项目共享。
- **桌面版（可选）**：Electron/Tauri 包装前端，主进程内跑 SQLite，参考 AI-Novel-Writer 的本地优先方案。

---

## 11. 演进路线（对应需求优先级）
- **MVP（P0）**：初始化 + 正文流式 + 分歧点 + 抽卡(盲抽/明选) + 自由输入 + 基础一致性 + 存档/回退/分支 + 决策页 UI + SQLite。
- **V1.1（P1）**：去 AI 味 lint、长上下文（L2+RAG）、自动压缩、审稿-修复、多模型 BYOK + token 看板。
- **V2（P2）**：卡牌图鉴收集、角色属性影响抽卡权重、分支树可视化、结局统计、可选多人在线。

---

## 12. 风险与对策
| 风险 | 对策 |
|------|------|
| 抽到高戏剧卡导致剧情断线 | SSR 卡强制 risk_balance + FixerAgent reconcile + UI 轻提示 |
| 长文上下文膨胀 / 成本高 | L0/L1/L2 分层 + 自动压缩 + 按任务路由模型 + token 预算告警 |
| 一致性问题（吃书/伏笔不回收） | 结构化状态卡每次 diff + ConsistencyChecker + 来源明确 |
| 卡池生成跑题或太随机 | 强 schema 约束 + 与当前状态强相关 prompt + 卡池重roll |
| 模型服务商故障 | LLM Gateway 多提供商降级 + 本地模型 fallback |
| 依赖大型框架导致部署重（参考 NovelClaw 教训） | 向量库默认 LanceDB/FTS 本地化，避免硬依赖 chromadb/langchain 全家桶 |