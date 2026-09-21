# AI Novel Gacha · 命运抽卡互动小说生成系统

> 以「**抽卡（Gacha）** / **自由输入**」作为剧情决策核心机制的 AI 互动小说生成系统。用户在剧情分歧点抽一张命中卡（盲抽/明选）或用自然语言自由引导，系统据此连续生成剧情连贯、去 AI 味的**分卷长篇小说**正文，并支持真实世界信息召回与自动完结。

**当前状态**：完整创作闭环已可跑通——开书（异步任务）→ 构建世界观/历史/角色/伏笔种子与关系账本 → 抽卡/自由输入 → 正文流式生成（剧情时间线逐拍追加复盘）→ 一致性质检 + 去 AI 味 → **分章分卷 → LLM 收敛自动完结**。并已接入**真实信息召回**（开书按画像网络预取 + 每次决策实时检索注入）与**简介事实校验门**。数据 **SQLite + Chroma 向量库持久化**（重启不丢）。需在设置面板/接口配置模型（BYOK），未接入真实模型时生成会明确报错提示，不再静默降级 mock。

---

## 核心玩法

```
正文推进 → 到达分歧点 → 生成 3~5 张命中卡
        → ① 盲抽(随机揭晓) | ② 明选(展示卡面) | ③ 自由输入(自然语言引导 / 改写卡)
        → 采用方向 → 流式生成下一段正文 → 一致性校验 + 去AI味 → 状态回写 → 循环
        → 剧情浓度回落 / LLM 收敛判定 → 分卷 · 自动完结
```

卡牌带稀有度（N / R / SR / SSR），SSR 强制携带 `risk_balance`（张力 + 后续转折），避免"抽到神卡但剧情断线"。下一拍卡池**惰性生成**（正文流结束才召唤新分歧点，正文结束后自动提交并关闭按钮，防重复提交）。

---

## 功能总览

- [x] 后端骨架 + 核心抽卡决策引擎（数据模型 / 加权盲抽 / 明选，rng 可注入）
- [x] 前端 Vue3 决策闭环 UI（盲抽/明选/自由输入）
- [x] LLM Gateway（OpenAI 兼容多提供商 + BYOK，取消 mock 降级；LLM 未接入时明确报错）
- [x] DirectionGenerator 分歧点真实卡池 + WriterAgent 正文生成
- [x] **决策闭环 API + 前端接入**（抽卡 → 生成正文 跑通）
- [x] **SSE 流式输出**（`POST /decisions/{no}/stream`，逐 token 增量显示；流结束立即提交并关按钮）
- [x] **持久化：SQLite + Chroma 向量库**（重启不丢；写透 + 内存缓存，接口对服务层不变）
- [x] **一致性质检 + 去 AI 味 lint**（生成后自动扫描；`post /passages/{no}/lint` 可重扫）
- [x] **前置构建：世界观 / 历史线 / 角色 + 伏笔种子**（LLM 强 schema；初始伏笔从 `foreshadow_seeds` 长出）
- [x] **剧情时间线**（`GET /stories/{id}/timeline`）：每次决策追加"这拍发生了什么"，随选择复盘，区别于固定世界历史线
- [x] **文风预设 StyleProfile**（金庸武侠 / 现代都市 / 玄幻修仙 / 悬疑克苏鲁 / 沉稳冷峻，随书选择；含真实 LLM 文风对比页与说明页）
- [x] **一致性关联：角色/伏笔状态**（结构化设定事实清单注入校验 + 伏笔账本，`GET /foreshadows`）
- [x] **关系账本 + 知识图谱可视化**（echarts 图谱；剧情浓度差分推进剧情）
- [x] **叙事上下文：近期剧情前文召回 + 有界相关裁剪**（避免越写越跑偏）
- [x] **真实信息召回**：开书一次 LLM 判定检索画像（按专业/历史/技术/地域/时效专题），网络预取并入 `grounding`；每次决策实时增量检索本地向量库注入上下文
- [x] **简介真实信息门**（`/synopsis`）：前置召回真实事实 + 出厂事实校验门，冲突回喂重写
- [x] **章节分卷 + LLM 收敛完结**（软判定收束，`ending_max_chapters` 兜底；完结后拒绝新决策，`story.status == completed`）
- [x] **开书异步任务 + 轮询**（多书并行、单书内部扇出）
- [x] **书签持久化（localStorage）+ 我的收藏页**
- [x] **阅读翻页模式**：滚动连读 / 章节翻页（一屏当前章），正文按章渲染章节头，配套阅读主题·字体·字号设置
- [x] **书架 / 导入 / 导出**（md / txt / json 快照；删除二次确认；`undo` 撤销上一拍）

