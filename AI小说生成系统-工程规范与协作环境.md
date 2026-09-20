# AI 小说生成系统　工程规范与协作环境（Engineering Standards & Environment）

> 版本：v1.0　|　日期：2026-09-20
> 关联：规划 `AI 小说生成系统-开发计划与质量门禁.md`

---

## 1. 技术栈与目录结构（唯一事实源）

### 1.1 栈（与设计文档一致）
- 后端：Python 3.12 + FastAPI + LangGraph，包管理 `uv`，ORM SQLModel/SQLAlchemy，校验 Pydantic v2。
- 前端：Vue 3 + TypeScript + Vite + Pinia（状态），编辑器 TipTap（`@tiptap/vue-3`）或 Milkdown，接口客户端由 OpenAPI 生成（TS types）。
- 数据：SQLite（`better-sqlite3`/SQLite via SQLModel）+ LanceDB 向量。
- 桌面（可选）：Electron 或 Tauri。
- 测试：后端 pytest + pytest-asyncio；前端 vitest + Playwright；接口 schemathesis。

### 1.2 仓库结构（monorepo）
```
repo/
 ├─ backend/       # FastAPI 应用
 │   ├─ app/
 │   │   ├─ api/        # 路由（只收参/校验/调 service）
 │   │   ├─ services/   # 业务逻辑
 │   │   ├─ agents/     # LangGraph 图（writer/consistency/fixer/…）
 │   │   ├─ gacha/      # 抽卡引擎
 │   │   ├─ intent/     # 意图路由
 │   │   ├─ deslop/     # 去AI味规则
 │   │   ├─ llm/        # Gateway + providers
 │   │   ├─ models/     # 数据模型/迁移
 │   │   └─ storage/    # StateStore / VectorStore
 │   ├─ tests/
 │   └─ pyproject.toml
 ├─ frontend/      # Vue 3 应用
 ├─ contracts/     # OpenAPI 契约文件（单一事实源）
 ├─ infra/         # docker-compose、Dockerfile、Nginx
 └─ docs/          # 本套文档
```

---

## 2. 编码与协作规范

### 2.1 Python（后端）
- 类型注解完整；所有对外数据结构用 **Pydantic v2** 模型（同一处定义类型与校验）。
- 路由层**只负责收参/鉴权/调 service**，不写业务逻辑、不直接访问 DB。
- 例外/错误统一用约定错误码（见接口契约 §0.2），禁止裸抛 500。
- 格式化 `ruff format` + lint `ruff check`，类型检查 `mypy --strict`。
- 命名：`snake_case` 变量/函数，模块名短小名词，类 `PascalCase`。

### 2.2 TypeScript（前端，Vue）
- 接口类型**由 OpenAPI 自动生成**，禁止手写重复类型（防接口漂移）。
- 使用 Vue 3 组合式 API（`<script setup lang="ts">`）+ Pinia 状态管理；抽卡动画、流式正文等封装为可复用组件，避免 prop 钻透/重复逻辑。
- 格式化 `prettier`，lint `eslint`（vue 3 对应规则），类型检查 `vue-tsc --noEmit`。
- 命名：单文件组件 `PascalCase.vue`、组合式函数 `useXxx`、常量 `UPPER_SNAKE`。

### 2.3 契约优先（Contract-First）
- `contracts/` 下的 OpenAPI 是**改动必须经评审**的单一事实源 → 前后端据此生成 client/types。
- 改接口的**唯一合法路径**：改契约 → 评审 → 提交 → 两端重生成 → CI 校验 diff 为空。

### 2.4 提交规范（Conventional Commits）
`type(scope): subject`，type ∈ {feat, fix, refactor, chore, docs, test, perf, build}。示例：`feat(gacha): 支持盲抽揭晓动画`。破坏性变更加 `!`（如 `feat(story)!: 移除 xxx`）并写 `BREAKING CHANGE:`。

---

## 3. 分支策略与协作流程

### 3.1 Git 分支模型（GitHub Flow，用 Trunk-based 简化）
- `main`：始终可发布（绿）。只在合并 PR 后更新。
- 功能分支：`feat/<issue-id>-<kebab>`，从 main 切出。
- 修复分支：`fix/<issue-id>-<kebab>`。
- **禁止**直接 push main；一切通过 PR。

### 3.2 PR 流程
1. 从当前 main 切分支，对应 Issue（编号用于提交与 PR 关联）。
2. 本地 `ruff`/`mypy`/`tsc`/`test` 通过。
3. 开 PR，附模板：改动摘要 / 关联 Issue / 测试说明 / 契约是否变更。
4. CI 须全绿（lint + 类型 + 单测 + 契约 diff + 构建）。
5. 至少 **1 名** 非作者 reviewer 批准；契约/数据模型变更需 owner 复核。
6. 合并用 squash，保留清晰主线。

### 3.3 代码评审关注点（评审 checklist）
- 接口与契约是否一致（字段/枚举/错误码）。
- 是否引入未评级的 key/配置；是否碰了 `main` 不该动的范围。
- 一致性与状态回写是否有人兜底（生成改状态）。
- 异常/越权/重放是否处理。

---

## 4. 环境与工具

### 4.1 环境矩阵
| 环境 | 用途 | 地址 | 配置来源 |
|------|------|------|----------|
| dev（本地） | 日常开发 | 后端 `:8000`、前端 `:5173` | 本地 `.env`（BYOK） |
| test（CI/Staging） | 自动测试 + 集成 | CI 内 / `staging.<domain>` | secrets 托管 |
| prod | UAT/发布 | `https://api.<domain>` | secrets 托管，本地不落明文 |

所有敏感配置（API Key、数据库等）走**环境变量/secrets**，不入库。`docs/.env.example` 提供模板。

### 4.2 常用命令（团队统一）
- 后端：`uv sync` → `uv run uvicorn app.main:app --reload`；测试 `uv run pytest`。
- 前端：`npm ci` → `npm run dev`；测试 `npm test`；e2e `npm run e2e`。
- 契约：`schemathesis run <openapi>` 对实现跑契约校验。
- 本地一键：`docker compose up`（dev 全部起）。

### 4.3 版本控制工具
- Git 统一用 Underscore commit message（见 §2.4）。
- 禁止提交：`node_modules/`、`__pycache__/`、`.venv/`、`.env*`（除 `.env.example`）、模型 `output/`、`*.sqlite`（本地库）。
- 生成物（OpenAPI 生成的 client 类型）由 CI/构建产，不入库或按团队约定入库。

---

## 5. 缺陷管理流程

基于 `AI 小说生成系统-开发计划与质量门禁.md` §6，落地到工具（如 GitHub Issues + Labels）。

- **Issue 模板字段**：标题、环境、严重级（P0/P1/P2/P3）、复现步骤、期望行为、实际行为、受影响接口、相关 commit。
- **标签**：`P0/P1/P2/P3`、`bug/feature/enhancement`、`contract-change`。
- **流程状态机**：
  `New → Triaged(定级+指派) → In Progress → Fixed(提交链接修复PR) → Validate(QA) → Closed / Reopened`
- **效率约定**：
  - P0：当天响应，修复 PR 当天提。
  - P1：3 天内提修复。
  - P2/P3 进 backlog，排期后处理。
  - 提测（Validate）必须带复测证据（截图/日志/用例编号）。
- 涉及接口变更的 Bug，须同时改契约并标注 `contract-change`（阻止契约漂移）。

---

## 6. 结语
本文件 + 契约 + 计划 共同构成团队开工的"交通规则"。原则：**契约是协作边界，main 始终可发布，异常/越权/重放必须有兜底，接口变更必走契约流程**。