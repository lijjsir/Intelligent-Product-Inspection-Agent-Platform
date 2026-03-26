# PIAP 公网发布最小方案

## 1. 当前局域网可访问性判断

当前主机监听情况：

- 后端：`0.0.0.0:8000`
- 前端开发服务：`*:5173`
- RabbitMQ 管理台：`*:15672`
- Qdrant：`*:6333`
- MinIO API：`*:19000`
- MinIO Console：`*:19001`

当前主机 IP：

- `172.30.47.9`

因此在同一局域网或同一可达网段内，如果防火墙没有拦截，理论上可访问：

- `http://172.30.47.9:5173`
- `http://172.30.47.9:8000/docs`

注意：

- `5173` 是 Vite 开发服务器，只适合开发联调，不建议直接暴露到公网
- `3306` 和 `16379` 当前只绑定到 `127.0.0.1`，外部不能直接连 MySQL / Redis
- 如果你运行在 WSL，Windows 防火墙、WSL 端口转发和宿主网络策略仍可能阻断访问

## 2. 生产发布推荐拓扑

推荐对外只开放：

- `80`
- `443`

Nginx 负责：

- 托管前端 `dist`
- 反向代理后端 `/api`
- 统一做 HTTPS、压缩、静态缓存、访问日志

后端只监听本机：

- `127.0.0.1:8000`

数据库和中间件尽量只保留本机或内网访问：

- MySQL：`127.0.0.1:3306`
- Redis：`127.0.0.1:16379`
- RabbitMQ / Qdrant / MinIO 仅在明确需要时开放

## 3. 已提供的部署文件

- Nginx 站点配置：
  - `deploy/nginx/piap.conf`
- 前端生产环境示例：
  - `frontend/.env.production.example`
- 后端生产环境示例：
  - `backend/.env.production.example`

## 4. 最小上线步骤

### 前端

```bash
cd frontend

# 1) 复制生产环境变量模板
cp .env.production.example .env.production

# 2) 安装依赖
npm install

# 3) 构建生产静态资源
npm run build
```

将构建产物部署到：

- `/var/www/piap/frontend/dist`

### 后端

```bash
cd backend

# 1) 复制生产环境变量模板
cp .env.production.example .env

# 2) 执行数据库迁移
PYTHONPATH=. alembic upgrade head

# 3) 启动后端服务（开发方式）
python main.py
```

生产环境建议不要直接 `python main.py`，而是改成：

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

### Nginx

将 `deploy/nginx/piap.conf` 放到：

- `/etc/nginx/sites-available/piap.conf`

```bash
# 1) 建立站点启用链接
sudo ln -s /etc/nginx/sites-available/piap.conf /etc/nginx/sites-enabled/piap.conf

# 2) 检查 Nginx 配置
sudo nginx -t

# 3) 重载 Nginx
sudo systemctl reload nginx
```

## 5. 最小安全要求

公网发布至少做到这些：

1. 只开放 `80/443`，不要把 `5173/8000/15672/6333/19000/19001` 直接暴露公网
2. 开启 HTTPS，至少使用 Let's Encrypt
3. 替换默认密钥与口令
   - JWT 私钥 / 公钥
   - `PIAP_GOVERNANCE_SECRET`
   - MySQL / Redis / RabbitMQ / MinIO 默认密码
4. 关闭调试模式
   - `PIAP_APP_ENV=prod`
5. 给 Nginx 配置请求体大小限制、超时、访问日志
6. RabbitMQ 管理台、MinIO Console、Qdrant 管理接口不要直接公网开放
7. 对 `/docs` 做访问控制，生产环境最好只内网可见

## 6. 当前项目里需要你特别注意的点

1. 你现在看到的 `5173` 只是开发服务，不是正式前端部署方式
2. 后端默认配置已经调整为与当前 `docker-compose.yml` 一致：
   - Redis：`16379`
   - MinIO：`19000`
   - MySQL：`3306`
3. 如果要做公网发布，建议再补：
   - systemd 服务文件
   - HTTPS 证书自动续签
   - 后端进程守护
   - 访问日志与错误日志归档
