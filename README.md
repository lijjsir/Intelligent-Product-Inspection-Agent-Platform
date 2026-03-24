# PIAP 智能产品检测 Agent 平台 (Intelligent Product Inspection Agent Platform)

PIAP 是一个基于前沿大语言模型与多智能体（Multi-Agent）技术的产品缺陷智能检测及审核平台。利用大视觉语言模型（Vision LLMs）和检索增强生成（RAG），该平台能够自主加载产品规格说明书，智能化分析产线摄取的图像，并给出一站式的质量检测报告、风险评级和稳定性溯源分析。

---

## 🏗系统架构与技术栈

### Backend (后端)
- **Web 框架**: FastAPI + Uvicorn 
- **数据库组件**: SQLAlchemy 2 (Alembic) + aiomysql
- **AI 智能体引擎**: LangChain + LangGraph
- **异步任务流**: Celery + RabbitMQ
- **对象存储与向量**: MinIO 存储图像，Qdrant 处理 RAG 规格说明相似度检测
- **认证防护**: PyJWT + Argon2 密码散列加密，以及严格的多租户（Tenant）权限隔离

### Frontend (前端)
- **核心框架**: Vue 3 (Composition API) + Vite + TypeScript
- **状态管理与路由**: Pinia + Vue Router
- **UI 和图表组件**: Element Plus + ECharts (趋势图、雷达图、聚合表盘)
- **交互特性**: 长连接 SSE 接口实时呈现检测进度、业务图谱数据实时过滤

---

## 📂 核心目录与功能分布

```text
.
├── backend/
│   ├── agent/            # AI Agent 智能体核心决策树与 LangGraph DAG 节点定义
│   │   ├── graph/        # Agent 图结构定义与 State 声明
│   │   ├── llm/          # Ollama 等底层大模型驱动封装
│   │   ├── rag/          # Qdrant 知识库向量索引、检索工具
│   │   └── tools/        # 外部供大模型调用的确权执行器（Execution Tools）
│   ├── app/
│   │   ├── api/          # FastAPI 基础 REST 路由实现（分模块）
│   │   ├── core/         # 全局配置、认证拦截器、中间件以及全局 Exception 定义
│   │   ├── models/       # ORM SQLAlchemy 表结构申明
│   │   ├── repositories/ # 强隔离的增删改查底层 Dao（Repository 模式）
│   │   ├── schemas/      # Pydantic Req/Res 类型约定（输入输出格式化）
│   │   └── services/     # 复杂多逻辑抽象（Service 模式）处理纯业务逻辑
│   ├── migrations/       # Alembic 数据库迁移同步链表
│   └── worker/           # Celery 异步任务定义（处理繁重推理流程）
│
├── frontend/
│   ├── src/
│   │   ├── api/          # Axios HTTP / SSE 双向长数据拦截与封装
│   │   ├── components/   # Element Plus 交互组件（如通用 Header、弹窗、看板）
│   │   ├── composables/  # Hooks（例如 usePagination、useEcharts、useSSE）
│   │   ├── router/       # 前端统一拦截守卫及页面路由
│   │   ├── stores/       # Pinia 各模块状态下发（乐观更新存储）
│   │   ├── types/        # 前后端严格拉平绑定的 TypeScript 类型约束
│   │   └── views/        # 各业务域专属 Vue 面板视图 (列表页、聚合页、详情页)
│   └── vite.config.ts    # 前端代理与构建配置文件
│
└── docker-compose.yml    # 项目内外部独立中间件组件群（提供 MySQL、Redis、Queue、S3、Ollama 等启动编排）
```

---

## 🚀 快速启动指南

### 1. 启动周边组件生态

系统需要借助 Docker 提供必要的存储驱动支持。
打开终端，在项目根目录下利用 Makefile 拉起依赖：
```bash
make dev-up
# 或是直接使用: docker-compose up -d
```
> **涵盖的服务**：MySQL(13306), Redis(6379), RabbitMQ(5672/15672), MinIO(9000/9001), Qdrant(6333) 和 Ollama(11434)。

### 2. 后端部署与应用数据初始化

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 配置基础环境（注意替换/使用根目录配置好的证书口令）
cp .env.example .env

# 执行数据库关系迁移与映射热身
alembic upgrade head

# 拉起主控 API 服务（默认监听 127.0.0.1:8000）
python main.py
```

### 3. 前端交互挂载

后端启动后，请新开一个 Terminal，执行：
```bash
cd frontend
npm install
npm run dev
```

通过访问 `http://localhost:5173` 即可进入本平台（具备 Vite 级联反向代理 `/api` 转发）。如果首次访问，你可以先进入注册页面获取组织身份与 Admin 用户权益。

---

## 🔌 专用视觉服务接入

如果需要把外部目标检测 / AOI / CV 服务接入到 PIAP 的视觉节点，可参考：

- [backend/docs/vision_detector_protocol.md](backend/docs/vision_detector_protocol.md)

当前视觉链路优先级为：
- 配置了 `PIAP_VISION_DETECTOR_URL` 时，先调用专用视觉检测服务
- 若专用服务不可用或返回空结果，则回退到火山多模态大模型
- 若仍无法产出有效结构化缺陷框，则使用项目内可变兜底输出

---

## 🚢 生产部署参考

已补充最小生产部署文件与公网发布说明：

- [deploy/nginx/piap.conf](deploy/nginx/piap.conf)
- [deploy/PUBLIC_RELEASE_MINIMUM.md](deploy/PUBLIC_RELEASE_MINIMUM.md)
- [frontend/.env.production.example](frontend/.env.production.example)
- [backend/.env.production.example](backend/.env.production.example)

---

## 🌿 Git 分支协作

已补充当前项目的分支与并行开发规则：

- [BRANCH_RULES.md](BRANCH_RULES.md)
- [scripts/create_parallel_branch.sh](scripts/create_parallel_branch.sh)

---

## 💡 开发参考与技能接入说明

后续所有对于本平台 API、组件或后台逻辑的追加，请必须完全遵循 `~/.agents/skills/backend/SKILL.md` 与 `~/.agents/skills/frontend/SKILL.md` 中严格约定的项目代码模式与错误封装协议（如后端使用 `ResponseEnvelope` 进行数据出口封装；前端使用组合式 API 和 `usePermission` 函数隔离路由权限）。详细设计参考根目录下的多份设计源文档（如 `PIAP_SDD_v1.0.0.docx`）。
