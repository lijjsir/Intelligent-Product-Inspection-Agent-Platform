# PIAP 智能产品检测 Agent 平台

PIAP 是一个面向工业质检场景的全栈 AI Agent 平台。当前项目已经具备以下主链路能力：

- 组织注册、登录、JWT 鉴权、多租户隔离
- 质检任务创建、任务流式状态订阅、结果与稳定性分析
- 检测标准配置与标准门禁判定
- 基于 Vision LLM + RAG 的缺陷识别与推理
- 前端控制台、管理页、分析页与实时 SSE 事件流

## 当前实现说明

当前仓库的实际实现与一些旧文档描述有差异，以下口径以当前代码为准：

- 本地依赖编排文件存在于项目根目录：`docker-compose.yml`
- 本地启动命令应优先使用 `docker compose`，不是旧式 `docker-compose`
- `docker compose` 默认暴露的 MySQL 端口是 `3306`，不是 `13306`
- Celery 当前默认 broker / result backend 都是 Redis；RabbitMQ 容器已提供，但不是默认必需依赖
- RAG 当前主实现使用 Qdrant HTTP API
- 任务字段已经统一为 `spec_code`，数据库迁移需要执行到 `0010_task_spec_id_to_spec_code`
- 前端任务创建页当前使用“检测标准”下拉选择，不再手填旧的 `spec_id`

## 技术栈

### 后端

- FastAPI + Uvicorn
- SQLAlchemy 2 + Alembic + aiomysql
- Celery
- LangGraph
- Qdrant
- Redis
- MySQL 8
- 可选：MinIO、专用视觉检测服务、Langfuse

### 前端

- Vue 3 + Vite + TypeScript
- Pinia
- Vue Router
- Element Plus
- ECharts

## 目录结构

```text
.
├── backend/
│   ├── agent/                 # Agent 图、RAG、LLM、视觉与稳定性分析
│   ├── app/
│   │   ├── api/               # FastAPI 路由
│   │   ├── core/              # 配置、权限、中间件、错误处理
│   │   ├── models/            # ORM 模型
│   │   ├── repositories/      # 数据访问层
│   │   ├── schemas/           # Pydantic Schema
│   │   └── services/          # 业务服务
│   ├── migrations/            # Alembic 迁移
│   ├── scripts/               # 运维/导入脚本
│   ├── tests/                 # 后端测试
│   └── worker/                # Celery worker 与任务
├── frontend/
│   ├── src/
│   │   ├── api/               # HTTP / SSE API 封装
│   │   ├── components/        # 业务与通用组件
│   │   ├── composables/       # 组合式函数
│   │   ├── router/            # 路由
│   │   ├── stores/            # Pinia store
│   │   ├── types/             # TypeScript 类型
│   │   └── views/             # 页面
│   └── tests/                 # 前端测试
├── deploy/
│   ├── nginx/piap.conf        # Nginx 反代示例
│   └── PUBLIC_RELEASE_MINIMUM.md
├── docker-compose.yml         # 本地依赖编排
└── Makefile                   # 常用开发命令
```

## 运行前准备

### 软件要求

- Python `3.10+`
- Node.js `18+`
- npm `9+`
- Docker Engine + Docker Compose Plugin

### 端口占用

本地默认会使用这些端口：

- Backend: `8000`
- Frontend Dev Server: `5173`
- MySQL: `3306`
- Redis: `16379`
- RabbitMQ AMQP: `5672`
- RabbitMQ Console: `15672`
- MinIO API: `19000`
- MinIO Console: `19001`
- Qdrant: `6333`

## 本地开发部署

### 1. 启动中间件

在项目根目录执行：

```bash
docker compose up -d
```

也可以使用 Makefile：

```bash
make dev-up
```

启动后建议先确认容器状态：

```bash
docker compose ps
```

### 2. 配置并启动后端

