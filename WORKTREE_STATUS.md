# WORKTREE_STATUS

## Branch
- `feature/c-gpu-metrics`

## Last Updated
- `2026-03-24`

## Owner
- `C-side governance / gpu`

## Worktree Path
- `/home/lijjsir/program/piap-feature-gpu-metrics`

## Base Branch
- `develop`

## Merge Target
- `develop`


## Test Command
- `cd backend && pytest tests -q -p no:cacheprovider`
- `cd frontend && npm run typecheck`

## Role
- C 端治理工作台 GPU 指标分支

## Goal
- 补齐 GPU 监控真实后端指标源
- 打通治理页 GPU 数据展示

## Done
- 已建立独立 worktree
- 已完成分支重命名与 ownership 归类

## Pending
- 指标采集接口
- 指标持久化或实时查询方案
- 前端 GPU 页面接真数据

## Sensitive Files
- `backend/app/api/v1/*gpu*`
- `backend/app/services/*gpu*`
- `frontend/src/views/admin/GpuMonitorView.vue`
- `task.md`

## Merge Notes
- 不要顺手改认证和任务主链路