---

## 难点与解法（踩过的坑）

**难点：AI 写的简介/正文总是一个味。** 给一句灵感开书，简介老是往"击败黑恶势力"这种烂大街套路跑，还会不管什么前提都硬塞现代科技——因为模型没有实料可依、提示词又催它编点冲突，它就拿训练数据里概率最高的那个模板填空。

**解法：给生成环节喂"题材引导"。** 开书时 profiling（本来每书就要判一次画像）顺带把题材认出来 → 去题材库里查这个题材该"避点什么、按什么节奏写"，拼进简介/蓝图/正文/命运卡的提示词里，明确告诉模型"你是玄幻就不是刑侦，别硬套反派的打脸套路"。题材卡与反模式清单直接搬自开源 MIT 项目 oh-story（32 张正文题材卡）和 storyforge（反模式表），带来源说明；开关 `genre_guidance_enabled` 可一键关闭。识别出的题材还存进书里，书架/快照都直接显示。

顺手调了正文/简介的**生成温度**：简介单独用较高温度（0.9）求新颖，文风选择仍保持稳定——避免"简介和文风选择共用一套参数"导致简介越写越一样。

---

## 技术栈

| 层 | 选型 |
|----|------|
| 后端 | Python ≥3.11 · FastAPI · Pydantic v2 · uv |
| 检索/存储 | sqlite3（stdlib）+ **Chroma 向量库**（本地 RAG，n-gram 兜底 embedding） |
| 前端 | Vue 3 · Vite · TypeScript · Pinia · vue-router · echarts（知识图谱） |

> 运行依赖均未提交（`.venv/`、`node_modules/`、`backend/data/`、`*.sqlite` 均已 gitignore），首次需 `uv sync` / `npm install`。

---

## 目录结构

```
.
├─ backend/                 # FastAPI 后端
│  ├─ app/
│  │  ├─ main.py            # 应用入口 + 健康检查
│  │  ├─ config.py          # pydantic-settings 统一配置（API Key 走环境变量）
│  │  ├─ schemas.py         # 核心数据模型（与《接口契约》一致）
│  │  ├─ api/routes.py      # /v1 全量路由
│  │  ├─ gacha/engine.py    # 抽卡引擎（加权盲抽 / 明选，rng 可注入）
│  │  ├─ llm/               # LLM Gateway（多提供商 + 路由 + BYOK）
│  │  ├─ services/          # 创作管线各环节
│  │  │  ├─ blueprint.py    #   世界观/历史/角色/伏笔种子构建
│  │  │  ├─ direction.py    #   分歧点卡池 + 惰性下一拍
│  │  │  ├─ writer.py       #   正文生成（按文风路由）
│  │  │  ├─ narrative.py    #   叙事上下文（前文召回 + 有界裁剪）
│  │  │  ├─ progression.py  #   章节分卷 + LLM 收敛完结判定
│  │  │  ├─ retrieval.py    #   检索画像判定 + 网络预取
│  │  │  ├─ grounding.py    #   每次决策实时事实检索注入
│  │  │  ├─ facts.py        #   事实账本 / 简介校验门、角色伏笔状态
│  │  │  ├─ styles.py       #   文风预设
│  │  │  ├─ vector_kb.py    #   Chroma 向量库封装
│  │  │  ├─ tasks.py        #   开书异步任务
│  │  │  ├─ keychain.py     #   模型配置持久化（Key 脱敏）
│  │  │  └─ story_service.py / store.py / jsonparse.py / registry.py …
│  │  ├─ consistency/checker.py  # 一致性质检
│  │  ├─ deslop/lint.py          # 去 AI 味 lint
│  │  └─ storage/sqlite.py       # SQLite 持久化
│  └─ tests/                # pytest（17 个用例文件，127 个用例）
├─ frontend/                # Vue3 前端
│  └─ src/
│     ├─ views/             # HomeView(书架) / StoryView(阅读) / LoreView(世界观·简介)
│     │                     # FavoritesView(收藏) / StyleCompareView / StyleAboutView
│     ├─ components/        # DecisionPanel / BlueprintPanel / GroundingPanel
│     │                     # ChapterDirPanel / KnowledgeGraph / ReadingSettingsPanel / SettingsPanel
│     ├─ stores/            # decision.ts / reading.ts（翻页模式·主题·字号）
│     ├─ api/client.ts · types.ts
│     └─ router/index.ts
├─ novel_projects/          # 调研用第三方克隆（gitignored，不入库）
└─ *.md                     # 完整设计文档集（见下）
```