```bash
cd backend

# 1) 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 2) 安装依赖
pip install -r requirements.txt

# 3) 复制环境变量
cp .env.example .env
```

默认 `backend/.env.example` 已经对齐宿主机本地开发端口，关键值如下：

- `PIAP_DB_URL=mysql+aiomysql://piap:piap@127.0.0.1:3306/piap_main`
- `PIAP_REDIS_URL=redis://127.0.0.1:16379/0`
- `PIAP_CELERY_BROKER_URL=redis://127.0.0.1:16379/0`
- `PIAP_CELERY_RESULT_BACKEND=redis://127.0.0.1:16379/0`
- `PIAP_QDRANT_URL=http://127.0.0.1:6333`
- `PIAP_S3_ENDPOINT=http://127.0.0.1:19000`

然后执行数据库迁移：

```bash
PYTHONPATH=. alembic upgrade head
```

当前任务表字段迁移必须至少包含：

- `0010_task_spec_id_to_spec_code`

再启动后端：

```bash
python main.py
```

或者使用更明确的命令：

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

启动后可检查：

- 健康响应：`http://127.0.0.1:8000/`
- OpenAPI：`http://127.0.0.1:8000/docs`

### 3. 可选：导入标准文档到 Qdrant

如果你希望 RAG 检索立即可用，执行：

```bash
cd backend
source venv/bin/activate
PYTHONPATH=. python scripts/import_standard_docs.py
```

默认会导入：

- `backend/scripts/standard_docs.seed.jsonl`

如果导入失败并提示 embedding 为空，通常是以下配置未正确填写：

- `PIAP_VOLCENGINE_API_KEY`
- `PIAP_VOLCENGINE_EMBED_MODEL`
- `PIAP_VOLCENGINE_BASE_URL`

### 4. 启动前端

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

默认 `frontend/.env.example` 为：

```env
VITE_API_BASE=/api
```

开发模式下 Vite 会把 `/api` 代理到 `http://localhost:8000`。

访问：

- 前端控制台：`http://127.0.0.1:5173`

### 5. 初始化账号

当前项目没有预置管理员种子账号，建议直接走前端注册页或接口注册：

- 前端注册页：`/register`
- 后端接口：`POST /api/v1/auth/register`

注册后会自动创建组织和首个 `org_admin` 用户。

### 6. 可选：启动 Celery Worker

任务执行接口 `backend/app/api/v1/agent.py` 的设计是：

- 如果 Celery worker 可用，任务以 `mode=celery` 异步执行
- 如果 Celery worker 不可用，会自动降级为本地后台任务 `mode=local_background`

因此本地开发可以不启动 worker；如果需要完整验证异步链路，再额外启动：

```bash
cd backend
source venv/bin/activate
PYTHONPATH=. celery -A worker.celery_app.celery_app worker -l info
```

### 7. 停止本地依赖

```bash
docker compose down
```

或：

```bash
make dev-down
```

## 生产部署步骤

以下步骤适用于单机或单 VM 最小可用部署。

### 1. 准备主机

- 安装 Python 3.10+
- 安装 Node.js 18+
- 安装 Nginx
- 安装 MySQL 8、Redis 7、Qdrant
- 可选安装 MinIO
- 如需 Celery 异步执行，保留 Redis 或自行改成 RabbitMQ

推荐只对公网开放：

- `80`
- `443`

内部服务建议仅监听内网或本机：

- Backend: `127.0.0.1:8000`
- MySQL: `127.0.0.1:3306`
- Redis: `127.0.0.1:6379`
- Qdrant: `127.0.0.1:6333`
- MinIO: `127.0.0.1:9000`

