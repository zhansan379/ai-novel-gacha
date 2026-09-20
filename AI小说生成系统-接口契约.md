# AI 小说生成系统　接口契约（API Specification）

> 版本：v1.0　|　日期：2026-09-20
> 关联：`AI 小说生成系统-设计文档.md` §9、`AI 小说生成系统-需求文档.md`
> 说明：本文档是**前后端并行开发契约**。所有字段名、类型、是否必填、取值范围、错误码以本文为准。正文流式生成统一走 SSE。

---

## 0. 通用约定

- **协议**：HTTP/1.1 over TLS（本地 dev 可降级 http）；`Content-Type` 请求一律 `application/json`（流式事件为 `text/event-stream`）。
- **Base URL**：`https://api.<domain>/v1`（本地开发 `http://localhost:8000/v1`）。
- **鉴权**：`Authorization: Bearer <token>`；BYOK 的模型 Key 不在此处，仅存于服务端配置。
- **字符编码**：UTF-8；正文/卡面文本长度按 **字符数** 计（中文 1 字符 = 1）。
- **时间戳**：统一 UTC ISO-8601（`YYYY-MM-DDTHH:mm:ssZ`）。
- **分页**：列表接口统一参数 `page`（默认 1，≥1）、`page_size`（默认 20，1~100），返回统一 `{ items, total, page, page_size }`。

