# WORKTREE_STATUS

## Branch
- `feature/shared-user-management`

## Last Updated
- `2026-03-24`

## Owner
- `shared / user-management`

## Worktree Path
- `/home/lijjsir/program/piap-feature-user-management`

## Base Branch
- `develop`

## Merge Target
- `develop`


## Test Command
- `cd backend && pytest tests -q -p no:cacheprovider`
- `cd frontend && npm run typecheck`

## Role
- 共享用户与权限管理分支

## Goal
- 完善用户管理高级能力
- 持续落地角色分配策略与共享认证约束

## Done
- 已建立独立 worktree
- 已完成分支重命名与 ownership 归类
- 已补齐用户筛选 / 搜索
- 已补齐管理员重置密码入口与个人资料页
- 已接入可分配角色策略接口，并在后端补充自改角色 / 自停用约束

## Pending
- 合并前需复核与其他 auth claims 分支的角色字段兼容性
- 如有需要，可继续补 profile 头像 / MFA / 安全日志等更深层个人安全能力

## Sensitive Files
- `backend/app/api/v1/users.py`
- `backend/app/services/user_service.py`
- `frontend/src/views/UserListView.vue`
- `frontend/src/stores/auth.store.ts`
- `task.md`

## Merge Notes
- 合并前需和所有涉及 auth claims 的分支对齐
