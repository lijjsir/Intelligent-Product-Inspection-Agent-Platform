# Branch Ownership And Merge Checklist

## Branch Roles
- `main`
  - 正式部署分支
  - 只接收来自 `develop` 的已验证合并
- `develop`
  - 集成分支
  - 用于合并各功能分支、回归验证、准备发布
- `feature/c-*`
  - C 端治理工作台相关功能
  - 包含 `/admin/*`、`/quality/*`、模型治理、质量追踪、GPU 治理、缺陷标准治理
- `feature/shared-*`
  - 会修改共享认证、路由、布局、公共 store、公共 schema 的分支

## Ownership
- `feature/c-defect-detection-engine`
  - 主责：
    - `backend/agent/vision/`
    - `backend/agent/graph/nodes/vision.py`
    - `backend/app/services/inspection_standard_service.py`
    - `backend/app/models/inspection_spec.py`
    - 检测标准、缺陷判定、AI gate
  - 允许联动：
    - `backend/app/services/inspection_pipeline_service.py`
    - `frontend/src/components/business/result/*`
    - `frontend/src/views/ResultDetailView.vue`

- `feature/c-gpu-metrics`
  - 主责：
    - `backend/app/api/v1/*gpu*`
    - `backend/app/services/*gpu*`
    - `frontend/src/views/admin/GpuMonitorView.vue`
  - 禁止顺手改认证、任务主链路

- `feature/c-model-governance-runtime`
  - 主责：
    - `backend/agent/llm/gateway.py`
    - `backend/agent/llm/model_selector.py`
    - `backend/agent/llm/health_checker.py`
    - `backend/app/services/model_config_service.py`
  - 允许联动：
    - `frontend/src/views/admin/ModelConfigView.vue`

- `feature/shared-user-management`
  - 主责：
    - `backend/app/api/v1/users.py`
    - `backend/app/services/user_service.py`
    - `frontend/src/views/UserListView.vue`
  - 高冲突文件改动前需同步

- `feature/shared-analytics-drilldown`
  - 主责：
    - `backend/app/api/v1/analytics.py`
    - `backend/app/services/analytics_service.py`
    - `backend/app/repositories/analytics_repo.py`
    - `frontend/src/views/AnalyticsView.vue`

## High-Conflict Files
- `frontend/src/router/index.ts`
- `frontend/src/layouts/AppLayout.vue`
- `frontend/src/stores/auth.store.ts`
- `frontend/src/composables/usePermission.ts`
- `backend/app/api/v1/deps.py`
- `backend/app/api/v1/auth.py`
- `backend/app/core/permissions.py`
- `backend/app/core/config.py`
- `backend/app/services/inspection_pipeline_service.py`
- `task.md`

## Merge Order
1. 低冲突、独立性高的分支先合入 `develop`
2. 共享认证/路由相关分支在中后段合并
3. 涉及 `inspection_pipeline_service.py` 的分支最后合并
4. 每次只合一个分支，合完立刻跑验证

## Per-Branch Merge Checklist
- [ ] 当前分支 `git status` 干净
- [ ] 已写或更新本分支 `WORKTREE_STATUS.md`
- [ ] 已说明本分支修改范围与未完成项
- [ ] 后端测试已跑
- [ ] 前端 `typecheck` 已跑
- [ ] 如涉及前端构建，`vite build` 已跑
- [ ] 如涉及迁移，已附 Alembic revision 与执行说明
- [ ] 未顺手修改高冲突文件，或已明确说明原因
- [ ] 已确认不会覆盖其他 worktree 的未合并事实

## Develop Merge Checklist
- [ ] `develop` 先拉到最新基线
- [ ] 逐个合并 feature 分支
- [ ] 每合并一个分支就解决冲突并提交
- [ ] 合并后统一跑：
  - [ ] `pytest`
  - [ ] `npm run typecheck`
  - [ ] `npm run build`
- [ ] 更新 `task.md`
- [ ] 更新共享文档与部署说明

## Main Release Checklist
- [ ] `develop` 已完成一轮集成回归
- [ ] 数据迁移脚本已审查
- [ ] 配置项变更已写入部署文档
- [ ] `main <- develop` 合并前 tag/版本说明已准备
