# PIAP Backend

## 运行前准备
- Python 3.10+
- MySQL 8.0+
- Redis 7+
- Qdrant
- 可选：RabbitMQ / MinIO（项目根目录 `docker-compose.yml` 已提供默认编排）

## 依赖安装
- 使用 requirements：`pip install -r requirements.txt`
- 使用 uv（可选）：`uv pip install -r requirements.txt`

## 本地开发
```bash
# 1) 复制环境变量模板
cp .env.example .env

# 2) 执行数据库迁移
PYTHONPATH=. alembic upgrade head

# 3) 运行服务
python main.py
```

默认监听：
- `0.0.0.0:8000`

当前默认本地依赖端口：
- MySQL：`127.0.0.1:3306`
- Redis：`127.0.0.1:16379`
- MinIO API：`http://127.0.0.1:19000`
- MinIO Console：`http://127.0.0.1:19001`
- Qdrant：`http://127.0.0.1:6333`

说明：

- 当前 Celery 默认 broker / result backend 使用 Redis
- `backend/.env.example` 已对齐宿主机本地开发端口
- 任务表字段当前使用 `spec_code`，迁移需执行到 `0010_task_spec_id_to_spec_code`

## 迁移
- 生成迁移：`alembic revision --autogenerate -m "init"`
- 执行迁移：`PYTHONPATH=. alembic upgrade head`

## 说明
- 主入口在 `backend/main.py`
- 配置文件集中在 `backend/app/core/config.py`
- 专用视觉检测服务接入协议见 `backend/docs/vision_detector_protocol.md`
- 当前主模型链路以火山引擎 Ark / OpenAI-compatible 接口为主