### 2. 部署后端

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.production.example .env
```

编辑 `backend/.env.production.example` 对应的生产值，至少确认这些项：

- `PIAP_APP_ENV=prod`
- `PIAP_DB_URL`
- `PIAP_DB_REPLICA_URL`
- `PIAP_REDIS_URL`
- `PIAP_CELERY_BROKER_URL`
- `PIAP_CELERY_RESULT_BACKEND`
- `PIAP_QDRANT_URL`
- `PIAP_QDRANT_COLLECTION`
- `PIAP_JWT_PRIVATE_KEY`
- `PIAP_JWT_PUBLIC_KEY`
- `PIAP_VOLCENGINE_API_KEY`
- `PIAP_VOLCENGINE_MODEL_ID`
- `PIAP_VOLCENGINE_EMBED_MODEL`
- `PIAP_GOVERNANCE_SECRET`

执行迁移：

```bash
PYTHONPATH=. alembic upgrade head
```

启动后端进程：

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

生产环境建议改成 `systemd` 托管，而不是手工常驻。

### 3. 部署前端

```bash
cd frontend
npm install
cp .env.production.example .env.production
npm run build
```

构建产物位于：

- `frontend/dist`

将其发布到：

- `/var/www/piap/frontend/dist`

### 4. 配置 Nginx

项目已提供最小配置：

- `deploy/nginx/piap.conf`

部署步骤：

```bash
sudo cp deploy/nginx/piap.conf /etc/nginx/sites-available/piap.conf
sudo ln -sf /etc/nginx/sites-available/piap.conf /etc/nginx/sites-enabled/piap.conf
sudo nginx -t
sudo systemctl reload nginx
```

当前配置默认：

- 静态目录：`/var/www/piap/frontend/dist`
- `/api/` 反代到 `http://127.0.0.1:8000/api/`
- `/docs` 和 `/openapi.json` 反代到后端

### 5. 可选：启动 Celery Worker

如果生产环境需要独立 worker：

```bash
cd backend
source venv/bin/activate
PYTHONPATH=. celery -A worker.celery_app.celery_app worker -l info
```

同样建议放入 `systemd`。

### 6. 可选：导入标准文档

生产库初始化后，如需启用 RAG 标准检索：

```bash
cd backend
source venv/bin/activate
PYTHONPATH=. python scripts/import_standard_docs.py
```

### 7. 验证部署

按以下顺序检查：

1. `curl http://127.0.0.1:8000/` 返回后端欢迎信息
2. `curl http://127.0.0.1:8000/docs` 返回 Swagger HTML
3. `curl http://127.0.0.1/` 或域名首页可以返回前端页面
4. 浏览器可以打开登录页和注册页
5. 完成一次注册、登录、创建任务、启动任务
6. 任务详情页能收到 SSE 事件
7. 检测标准页可正常拉取 `/api/v1/inspection-specs`

## 常见问题

### `Unknown column 'inspection_tasks.spec_code'`

说明数据库还没执行到最新迁移。进入 `backend/` 执行：

```bash
PYTHONPATH=. alembic upgrade head
```

### `Can't connect to MySQL server on '127.0.0.1'`

先检查：

- MySQL 是否启动
- `PIAP_DB_URL` 是否正确
- Docker 端口是否映射到宿主机

### 前端能打开但 `/api` 失败

检查：

- 后端是否监听 `8000`
- `frontend/.env.local` 或 `frontend/.env.production` 中的 `VITE_API_BASE`
- Nginx 的 `/api/` 反向代理是否生效

### 任务运行返回 `local_background`

这是预期降级行为，表示当前没有可用 Celery worker。要切回异步队列模式，启动 worker 即可。

### RAG 检索为空

检查：

- Qdrant 服务是否启动
- 是否执行过 `python scripts/import_standard_docs.py`
- embedding 模型配置是否有效

## 相关文件

- 视觉检测服务协议：`backend/docs/vision_detector_protocol.md`
- 最小公网发布说明：`deploy/PUBLIC_RELEASE_MINIMUM.md`
- Nginx 示例：`deploy/nginx/piap.conf`
- 后端说明：`backend/README.md`


## 补充文档

- [AI 质量与稳定性指标说明](docs/AI_QUALITY_METRICS.md)
