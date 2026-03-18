# PIAP 智能产品检测 Agent 平台

## 目录结构
- `backend/` 后端服务（FastAPI/LangGraph）
- `frontend/` 前端应用（Vue 3/Pinia/Vite）
- `docker-compose.yml` 本地依赖服务（MySQL/Redis/RabbitMQ/MinIO/Qdrant）
- `Makefile` 常用命令

## 快速开始
1. 启动本地依赖
   - `make dev-up`
2. 配置后端环境变量
   - `cp backend/.env.example backend/.env`
3. 安装后端依赖
   - `pip install -r backend/requirements.txt`
4. 运行后端
   - `make backend-run`
5. 运行前端
   - `make frontend-dev`

## 文档
- `PIAP_SDD_v1.0.0.docx`
- `PIAP_SYS_002_MySQL.docx`
- `PIAP_BAD_003_Architecture.docx`
- `PIAP_FED_004_Frontend.docx`

## 备注
- 如需调整端口或依赖服务，修改 `docker-compose.yml`
