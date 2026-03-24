# WORKTREE_STATUS

## Branch
- `feature/c-defect-detection-engine`

## Last Updated
- `2026-03-24`

## Owner
- `C-side governance / defect detection`

## Worktree Path
- `/home/lijjsir/program/piap-feature-defect-detection`

## Base Branch
- `develop`

## Merge Target
- `develop`


## Test Command
- `cd backend && pytest tests -q -p no:cacheprovider`
- `cd frontend && npm run typecheck`
- `cd backend && PYTHONPATH=. alembic upgrade head`

## Role
- C 端缺陷识别检测与标准判定主分支

## Goal
- 将缺陷检测从“仅模型粗判”推进到“检测标准 + AI 门禁 + 结构化缺陷输出”闭环
- 持续接入专用视觉检测能力
- 落地 `agent_operator + workspace claims` 到真实前后端代码

## Done
- 已查看并吸收 `PIAP009` 的核心约束
- 已新增 `agent_operator` 到后端权限矩阵与前端角色常量
- 已落地统一 claims 解析与生成：
  - `roles`
  - `plan_tier`
  - `capabilities`
  - `workspaces`
  - `default_workspace`
- 登录/注册/鉴权依赖已兼容多角色 claims
- 前端 `auth.store / usePermission / router / AppLayout` 已兼容多角色与 workspace
- 已新增标准模型与服务：
  - `inspection_specs`
  - `inspection_spec_items`
  - `InspectionStandardService`
- 已新增迁移：`0008_inspection_specs`
- 已接入主流水线：
  - `inspection_pipeline_service` 现在会执行标准判定与 AI gate
- 已满足 `QS-009` 的基线要求：
  - 无有效标准不自动 `PASS`
  - 命中拒收规则可直接 `FAIL`
- `task.md` 已同步更新

## Pending
- 执行本地 Alembic 迁移 `0008_inspection_specs`
- 增加 `inspection_specs` 的 CRUD API
- 增加治理前端的标准配置页
- 扩展更细粒度规则：区域、数量、聚合判定、人工复核策略
- 继续接入专用工业视觉检测服务，减少对多模态 LLM 的依赖
- 将 workspace shell 真正拆分到 `/app /ops /governance`

## Validation
- 后端测试：`19 passed`
- 前端 `npm run typecheck`：通过
- 前端 `vitest/build`：当前环境受 Vite 临时文件写入的只读限制影响，未在本沙箱内跑通

## Sensitive Files
- `backend/app/services/inspection_pipeline_service.py`
- `backend/app/api/v1/auth.py`
- `backend/app/api/v1/deps.py`
- `backend/app/core/permissions.py`
- `backend/app/core/claims.py`
- `frontend/src/stores/auth.store.ts`
- `frontend/src/router/index.ts`
- `frontend/src/layouts/AppLayout.vue`
- `task.md`

## Merge Notes
- 合并前先执行迁移并回归检测结果判定
- 与 `feature/shared-user-management` 合并时重点检查 auth claims 相关冲突
- 与 `feature/c-model-governance-runtime` 合并时重点检查 `inspection_pipeline_service.py`
