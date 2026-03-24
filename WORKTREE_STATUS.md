# WORKTREE_STATUS

## Branch
- `feature/ljc`

## Last Updated
- `2026-03-24`

## Owner
- `shared / integration`

## Worktree Path
- `/home/lijjsir/program/Intelligent-Product-Inspection-Agent-Platform`

## Base Branch
- `develop` 基线整理区

## Merge Target
- `develop`


## Test Command
- `cd backend && pytest tests -q -p no:cacheprovider`
- `cd frontend && npm run typecheck`

## Role
- 历史开发主线工作区
- 当前用于基线整理、共享文档、集成规划

## Goal
- 不直接承担新的长期功能开发
- 用于维护共享规则、文档、分支协作规范

## Done
- 已建立 `develop/main` 分支结构
- 已建立 worktree 并行协作方式
- 已冻结 `agent_operator + workspace claims` contract
- 已建立 `branch ownership + merge checklist`

## Pending
- 将 `develop` 专用集成工作区单独落地
- 持续维护共享文档与集成规范

## Sensitive Files
- `BRANCH_RULES.md`
- `BRANCH_OWNERSHIP_AND_MERGE_CHECKLIST.md`
- `task.md`
- `README.md`

## Merge Notes
- 该工作区的改动优先走 `develop`
- 只做共享规则、文档、集成说明，不承接大功能开发
