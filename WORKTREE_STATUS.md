# WORKTREE_STATUS

## Branch
- `develop`

## Last Updated
- `2026-03-24`

## Owner
- `shared / integration`

## Worktree Path
- `/tmp/piap-develop-merge`

## Base Branch
- `main`

## Merge Target
- `main`

## Test Command
- `cd backend && pytest tests -q -p no:cacheprovider`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run build`

## Role
- 集成分支
- 负责合并各功能分支并做回归验证

## Goal
- 集成已完成的功能分支
- 解决共享文件冲突
- 为后续发布到 `main` 做准备

## Done
- 已创建独立 develop 临时 worktree
- 正在合并各功能分支

## Pending
- 完成剩余功能分支合并
- 跑通回归检查
- 推送 develop

## Sensitive Files
- `frontend/src/router/index.ts`
- `frontend/src/layouts/AppLayout.vue`
- `frontend/src/stores/auth.store.ts`
- `backend/app/services/inspection_pipeline_service.py`
- `task.md`

## Merge Notes
- 遇到分支私有状态文件冲突时，保留 develop 版本
- 合并完成后统一回归，不直接跳过共享文件冲突
