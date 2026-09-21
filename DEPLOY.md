# 公网多用户部署指南（轻量简化）

整个系统是 **FastAPI 后端 + Vue 前端 + SQLite**，公网部署只需一台云服务器 + Caddy（或 nginx）+ 一个进程。
多用户隔离与「每用户自带模型 Key（BYOK）」已在代码内完成，无需外部数据库/认证服务。

## 一、本仓库已就绪的多用户能力

| 能力 | 说明 |
| --- | --- |
| 用户注册/登录 | `POST /v1/auth/register`、`/v1/auth/login`，返回会话 token（PBKDF2 存密码哈希） |
| 会话鉴权 | 请求带 `Authorization: Bearer <token>`，全部业务接口校验（未登录 → 401） |
| 数据隔离 | `stories.keychain` 均带 `user_id`；越权访问他人书一律按 404（不泄露存在性） |
| 每用户模型 | `settings` 面板保存的 `provider/model/base_url/api_key` 按用户各自生效，互不影响 |
| Key 加密落库 | 配置 `SECRET_KEY`（secure 组）后用 Fernet 加密存储 API Key；查询不回传明文 |
| 前端登录态 | 登录页 + 路由守卫 + 自动附带 Authorization 头 + token 失效自动回登录页 |

## 二、服务端启动

```bash
cd backend
python -m venv .venv && ./.venv/Scripts/pip install -e '.[secure]'   # 公网装 secure 组以启用 Key 加密
# 生成并填写 SECRET_KEY（见 .env.example），务必与模型 Key 分开保管
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

> **保持单 worker**：`tasks`（异步开书任务）是进程内注册表，多 worker 会把任务打散。并发建议交给上一层（见下）。

## 三、前端构建 + Caddy（自动 HTTPS）

生产环境推荐 **Caddy 同域托管前端 + 反代 API**：浏览器只访问一个域名，`/v1/*` 交给后端，天然规避 CORS。

```nginx
# Caddyfile 示例（部署到服务器后）：域名替换为你的真实域名
novel.example.com {
    # 托管前端构建产物（frontend/dist）
    root * /srv/choice_novel/frontend/dist
    try_files {path} /index.html          # Vue history 路由回退

    # 业务 API 反代到本地后端
    handle_path /v1/* {
        reverse_proxy 127.0.0.1:8000
    }

    encode gzip
}
```

- Caddy 自动申请/续期 Let's Encrypt 证书，`https://novel.example.com` 直达。
- HTTP/3、gzip、静态缓存等 Caddy 自动处理，零配置。
- 防火墙只开 80/443；8000 仅监听 `127.0.0.1`，不对公网暴露。

> 若没有域名，可用 `curl -L https://caddyserver.com` 部署并配 `https://你的IP`（自签或无证书提示，体验弱一些）。有域名是最省心路径。

## 四、部署后的安全核对

1. **`SECRET_KEY` 已设置**（否则 API Key 明文落库）。
2. **`CORS_ORIGINS` 留空**或仅含你的域名（默认最严，禁止跨域）。
3. 后端只监听 `127.0.0.1:8000`，由 Caddy/nginx 转发；防火墙只开 80/443。
4. 前端 `dist` 构建产物即时生效，无需额外构建服务。

## 五、运维要点

- **备份**：整个系统数据在 `backend/data/app.db`（故事、用户、会话、每用户模型配置）。定期备份该文件即可；`chroma/` 是内置真实知识库，可一并备份。
- **升级**：改完代码后重新 `npm run build` 前端 + 重启后端即可；SQLite 列迁移自动执行。
- **扩容上限**：单进程 + SQLite 面向小规模（数十到数百用户）足够。若并发明显见顶，再考虑换 Postgres 或多副本 + 共享存储，现阶段不建议提前上。

## 六、本地开发不受影响

- 本地跑：`uvicorn app.main:app --reload` + `npm run dev`，前端经 Vite proxy 走同源 `/v1`，无需 CORS。
- 本地测试：`pytest` 会自动注入测试用户（`tests/conftest.py` + `tests/test_auth.py`），全量用例已覆盖多用户隔离。