---

## 文档集（设计源头）

| 文档 | 内容 |
|------|------|
| `AI小说生成系统-需求文档.md` | 需求与验收基线（FR/NFR/优先级/指标） |
| `AI小说生成系统-设计文档.md` | 总体架构 / 技术选型 / 核心流程 / 数据模型 |
| `AI小说生成系统-接口契约.md` | API Spec（字段/类型/必填/取值范围/错误码） |
| `AI小说生成系统-开发计划与质量门禁.md` | 里程碑 / RACI / 测试基线 |
| `AI小说生成系统-工程规范与协作环境.md` | 编码规范 / 分支策略 / 环境 |
| `AI小说生成系统-提示词与前置创作流程规范.md` | 提示词借鉴来源（MIT 合规）/ 世界观·历史·大纲前置流程 / 去AI味规则 |
| `检索触发机制-开源对比与落地报告.md` | 真实信息召回触发机制的开源对比与落地设计 |
| `小说生成开源项目调研报告.md` | 11 个 >200star 项目调研与优劣分析 |

---

## 本地运行

### 后端
```bash
cd backend
uv sync
uv run pytest          # 运行测试（127 用例）
uv run uvicorn app.main:app --reload --port 8000
# 健康检查: GET http://localhost:8000/v1/health
```

### 启用真实模型（无需改文件，页面右上角「⚙ 模型」配置）
```bash
# 方式一：页面配置（前端设置面板保存，持久化到 SQLite）
#   打开 http://localhost:5173 → 右上角「⚙ 模型」→ 填 provider/model/base_url/api_key → 保存
#   或直接调用接口：
curl -X POST http://localhost:8000/v1/models/config \
  -H 'Content-Type: application/json' \
  -d '{"provider":"deepseek","model":"deepseek-chat","api_key":"sk-xxxx","base_url":"https://api.deepseek.com/v1"}'

# 方式二：环境变量/.env（backend/.env，已 gitignore）
#   DEFAULT_PROVIDER=deepseek
#   DEFAULT_MODEL=deepseek-chat
#   API_KEYS='{"deepseek":"sk-xxxx"}'
#   BASE_URLS='{"deepseek":"https://api.deepseek.com/v1"}'
```
> 配置优先级：页面/接口保存的 Keychain > 环境变量/.env。未接入模型时生成会报错提示（不再有本地 mock 降级）。
> 状态查询：`GET /v1/models/config`（Key 脱敏）；清空：`POST /v1/models/config/clear`。

### 前端
```bash
cd frontend
npm install
npm run dev            # 打开 http://localhost:5173（/v1 自动代理到 :8000）
```

---

## 后续规划

- [ ] 正式 License（当前代码仓库私有开发中；发布前确定，参考：提示词借鉴自 MIT 项目 oh-story / storyforge，规避 AGPL 传染）

---

## License
代码部分仓库私有开发中；正式发布前确定 License（参考：提示词借鉴自 MIT 项目 oh-story / storyforge，规避 AGPL 传染）。