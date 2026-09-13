# WORKTREE_STATUS

## 当前状态

- 更新时间：2026-09-01
- 分支：`zl2`
- 工作区：共享集成工作区，当前包含会议室知识空间、共享记忆治理和算法工作台改造
- 数据库迁移：`0097_normalize_deleted_transfer_statuses`（当前 head）

## 已验证

- 会议室 / 记忆 / QDL 专项后端测试：151/151 通过
- 数据接入 / 算法工作台专项后端测试：62/62 通过
- 前端全量单测：97/97 通过
- 前端 TypeScript 类型检查：通过
- 前端 ESLint：通过
- 前端生产构建：通过
- Docker Compose 依赖服务：运行中
- 后端全量回归：1036/1036 通过（1 个现有 FastAPI/httpx 弃用警告）
- QDL 工作台 E2E：通过（真实 API + UI，1440/375 视口）
- 会议室 UI E2E：通过（真实 API + UI，Agent 交互部分含浏览器模拟，1440/1024/375 视口）
- Pipeline 入口门禁：已禁止新建/选择未实现的 `pipeline`，历史配置会返回 `AGENT_ADAPTER_UNAVAILABLE`
- 基础设施状态：租户 API 已聚合 MySQL、Redis、Qdrant、对象存储、Chat Model、Embedding、Neo4j、Celery

## 已实现但仍需真实环境验收

- 会议室公共消息、私聊、实时流、权限和消息分页
- 会议 Agent 查询、主动参与、回答共享和取消
- 业务上下文、数据域边界、敏感信息隔离
- 记忆提取、确认、驳回、争议、版本和共享审批
- 冲突检测、冲突事件处理和会议待办
- QDL v2 结构、来源追溯和治理状态
- 数据集分片上传、知识图谱 MVP、对齐、增强和 VLM-JSON 导出 API

## 当前阻塞 / 风险

1. 本机没有可访问的本地模型：宿主机 `127.0.0.1:11434` 拒绝连接，容器访问 `host.docker.internal:11434` 不可达。因此真实模型驱动的会议闭环 E2E 尚未执行。
2. 现有会议 E2E 的 Agent 推理和回答共享部分使用浏览器路由模拟，只能证明交互和权限展示，不能替代真实模型验收。
3. `backend/agent/adapters/pipeline_adapter.py` 仍是预留空壳；入口已禁用，后续需接入统一 `AgentManager/ManagerLoop` 后再启用。
4. 真实聊天模型和 Embedding 服务仍未在当前环境完成可访问性验收。
5. 工作区仍有大量未提交修改和新增文件，尚未形成 release candidate 提交。

## 下一步

1. 在具备模型和 Embedding 服务的环境执行无模拟会议知识闭环 E2E。
2. 将 meeting 反馈接入质量分析，并补充知识隧道的域间映射与转换审计。
3. 硬化 RAG、Qdrant、Celery、MinIO 的生产降级策略。
4. 清理临时文件、更新发布文档、整理提交并建立 release candidate。

## 回归命令

```bash
cd backend && pytest tests -q -p no:cacheprovider
cd frontend && npm run test -- --run
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
```
