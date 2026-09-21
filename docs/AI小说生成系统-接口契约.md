# AI 小说生成系统　接口契约（API Specification）

> 版本：v1.0　|　日期：2026-09-20
> 关联：`AI 小说生成系统-设计文档.md` §9、`AI 小说生成系统-需求文档.md`
> 说明：本文档是**前后端并行开发契约**。所有字段名、类型、是否必填、取值范围、错误码以本文为准。正文流式生成统一走 SSE。

---

> **这份文档是干嘛的？**
> 简单说，这就是一份「前后端照着它对接口的说明书」。前端（网页/App）和后端（服务器）各写各的代码，两边靠本文档里约定的「地址、要传的参数、服务器会给什么」来对接，谁都不许自己改口径。
> 本文用大白话把每个接口的**用途**讲清楚，但接口的**地址、参数、返回字段、取值范围、错误码这些硬信息一律原封不动**，改一个字都可能对不上号。凡是用引号或等宽字标出来（如 `project_id`、`BASIC`）的，都是原文里的字段名/取值，请直接照抄。

---

## 0. 通用约定（所有接口都遵守的公共规则）

- **协议（传输方式）**：HTTP/1.1 over TLS（即加密的 HTTP；本地开发可降级为普通 http）；所有请求的 `Content-Type` 一律用 `application/json`（流式推送那类事件用 `text/event-stream`）。
- **Base URL（地址前缀）**：`https://api.<domain>/v1`（本地开发 `http://localhost:8000/v1`）。后面的每个接口地址都要拼在这个前缀后面。
- **鉴权（身份验证）**：请求头带 `Authorization: Bearer <token>`；BYOK（自带模型密钥）的模型 Key 不放在这里，只存在服务器配置里。
- **字符编码**：UTF-8；正文/卡面文案的长度按 **字符数** 数（中文 1 个字符 = 1）。
- **时间戳**：统一用 UTC ISO-8601 格式（长这样：`YYYY-MM-DDTHH:mm:ssZ`）。
- **分页（一次显示多少条）**：列表类接口统一用 `page`（页码，默认 1，最小 1）和 `page_size`（每页条数，默认 20，范围 1~100）这两个参数，返回格式固定为 `{ items, total, page, page_size }`。

