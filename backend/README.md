# PIAP Backend

## 运行前准备
- Python 3.11+
- MySQL 8.0+
- Redis 6+
- 任选：RabbitMQ / MinIO / 向量数据库（本项目默认提供 docker-compose）

## 依赖安装
- 使用 requirements：`pip install -r requirements.txt`
- 使用 uv（可选）：`uv pip install -r requirements.txt`

## 本地开发
1. 复制环境变量模板
   - `cp .env.example .env`
2. 运行服务
   - `python main.py`

## 迁移
- 生成迁移：`alembic revision --autogenerate -m "init"`
- 执行迁移：`alembic upgrade head`

## 说明
- 主入口在 `backend/main.py`
- 配置文件集中在 `backend/app/core/config`（如已存在）
