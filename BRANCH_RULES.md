# Git Branch Rules

## 结论

可以。

推荐做法是：

- 保留当前分支作为长期开发分支
- 新建一个相对稳定的正式部署分支
- 日常功能、缺陷修复、实验任务都从开发分支继续切短期分支
- 并行开发时优先使用 `git worktree`，不要在同一个工作目录频繁切分支

## 推荐分支模型

最小可行模型：

- `main`
  - 正式部署分支
  - 只接收已经验证通过的版本
- `develop`
  - 日常开发主分支
  - 作为功能分支的基线
- `feature/*`
  - 新功能
- `fix/*`
  - Bug 修复
- `hotfix/*`
  - 线上紧急修复
- `chore/*`
  - 非业务代码整理、配置、脚本

如果你现在所在分支已经承担“开发主线”角色，就直接把它视为 `develop` 即可，不必强行重命名。

## 推荐发布流

1. 日常开发进入 `develop`
2. 需要正式部署时，从 `develop` 合并到 `main`
3. 在 `main` 打 tag
4. 部署只基于 `main` 或 tag

不要把“部署环境修改”长期直接做在 `main` 上。
正确做法是：

- 部署相关改动仍从 `develop` 或 `chore/deploy-*` 分支开发
- 验证通过后再合入 `main`

## 多分支并行开发规则

并行处理任务时，建议一任务一分支，一分支一工作目录。

命名建议：

- `feature/analytics-drilldown`
- `feature/vision-detector-adapter`
- `fix/task-list-sort-memory`
- `chore/nginx-prod-deploy`

并行开发规则：

- 一个分支只处理一个明确主题
- 不要在同一分支混入无关修改
- 分支合并前必须 rebase 或 merge 最新 `develop`
- 每个分支提交前至少做对应模块的最小验证
- 避免多个分支同时修改同一核心文件

高冲突文件要尽量串行处理，例如：

- `backend/app/core/config.py`
- `frontend/src/router/index.ts`
- `docker-compose.yml`
- `task.md`

## 推荐工作方式：git worktree

不要在一个目录里来回 `checkout` 多个分支。

推荐：

```bash
git worktree add ../piap-feature-analytics -b feature/analytics-drilldown develop
git worktree add ../piap-feature-vision -b feature/vision-detector-adapter develop
git worktree add ../piap-fix-sorting -b fix/task-list-sort-memory develop
```

这样每个任务一个独立目录，适合并行开发、并行测试、并行 Agent 协作。

## Agent / 自动化协作规则

如果你要在开发分支上并行跑多个 Agent，建议遵守：

- 每个 Agent 只拥有一个分支
- 每个 Agent 只负责一个明确模块
- 不同 Agent 尽量不要同时改同一文件
- 合并顺序优先：
  - schema / migration
  - backend service / api
  - frontend store / api
  - frontend view

推荐责任划分：

- Worker A：后端 API / Service / Repository
- Worker B：前端页面 / Store / 路由
- Worker C：部署 / 文档 / 配置

## 合并前检查

合并到 `develop` 前至少执行：

```bash
cd backend && PYTHONPATH=. pytest -q
cd frontend && npm run typecheck
cd frontend && npm run build
```

合并到 `main` 前至少确认：

- 数据库迁移可执行
- 部署配置已同步
- `task.md` 已更新
- 当前版本可回滚

## 不建议的做法

- 把 `main` 当开发分支长期直接提交
- 多个功能共用一个 feature 分支
- 在同一工作目录切来切去做并行任务
- 未验证就把迁移直接合到部署分支
- 让 Agent 在脏工作区上随意继续开发

## 当前项目建议

按你现在的项目状态，建议直接采用：

- `main`：正式部署
- `develop`：日常开发
- `feature/*`：新功能
- `fix/*`：缺陷修复
- `chore/*`：部署、脚本、文档

## 当前仓库基线说明

当前仓库已按以下方式收口：

- `main`
  - 保留为正式部署分支
- `develop`
  - 已创建
  - 当前作为日常开发主分支
- `feature/ljc`
  - 当前与 `develop` 指向同一提交
  - 视为历史开发主线别名
  - 不再建议继续承载新的长期开发任务

当前基线提交：

- `77908fbe` `准备使用并行开发`

建议：

- 后续新的功能开发统一从 `develop` 切出
- `feature/ljc` 暂时保留，作为迁移过渡和回退参考
- 在 `develop` 推送远端并稳定使用一段时间后，再考虑是否废弃 `feature/ljc`

## 三端分支命名约束

为对齐 `docs/project_docx/PIAP_INT_008_three_workspace_collab_spec_v1_0_0.docx`，后续分支命名统一按以下前缀：

- `feature/a-*`
- `feature/b-*`
- `feature/c-*`
- `feature/shared-*`

含义：

- `a-*`
  - A 端业务工作台
- `b-*`
  - B 端运营工作台
- `c-*`
  - C 端治理工作台
- `shared-*`
  - 共享认证、路由、workspace、公共契约、共享组件、共享数据结构

当前冻结的共享契约见：

- `docs/AGENT_OPERATOR_WORKSPACE_CONTRACT.md`

## 基线提交建议

如果要把当前仓库正式收口为新的开发基线，建议提交内容只包含“分支协作规则与部署辅助文件”，不要夹带业务功能修改。

建议基线提交范围：

- `BRANCH_RULES.md`
- `README.md`
- `scripts/create_parallel_branch.sh`
- `deploy/nginx/piap.conf`
- `deploy/PUBLIC_RELEASE_MINIMUM.md`
- `frontend/.env.production.example`
- `backend/.env.production.example`

建议提交信息：

```bash
git add BRANCH_RULES.md README.md scripts/create_parallel_branch.sh deploy/nginx/piap.conf deploy/PUBLIC_RELEASE_MINIMUM.md frontend/.env.production.example backend/.env.production.example
git commit -m "chore: establish develop baseline and deployment workflow"
```

如果你希望把最近一轮配置一致性修复也一起作为基线提交，可以额外包含：

- `backend/app/core/config.py`

对应提交信息建议：

```bash
git add BRANCH_RULES.md README.md scripts/create_parallel_branch.sh deploy/nginx/piap.conf deploy/PUBLIC_RELEASE_MINIMUM.md frontend/.env.production.example backend/.env.production.example backend/app/core/config.py
git commit -m "chore: establish develop baseline and align deployment defaults"
```

## develop 推送建议

当你确认基线提交完成后，再执行：

```bash
git push -u origin develop
```

此时不要立即删除远端 `feature/ljc`。
建议等以下条件满足后再决定是否清理：

- `develop` 已稳定使用
- 至少有一轮功能分支从 `develop` 正常创建、合并
- 正式部署流程已切换到 `main <- develop`
