# WORKTREE_STATUS

## Branch
- `feature/c-model-governance-runtime`

## Last Updated
- `2026-03-24`

## Owner
- `C-side governance / model runtime`

## Worktree Path
- `/home/lijjsir/program/piap-feature-model-governance`

## Base Branch
- `develop`

## Merge Target
- `develop`


## Test Command
- `cd backend && pytest tests -q -p no:cacheprovider`
- `cd frontend && npm run typecheck`

## Role
- C 端模型治理运行时分支

## Goal
- 完善模型健康检查、限速窗口、故障切换
- 强化多模型网关运行时治理

## Done
- 已建立独立 worktree
- 已完成分支重命名与 ownership 归类

## Pending
- 真实健康探活
- 自动故障切换
- RPM/TPM 窗口控制

## Sensitive Files
- `backend/agent/llm/gateway.py`
- `backend/agent/llm/model_selector.py`
- `backend/agent/llm/health_checker.py`
- `backend/app/services/model_config_service.py`
- `task.md`

## Merge Notes
- 与缺陷检测分支合并时重点检查 `inspection_pipeline_service.py`