### 0.1 通用响应包装
成功：直接返回业务对象，或 `{ "data": <object> }`。
错误：
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "卡面文案超出最大长度",
    "details": { "field": "content", "max": 200 }
  }
}
```

### 0.2 统一错误码表（所有接口通用）
| code | HTTP | 含义 | 触发场景 |
|------|------|------|----------|
| `UNAUTHORIZED` | 401 | 未认证/凭证失效 | token 缺失或过期 |
| `FORBIDDEN` | 403 | 无权限 | 非项目所有者访问私有项目 |
| `NOT_FOUND` | 404 | 资源不存在 | id 错误 |
| `CONFLICT` | 409 | 状态冲突 | 对已采用/已锁定节点再次操作 |
| `VALIDATION_ERROR` | 422 | 参数校验失败 | 类型/必填/取值非法（details 指明字段） |
| `RATE_LIMITED` | 429 | 触发限流 | 服务端或模型限流，返回 `Retry-After` |
| `QUOTA_EXCEEDED` | 402 | 用量/额度超限 | token 预算打满 |
| `MODEL_ERROR` | 502 | 上游模型失败 | 服务商超时/错误 |
| `INTERNAL` | 500 | 服务端未知错误 | 兜底 |

---

## 1. 故事与项目

### 1.1 POST `/projects`
创建项目。**响应**：`Project`。

**请求体**
| 字段 | 类型 | 必填 | 取值范围/说明 |
|------|------|------|---------------|
| `title` | string | 是 | 1~80 字符（可空串，允许后置命名） |
| `genre_hint` | string | 否 | 题材提示，≤50 字符；空则随机 |
| `user_id` | string | 是 | 由鉴权 token 解析，不可由客户端传 |

**响应 `Project`**
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string(uuid) | 项目主键 |
| `title` | string | — |
| `version` | integer | 初始 1 |
| `created_at` | string(ISO) | — |
| `status` | enum | `DRAFT \| ACTIVE \| ARCHIVED` |

### 1.2 POST `/stories`
从灵感创建并初始化一个故事（触发 FR-1 初始化流程）。同步返回"整本方向候选"。

**请求体**
| 字段 | 类型 | 必填 | 取值范围 |
|------|------|------|----------|
| `project_id` | string(uuid) | 是 | 必须存在 |
| `premise` | string | 是 | 一句话灵感，10~200 字符 |
| `style_profile_id` | string(uuid) | 否 | 文风预设 id；缺省用 default |

**响应 `story_init_payload`**
```json
{
  "story_id": "uuid",
  "direction_candidates": [ { "title": "…", "synopsis": "…" } ],   // 3 个
  "status": "pending_user_selection"
}
```
> 选方向用 `POST /stories/{id}/select-direction`（见 1.4）。

### 1.3 GET `/stories/{id}`
**响应 `StorySummary`**：`id`、`title`、`genre`、`synopsis`、`status`（`init \| building \| writing \| finished`）、`current_chapter_no`（integer≥0）、`style_profile_id`、`updated_at`。

### 1.4 POST `/stories/{id}/select-direction`
**请求体**：`{ "candidate_index": integer, 0~2 }` 或 `{ "custom_synopsis": string, 10~200 }` 二选一。
**响应**：`StorySummary`，status 变为 `building`（触发世界观/角色/初始卡池生成，异步完成后由前端轮询 `GET /stories/{id}/state` 或等 SSE `story.built` 事件）。

---

## 2. 正文与流式生成

### 2.1 POST `/stories/{id}/generate/stream`　◆SSE
推进生成下一段正文。**决策点前**调用（无 direction 表示自然续写）。

**请求体**
| 字段 | 类型 | 必填 | 取值范围 |
|------|------|------|----------|
| `chapter_no` | integer | 是 | ≥1；须等于当前章节或 `+1`（开新章） |
| `direction` | object | 否 | 若携带，表示已确定方向（见 §6 `DirectionSpec`） |
| `mode` | enum | 否 | `generate \| regenerate`，默认 `generate`；`regenerate` 需带 `passage_id` |
| `passage_id` | string(uuid) | 条件必填 | `mode=regenerate` 时必填 |
| `max_tokens` | integer | 否 | 100~2000，默认 800 |
| `temperature` | number | 否 | 0.0~1.5；覆盖文风预设（默认由 StyleProfile 决定） |

**SSE 事件流（`data:` 行，UTF-8）**
| 事件 | data 负载 | 说明 |
|------|-----------|------|
| `passage_start` | `{ passage_id, passage_no }` | 生成开始 |
| `delta` | `{ text: string }` | 增量文本，逐段推送 |
| `decision_point` | `{ decision_no, passage_id }` | **正文到达分歧点**，停止流式等待决策 |
| `passage_end` | `{ passage_id, word_count }` | 该段完成（可能因触碰决策点中止） |
| `chapter_end` | `{ chapter_id, chapter_no, summary }` | 整章完成 |
| `story_built` | `{ status }` | 初始化建设完成（异步通知） |
| `error` | `{ code, message }` | 见 §0.2 错误码 |

> 前端在收到 `decision_point` 后应暂停展示"抽卡/输入"UI。

---

## 3. 抽卡（核心）

### 3.1 POST `/stories/{id}/decisions/{no}/cards`
在分歧点生成卡池（FR-3/FR-4）。成功后可多次重roll（生成新卡池）。

**请求体**：（可空 `{}`；可选 `regen_reason`: "dislike" 用于标注重roll）

**响应 `card_pool`**
```json
{
  "decision_no": 3,
  "pool_version": 1,
  "cards": [ { "card_id", "title", "content", "label", "rarity", "weight", "risk_balance" } ]
}
```
**`Card` 字段**
| 字段 | 类型 | 取值范围 |
|------|------|----------|
| `card_id` | string(uuid) | — |
| `title` | string | 1~40 字符 |
| `content` | string | 卡面文案，1~200 字符 |
| `label` | enum | `EVENT \| ACTION \| SCENE \| MEETING \| FORESHADOW` |
| `rarity` | enum | `N \| R \| SR \| SSR` |
| `weight` | integer | 1~100 |
| `risk_balance` | object? | 仅 SSR 必填：`{ tension: integer 1~10, suggested_turn: string ≤80 }` |

### 3.2 POST `/stories/{id}/decisions/{no}/gacha`
**盲抽**：服务端按 `weight`/稀有度概率随机揭晓一张卡（不可指定）。**防重放/防刷由服务端持有随机数**。

**请求体**：`{ "pool_version": integer }`（须匹配最新卡池，防并发；不匹配返回 409 `CONFLICT`）。

**响应**
```json
{
  "decision_no": 3,
  "mode": "gacha_draw",
  "card": { …省略同 Card… },
  "direction_spec": { …见 §6… }
}
```

### 3.3 POST `/stories/{id}/decisions/{no}/apply`
采用方向（明选某张卡 / 用自由输入 / 用改写后的卡）。调用后该决策节点**锁定**，重复调用返回 409。

**请求体**（三选一，使用互斥字段，否则 422）
| 字段 | 类型 | 说明 |
|------|------|------|
| `card_id` | string(uuid) | 明选：直接采用该卡 |
| `custom_instruction` | string | 自由输入：1~500 字符，交意图路由 |
| `custom_transform` | object | 改写卡：`{ card_id, new_content: string(1~200), direction_patch?: object }` |

**响应**：`{ decision_id, decision_no, mode, direction_spec, result_summary? }`，随后前端可继续调 `2.1 generate/stream` 传入该 `direction_spec`。

---

## 4. 状态 / 一致性视图

### 4.1 GET `/stories/{id}/state`
**响应 `StoryState`**
```json
{
  "story_id": "…",
  "world": { },
  "characters": [ { "character_id", "name", "role", "state": {}, "arc": "" } ],
  "foreshadows": [ { "foreshadow_id", "desc", "status" } ],
  "timeline_head": { "day": 3, "tick": 15 },
  "revision": 42
}
```
> 该视图只读，供 UI 展示"设定/角色/伏笔/时间线"。

### 4.2 GET `/stories/{id}/passages`  （分页）
**响应项**：`{ passage_id, passage_no, chapter_no, content, status: generated|final, decision_id? }`。

### 4.3 POST `/stories/{id}/passages/{passage_id}/finalize`
将草稿段标记为 `final`（用户在 UI 手改/确认后）。

---

## 5. 回溯 / 分支

### 5.1 POST `/stories/{id}/decisions/{no}/undo`
回退到该决策点之前（保留正文为 `generated`，可重跑生成）。

**响应**：`{ new_revision, affected_passage_ids: [] }`；若该节点已派生过分支则 409。

### 5.2 POST `/stories/{id}/decisions/{no}/branch`
从该决策点建分支。**请求体**：`{ "name": string, 1~60 }`。
**响应**：`{ branch_id, branch_name, decision_id, created_at }`；返回后此决策点进入"已分支"态（其后续正文副本化，互不影响）。

---

## 6. 数据结构：DirectionSpec（决策输出的统一数据结构）

被 `generate/stream`、`gacha`、`apply` 共同使用，是抽卡/输入与生成的解耦契约。

```json
{
  "kind": "EVENT",                 // enum: EVENT|ACTION|SCENE|MEETING|FORESHADOW|CUSTOM
  "summary": "让主角发现一张神秘藏宝图",
  "taget_character_id": "uuid?",   // 可选关联角色
  "scene": "城市凌晨的旧码头?",
  "constraints": [ "保持既定文风", "不引入超自然设定" ],  // ≤5 条
  "risk_flag": false                // 是否高张力争端（决定是否强一致性兜底）
}
```

---

## 7. 质量 / 审稿 / 用量

### 7.1 POST `/stories/{id}/passages/{passage_id}/revision`
触发自重审稿（FR-12）。**响应** `revision_report`
```json
{
  "issues": [ { "type": "CONTINUITY|STYLE|FACT", "severity": "critical|warning",
                "fragment": "原文片段", "reason": "…", "fix_suggestion": "…" } ],
  "passed": false
}
```

### 7.2 POST `/revisions/{revision_id}/apply`（一键修复，可选）
**请求体**：`{ "issue_ids": [uuid] }`；**响应**：替换后的正文段。

### 7.3 GET `/projects/{id}/usage`
**响应项**：`{ task, model, in_tokens, out_tokens, cost_usd, at }`，支持 `?from=&to=` 时间过滤。

### 7.4 POST `/users/models`（BYOK 配置）
**请求体**：`{ provider, api_key?, base_url?, model_id, default_temperature }`；**响应**：配置 id。Key 仅存服务端加密配置，不回传明文。

---

## 8. 后端需保证的约束（回归基线）
1. 所有枚举取值严格（§字段表），非法值 422。
2. 决策节点 `apply` / `gacha` 单次有效，重放 409。
3. 流式事件顺序固定：`passage_start → delta* → (decision_point | passage_end | chapter_end)`。
4. 正文与状态 `revision` 强一致：状态库回写失败则该 passage 保持 `generated`（不得标 `final`）。
5. SSR 卡必须带 `risk_balance`，否则 422。
6. 分页参数越界自动夹取，不报错。