### 0.1 通用响应包装（成功和失败长什么样）
- 成功：直接返回业务对象，或者返回 `{ "data": <对象> }`。
- 失败（出错）长这样：
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "卡面文案超出最大长度",
    "details": { "field": "content", "max": 200 }
  }
}
```
（`code` 是错误代码，`message` 是给人看的说明，`details` 里标注具体是哪个字段出了问题。）

### 0.2 统一错误码表（所有接口通用）
| code（代码） | HTTP（状态码） | 含义（大白话） | 触发场景（什么时候会抛） |
|------|------|------|----------|
| `UNAUTHORIZED` | 401 | 没登录/凭证失效 | token 缺失或过期 |
| `FORBIDDEN` | 403 | 没权限 | 不是项目所有者却想访问私有项目 |
| `NOT_FOUND` | 404 | 找不到这个东西 | id 写错了 |
| `CONFLICT` | 409 | 状态冲突（这步已经做过了） | 对已采用/已锁定的节点再次操作 |
| `VALIDATION_ERROR` | 422 | 参数没通过校验 | 类型/必填/取值不合法（details 里标明字段） |
| `RATE_LIMITED` | 429 | 请求太频繁被限流 | 服务端或模型限流，会返回 `Retry-After` |
| `QUOTA_EXCEEDED` | 402 | 用量/额度用完了 | token 预算打满 |
| `MODEL_ERROR` | 502 | 上游模型（写正文的 AI）出错 | 服务商超时/错误 |
| `INTERNAL` | 500 | 服务器内部未知错误 | 兜底，实在没别的可报时就报它 |

---

## 1. 故事与项目

### 1.1 POST `/projects`
这个接口：**新建一个项目**（项目就是装故事的一个"文件夹"/容器）。成功后会返回一个 `Project` 对象。

**请求体（要传的参数）**
| 字段 | 类型 | 必填 | 取值范围/说明 |
|------|------|------|---------------|
| `title` | string | 是 | 1~80 字符（可以传空串，允许后补命名） |
| `genre_hint` | string | 否 | 题材提示（比如"玄幻""悬疑"），最长 50 字符；不传就随机 |
| `user_id` | string | 是 | 由鉴权 token 解析出来，不允许客户端自己传 |

**响应 `Project`（返回的对象）**
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string(uuid) | 项目主键（唯一编号） |
| `title` | string | — |
| `version` | integer | 初始为 1 |
| `created_at` | string(ISO) | 创建时间 |
| `status` | enum | 状态，取值为 `DRAFT \| ACTIVE \| ARCHIVED`（草稿 \| 进行中 \| 归档） |

### 1.2 POST `/stories`
这个接口：**从一句灵感创建并初始化一个故事**（触发 FR-1 初始化流程）。调用后是同步返回的，给的是"整本书的方向候选"（通常是几个简介让你选一个走向）。

**请求体**
| 字段 | 类型 | 必填 | 取值范围 |
|------|------|------|----------|
| `project_id` | string(uuid) | 是 | 必须真实存在 |
| `premise` | string | 是 | 一句话灵感，10~200 字符 |
| `style_profile_id` | string(uuid) | 否 | 文风预设的 id；不传就用 default（默认文风） |

**响应 `story_init_payload`（返回的对象）**
```json
{
  "story_id": "uuid",
  "direction_candidates": [ { "title": "…", "synopsis": "…" } ],   // 3 个
  "status": "pending_user_selection"
}
```
> 选出方向用 `POST /stories/{id}/select-direction`（见 1.4）。

### 1.3 GET `/stories/{id}`
这个接口：**按故事 id 拉取这个故事的概况**（进度条之类的前端展示用）。里面的 `{id}` 是故事 id 的占位符，请求时要替换成具体值。

**响应 `StorySummary`**：`id`、`title`、`genre`、`synopsis`、`status`（取值 `init \| building \| writing \| finished`，即：初始化 \| 建设中 \| 写作中 \| 已完成）、`current_chapter_no`（integer，当前章节号，最小 0）、`style_profile_id`、`updated_at`。

### 1.4 POST `/stories/{id}/select-direction`
这个接口：**选定第 1.2 步给的"方向候选"里的其中一个**，确认故事往哪个方向走。

**请求体**：传 `{ "candidate_index": integer, 0~2 }`（选序号 0/1/2）**或** `{ "custom_synopsis": string, 10~200 }`（自己写一句话简介）二选一。
**响应**：`StorySummary`，`status` 会变为 `building`（开始生成世界观/角色/初始卡池；这批内容是异步完成的，完成后前端轮询 `GET /stories/{id}/state` 看结果，或者等 SSE 的 `story.built` 事件通知）。

---

## 2. 正文与流式生成

### 2.1 POST `/stories/{id}/generate/stream`　◆SSE
这个接口：**让 AI 往下写一段正文，一边写一边通过 SSE 推给你**（SSE 就是服务器往浏览器/客户端持续推送消息的一种技术，前端拿到增量文本就能一段段显示出来）。要在**决策点之前**调用（不传 direction 就表示自然续写，不打断故事方向）。

**请求体**
| 字段 | 类型 | 必填 | 取值范围 |
|------|------|------|----------|
| `chapter_no` | integer | 是 | 最小 1；必须等于当前章节号，或者当前章号 `+1`（表示开新章） |
| `direction` | object | 否 | 如果带了，表示方向已经确定（结构见 §6 `DirectionSpec`） |
| `mode` | enum | 否 | `generate \| regenerate`，默认 `generate`；`regenerate`（重新生成）时必须带 `passage_id` |
| `passage_id` | string(uuid) | 条件必填 | 仅当 `mode=regenerate` 时才必填 |
| `max_tokens` | integer | 否 | 100~2000，默认 800（一次最多写多少 token） |
| `temperature` | number | 否 | 0.0~1.5；这里传了会覆盖文风预设（不传则由 StyleProfile 决定） |

**SSE 事件流（就是服务器一路推回来的 `data:` 行，UTF-8 编码）**
| 事件 | data 负载 | 说明 |
|------|-----------|------|
| `passage_start` | `{ passage_id, passage_no }` | 开始生成这一段了 |
| `delta` | `{ text: string }` | 增量文本，逐段推送（前端边收边显示） |
| `decision_point` | `{ decision_no, passage_id }` | **正文写到了分叉口**，停止流式输出，等你来做选择 |
| `passage_end` | `{ passage_id, word_count }` | 这一段写完了（可能是正常写完，也可能是碰到决策点被中途停掉） |
| `chapter_end` | `{ chapter_id, chapter_no, summary }` | 整章写完了 |
| `story_built` | `{ status }` | 初始化建设完成（异步通知） |
| `error` | `{ code, message }` | 出错，代码见 §0.2 错误码表 |

> 前端一旦收到 `decision_point`，就该暂停展示"抽卡/输入"的界面，等用户做选择。

---

## 3. 抽卡（核心玩法）

（这里的"抽卡"是一股小说玩法：故事在分叉口给出几张"命运卡片"，用户抽/选其中一张，决定故事往哪走。）

### 3.1 POST `/stories/{id}/decisions/{no}/cards`
这个接口：**在某个分歧点上生成一版卡池**（FR-3/FR-4）。这里的 `{no}` 是决策序号。成功后可以多次调用重 roll（会生成一版新卡池）。**注意**：这个接口只是"生成卡池给前端摆出来看"，还没定要用哪张。

**请求体**：可以不传参数（传 `{}` 空对象即可）；也可以带可选参数 `regen_reason`，值为 `"dislike"` 用来标注这是"重 roll"（用户不喜欢上一版）。

**响应 `card_pool`（返回的卡池）**
```json
{
  "decision_no": 3,
  "pool_version": 1,
  "cards": [ { "card_id", "title", "content", "label", "rarity", "weight", "risk_balance" } ]
}
```
**`Card` 字段（每张卡）**
| 字段 | 类型 | 取值范围 |
|------|------|----------|
| `card_id` | string(uuid) | 卡的唯一编号 |
| `title` | string | 1~40 字符 |
| `content` | string | 卡面文案，1~200 字符 |
| `label` | enum | 卡的类型，取值 `EVENT \| ACTION \| SCENE \| MEETING \| FORESHADOW`（事件 \| 行动 \| 场景 \| 会面 \| 伏笔） |
| `rarity` | enum | 稀有度，取值 `N \| R \| SR \| SSR` |
| `weight` | integer | 1~100（权重越大越容易被抽中） |
| `risk_balance` | object? | 仅 SSR（最稀有）卡必填：`{ tension: integer 1~10, suggested_turn: string ≤80 }` |

### 3.2 POST `/stories/{id}/decisions/{no}/gacha`
这个接口：**盲抽**。服务器按每张卡的 `weight`/稀有度概率随机揭晓一张卡给你，**你没法指定抽到哪张**。**防止重复抽/防刷由服务器这边持有随机数**（也就是结果在服务端算，客户端改不了）。

**请求体**：`{ "pool_version": integer }`（必须和最新卡池的版本对上，用来防止并发错乱；对不上就返回 409 `CONFLICT`）。

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
这个接口：**正式"定下"这个分歧点的走向**——可以明说用某张卡、也可以自己输入一句话、也可以用改写后的卡。调用之后，这个决策节点就**锁定**了，不能再来一遍；再调就返回 409。

**请求体**（三选一，三个字段互斥，只能带一个；带多了返回 422）
| 字段 | 类型 | 说明 |
|------|------|------|
| `card_id` | string(uuid) | 明选：直接采用这张卡 |
| `custom_instruction` | string | 自由输入：1~500 字符，交给意图路由处理（理解成"按用户自己说的一句话来定方向"） |
| `custom_transform` | object | 改写卡：`{ card_id, new_content: string(1~200), direction_patch?: object }`（在原卡基础上微调方向） |

**响应**：`{ decision_id, decision_no, mode, direction_spec, result_summary? }`；拿到 `direction_spec` 后，前端可以接着调 2.1 的 `generate/stream`，把它传进去让 AI 按这个方向继续写。

---

## 4. 状态 / 一致性视图

（这一节是"查进度/查当前设定"的只读接口，前端拿来做展示，不改任何东西。）

### 4.1 GET `/stories/{id}/state`
这个接口：**拉取这个故事当前的全部"背后设定"**——世界观、角色、伏笔、时间线走到哪了。前端拿去展示"设定/角色/伏笔/时间线"。

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
> 这个视图是只读的，仅供 UI 展示"设定/角色/伏笔/时间线"用。

### 4.2 GET `/stories/{id}/passages`  （分页）
这个接口：**分页拉取这个故事的所有正文段落**。
**响应项**：`{ passage_id, passage_no, chapter_no, content, status: generated|final, decision_id? }`。

### 4.3 POST `/stories/{id}/passages/{passage_id}/finalize`
这个接口：**把某段草稿标记为"定稿"**（`final`）。通常是用户在界面上手动改完、确认没问题之后调用。这里的 `{passage_id}` 是要定稿的那段的 id。

---

## 5. 回溯 / 分支

### 5.1 POST `/stories/{id}/decisions/{no}/undo`
这个接口：**后悔了，回退到某个决策点之前**。回退后，相关正文保留为 `generated`（草稿）状态，之后还可以重跑生成。

**响应**：`{ new_revision, affected_passage_ids: [] }`（新的版本号 + 受影响的段落 id 列表）；如果这个决策点已经派生过分支了，就返回 409（没法回退）。

### 5.2 POST `/stories/{id}/decisions/{no}/branch`
这个接口：**在这个决策点开一条新分支**（相当于"分岔出另一条剧情线"，各走各互不影响）。
**请求体**：`{ "name": string, 1~60 }`（给这条分支起个名）。
**响应**：`{ branch_id, branch_name, decision_id, created_at }`；返回之后，这个决策点进入"已分支"状态，它下面的正文会自动复制一份，两边互不影响。

---

## 6. 数据结构：DirectionSpec（决策输出的统一数据结构）

（这是"抽卡/输入的结果"到底长什么样的一份通用结构约定。它被 `generate/stream`、`gacha`、`apply` 三个接口共同共用，作用是**把"用户定下的方向"和"AI 怎么生成"这俩解耦**——先把方向定成这个统一格式，再喂给生成接口。）

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
这个接口：**触发一次"自我审稿"**（让 AI 检查这段写得有没有问题，FR-12）。
**响应 `revision_report`（审稿报告）**
```json
{
  "issues": [ { "type": "CONTINUITY|STYLE|FACT", "severity": "critical|warning",
                "fragment": "原文片段", "reason": "…", "fix_suggestion": "…" } ],
  "passed": false
}
```
（`type` 是问题类型：衔接不畅 CONTINUITY / 文风不合 STYLE / 前后矛盾 FACT；`severity` 是严重程度：critical 严重 / warning 提醒；`passed: true/false` 表示有没有通过审稿。）

### 7.2 POST `/revisions/{revision_id}/apply`（一键修复，可选）
这个接口：**一键修复审稿发现的问题**（可选项，不是必调）。
**请求体**：`{ "issue_ids": [uuid] }`（要修哪几条问题的 id）；**响应**：修复后替换好的正文段。

### 7.3 GET `/projects/{id}/usage`
这个接口：**查这个项目的用量/费用**。
**响应项**：`{ task, model, in_tokens, out_tokens, cost_usd, at }`（任务名、用的模型、进来多少字符、出去多少字符、花了多少美元、时间），支持用 `?from=&to=` 传时间范围做过滤。

### 7.4 POST `/users/models`（BYOK 配置）
这个接口：**配置用户自带的模型 Key（BYOK）**。用户把自己的模型连进来。
**请求体**：`{ provider, api_key?, base_url?, model_id, default_temperature }`（服务商、密钥、地址、模型 id、默认温度）；**响应**：配置 id。密钥只在服务端加密保存，**绝不回传明文**。

---

## 8. 后端需保证的约束（回归基线）

（这几条是"后端必须做到"的硬要求，改版时不能弄丢，是回归测试的底线。）
1. 所有枚举取值必须严格（见各字段表），非法值一律返回 422。
2. 决策节点的 `apply` / `gacha` 一次有效，重复调用返回 409。
3. 流式事件顺序固定，必须是：`passage_start → delta* → (decision_point | passage_end | chapter_end)`。
4. 正文与状态的 `revision` 强一致：状态库回写失败的话，该 passage 保持 `generated`（草稿）状态，**不能标成** `final`。
5. SSR 卡必须带 `risk_balance`，否则返回 422。
6. 分页参数越界时自动往边界内收拢（自动夹取），不报错。