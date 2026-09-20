# AI Novel Gacha · 命运抽卡互动小说生成系统

> 以「**抽卡（Gacha）** / **自由输入**」作为剧情决策核心机制的 AI 互动小说生成系统。用户在剧情分歧点：抽一张命运卡（盲抽/明选）或用自然语言自由引导，系统据此连续生成剧情连贯、去 AI 味的长篇小说正文。

**当前状态**：MVP 决策闭环**已可跑通**——灵感开书 → 构建世界观/历史/角色与伏笔种子 → 抽卡/自由输入 → 生成正文（剧情时间线随选择逐拍追加复盘）→ 去 AI 味/一致性质检，且 **SQLite 持久化**（重启不丢）。需在设置面板/接口配置模型（BYOK），未接入真实模型时生成会明确报错提示，不再静默降级 mock。

---

## 核心玩法

```
正文推进 → 到达分歧点 → 生成 3~5 张命运卡
        → ① 盲抽(随机揭晓) | ② 明选(展示卡面) | ③ 自由输入(自然语言引导 / 改写卡)
        → 采用方向 → 生成下一段正文 → 一致性校验 + 去AI味 → 状态回写 → 循环
```

卡牌带稀有度（N / R / SR / SSR），SSR 强制携带 `risk_balance`（张力 + 后续转折），避免"抽到神卡但剧情断线"。

---

## 技术栈

| 层 | 选型 |
|----|------|
| 后端 | Python 3.12 · FastAPI · Pydantic v2 · uv（LLM_Gateway / LangGraph 规划中） |
| 前端 | Vue 3 · Vite · TypeScript · Pinia · vue-router |
| 数据（规划） | SQLite + 文件系统 · LanceDB（RAG，可选） |

---

## 目录结构

```
.
├─ backend/              # FastAPI 后端
│  ├─ app/
│  │  ├─ main.py         # 应用入口 + 健康检查
│  │  ├─ config.py       # pydantic-settings 统一配置（API Key 走环境变量）
│  │  ├─ schemas.py      # 核心数据模型（Card/CardPool/DirectionSpec/…，与契约一致）
│  │  ├─ api/routes.py   # /v1 路由
│  │  └─ gacha/engine.py # 抽卡引擎（盲抽加权随机 / 明选，rng 可注入）
│  └─ tests/             # pytest（11 用例通过）
├─ frontend/             # Vue3 前端
│  └─ src/
│     ├─ components/DecisionPanel.vue  # 抽卡决策面板（盲抽/明选/自由输入）
│     ├─ stores/decision.ts            # 决策 store（占位卡池 + 加权盲抽）
│     ├─ views/                        # HomeView / StoryView
│     └─ types.ts                      # 与《接口契约》一致的客户端类型
├─ novel_projects/       # 调研用第三方克隆（gitignored，不入库）
└─ *.md                  # 完整设计文档集（见下）
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
| `小说生成开源项目调研报告.md` | 11 个 >200star 项目调研与优劣分析 |

---

## 本地运行

### 后端
```bash
cd backend
uv sync
uv run pytest          # 运行测试
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

> 说明：PyVenv 等运行依赖均未提交，首次需 `uv sync` / `npm install`。

---

## 路线图

- [x] 后端骨架 + 核心抽卡决策引擎（数据模型 / 加权盲抽 / 明选）
- [x] 前端 Vue3 决策闭环 UI（盲抽/明选/自由输入）
- [x] LLM Gateway（OpenAI 兼容多提供商 + BYOK，取消 mock 降级）
- [x] DirectionGenerator：分歧点生成真实卡池 + WriterAgent 正文生成
- [x] **决策闭环 API + 前端接入**（抽卡 → 生成正文 跑通）
- [x] **持久化：SQLite**（重启不丢；写透 + 内存缓存，接口对服务层不变）
- [x] **一致性质检 + 去 AI 味 lint**（生成后自动扫描；`post /passages/{no}/lint` 可重扫）
- [x] **前置构建：世界观 / 历史线 / 角色 + 伏笔种子**（LLM 强 schema，`GET /blueprint`；初始伏笔从 `foreshadow_seeds` 长出）
- [x] **剧情时间线**（`GET /stories/{id}/timeline`）：每做一次决策追加一条"这拍发生了什么"，随选择复盘，区别于固定的世界历史线
- [x] **文风预设 StyleProfile**（金庸武侠/现代都市/玄幻修仙/悬疑克苏鲁/沉稳冷峻，可随某本故事选择）
- [x] **一致性关联角色/伏笔状态**（结构化设定事实清单注入校验 + 伏笔账本，`GET /foreshadows`）
- [x] **正文 SSE 流式输出**（`POST /decisions/{no}/stream`，逐 token 增量显示）

---

## License
代码部分仓库私有开发中；正式发布前确定 License（参考：提示词借鉴自 MIT 项目 oh-story / storyforge，规避 AGPL 传染）。