# 本地质量监督隔离演示环境

当前完成阶段一的独立环境，并完善阶段二的资料接入和对象关联。
阶段二的接口、去重边界和验收命令见 [PHASE2.md](PHASE2.md)。不把模拟资料当作真实市场事件、检测报告或已确认风险。
阶段顺序与验收门槛见 [PLAN.md](PLAN.md)。

## 启动与访问

在项目根目录执行：

```powershell
python deploy/quality-demo/manage.py up
```

需要 Docker Desktop 和本机开发镜像 `agent_project-backend:latest`、
`agent_project-frontend:latest`，以及已缓存的 `mysql:8.0`、`redis:7`。
缺少开发镜像时可先运行 `docker compose build backend frontend`，然后启动演示项目。

- 页面：<http://127.0.0.1:15174>
- API：<http://127.0.0.1:18010/docs>
- 组织：`piap-quality-demo`
- 账号：`demo_admin`、`demo_analyst`、`demo_reviewer`；密码自动生成，见本地 `.codex_tmp/piap_quality_demo/accounts.json`。

初始化生成独立的 `.env.quality-demo` 和 JWT 密钥，不读取或覆盖正常开发 `.env`。
数据库名固定为 `piap_quality_demo`，专用数据库用户没有原业务库权限。
MySQL、Redis 不向宿主机开放端口；Redis、文件卷和网络属于 `piap-quality-demo` 项目。
正常开发的 `8000`、`5173` 等服务保持原有运行方式。

## 重复初始化与验收

```powershell
python deploy/quality-demo/manage.py seed
python deploy/quality-demo/verify.py
python frontend/tests/quality_demo_live_browser.py
```

重复初始化保留账号密码、案例 ID、资料、已有版本和人工操作。账号身份冲突时会停止，
不会自动重置角色或密码。初始化仅创建模拟资料与草稿，不调用真实模型、不代替专家复核。

验收结果与截图写入 `.codex_tmp/piap_quality_demo/`；账号文件不应提交或分享。
登录页和业务页的“演示环境”标识来自后端 `/api/v1/runtime-context`，不能用前端参数开启。
演示环境上传的资料由后端强制标记为 `synthetic`，目前禁止确认正式风险；后续阶段另建演示复核状态。

初次建库从当前 ORM 创建隔离模式的完整表结构，时间字段按 MySQL 毫秒精度创建；
不导入历史迁移中的业务种子数据，不运行针对现有业务库的升级或清理。
库内保存专用所有权标记，遇到没有标记的非空数据库会拒绝初始化。

## 状态与停止

阶段三的模拟时间序列使用独立命令 `python deploy/quality-demo/manage.py seed-market`，
不会通过基础 `seed` 自动扩展。监测规则、接口与验收方式见 [PHASE3.md](PHASE3.md)。

阶段四第一步已支持专家人工演示草稿的保存、提交、独立复核和补证重评，使用独立演示状态。
操作、边界及两账号验收命令见 [PHASE4A.md](PHASE4A.md)。

阶段四第二步已接通同单位协同：固定研判版本，复用受限会议和协同请求，公开意见返回原事项。
协同验收命令见 [PHASE4B.md](PHASE4B.md)。阶段四第三步已完成独立演示抽查候选、建议保存与固定、来源版本追溯及依据变化重评。
阶段四验收命令见 [PHASE4C.md](PHASE4C.md)。阶段五已完成可选实验室验证、原事项补证重评、独立研判报告 PDF/Word 和六模块导航。
当前状态与复验顺序见 [PHASE5.md](PHASE5.md)，真实数据/模型/正式发布的未验证项目见 [REMAINING_VALIDATION.md](REMAINING_VALIDATION.md)。

2026-10-18 全流程二次检查的缺陷修复、当前断点和改进优先级见 [SECOND_AUDIT.md](SECOND_AUDIT.md)。演示监控省略日期时固定使用初始化统计日，页面明确显示；正式环境仍使用北京时间当前日。

二次复查后的正式研判下游、建议进入计划、正式独立报告与真实模型连通性修复见 [REPAIR_2026-10-18.md](REPAIR_2026-10-18.md)。真实任务自动回流、规模压测与真实手机验收仍待继续。

```powershell
python deploy/quality-demo/manage.py status
python deploy/quality-demo/manage.py stop
```

停止只作用于演示项目，保留专用数据卷。后续更新表结构需增加明确的演示库升级步骤，
现有初始化不会自动改写已存在的列，也不会运行历史迁移种子。

已复核检测结果的显式回流、新版自动引用、引用撤回，以及专家目录菜单整理见 [RESULT_RETURN.md](RESULT_RETURN.md)。
