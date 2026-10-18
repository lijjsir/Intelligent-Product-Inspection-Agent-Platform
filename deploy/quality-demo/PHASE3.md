# 阶段三：市场监控

本阶段补齐市场概览、异常监测、重点对象，以及数量线索到研判事项的引用关系。运行与验收仅在本地隔离演示库中进行。

## 本地查看

```powershell
python deploy/quality-demo/manage.py up
python deploy/quality-demo/manage.py seed-market
python deploy/quality-demo/verify_phase3.py
python frontend/tests/market_monitoring_stage3_live_browser.py
```

使用 `demo_analyst` 或 `demo_reviewer` 登录 <http://127.0.0.1:15174>，打开“质量监督 → 市场监控”。账号密码仍保存在本机 `.codex_tmp/piap_quality_demo/accounts.json`。

演示资料首次初始化的截止日为 **2026-10-17**，可以打开：
<http://127.0.0.1:15174/app/quality-analytics?as_of=2026-10-17>。
新环境以首次基础初始化保存的北京时间日期为准；实际日期见 `phase3-api-acceptance.json` 的 `as_of`。
默认留空使用北京时间今天。演示时间序列不会随重复初始化滚动或改写，隔天验收应选用保存的截止日。

`seed-market` 额外创建 11 条明确标注模拟的资料，包含正常基数、增长、零基数、未知时间和未确认对象。原基础案例、原文、附件、账号、历史版本及人工关联不会重置。原文片段按现有机制登记为 synthetic 证据，补齐缺失片段不会替代专家研判或复核。

## 统计口径

- 最近两个完整七日窗口，时区固定 `Asia/Shanghai`。截止日为当天 00:00，本期 `[截止日−7日, 截止日)`，上期再向前七日。边界统一转为 UTC 后查询。
- 投诉、舆情分别计数；产品与企业分开观察。只按本组织仍有效的档案 ID 分组，兼容旧企业引用 `enterprise_ref.id`，不会通过原文名称猜测身份。
- 默认同时满足：本期不少于 3 条、至少增加 3 条、达到上期 2 倍。上期为零时标记“新增集中线索”，增长百分比为 null。
- 每个参与统计的来源和资料类型必须有覆盖两个窗口的声明。声明不足时显示“无法比较”，不产生可转换线索。只证明所列接入来源的资料覆盖，不代表整个市场覆盖或市场发生率。
- 发生时间未知单列，不以受理时间补齐；对象未确认、档案停用或跨组织引用进入待整理列表；来源撤回或停用的资料单列并退出统计。
- 正式模式仅计 observed，隔离演示模式仅计 synthetic；inferred 不计入上述数量。模式由服务端决定。
- 数量规则不执行模型调用，不产生风险等级、概率或正式风险结论。

规则和覆盖声明由有业务资料读取权限的本组织管理员、专家维护。修改需要依据；规则采用乐观版本校验，陈旧版本返回 409。所有修改保留操作者、时间和前值。

## 线索、事项与重点对象

扫描为达到阈值的线索保存统计窗口、算法与阈值版本、来源 ID、内容及对象指纹和覆盖声明。原快照不被刷新覆盖；资料撤回、对象改绑、迟到资料、规则或声明变化会使旧快照过期。未转换的旧快照返回 409，页面提示重新扫描核对。

转换可以新建事项，也可以选择同一对象、同一演示/正式模式的既有事项。原始资料直接引用，无需再次接入；事项能返回市场线索，线索能打开原文和附件。已有转换映射在重复点击或并发请求时返回同一事项；源资料后续变化仍由研判的证据核验控制。转换不新增研判结论、不执行检测，也不进入正式抽查候选。

单个事项沿用现有 500 条来源上限，超限明确返回业务提示，保留原线索快照；更大规模的汇总与资料范围整理留待真实数据阶段验证。

重点对象为本组织共享关注列表，复用企业或产品档案，不另建主数据；重复添加复用同一条关注，取消关注后保留审计，再次添加仍沿用同一记录。它与抽查候选独立。对象停用后列表明确提示不可用。

## 接口

| 方法与路径（统一 `/api/v1` 前缀） | 用途 |
| --- | --- |
| `GET /market-monitoring?as_of=&object_type=product` | 查询当前统计，不写入快照 |
| `POST /market-monitoring/scan` | 查询并持久化达到阈值的线索 |
| `GET /market-monitoring/signals/{id}` | 原快照、当前有效性及可访问原始资料引用 |
| `POST /market-monitoring/signals/{id}/risk-case` | 幂等创建/关联事项，可传 `target_case_id` |
| `PATCH /market-monitoring/rule` | 带 `expected_version` 和依据更新阈值 |
| `GET /market-monitoring/coverage` | 来源与资料类型的覆盖声明 |
| `PUT /market-monitoring/coverage` | 登记带时区的覆盖起止与核对依据 |
| `GET/POST /market-monitoring/focus-objects` | 查询/添加关注 |
| `POST /market-monitoring/focus-objects/{id}/archive` | 带依据取消关注 |

持久化复用现有 `supervision_records` 的专用 kind：`market-signal`、`market-rule`、`market-coverage`、`market-focus`。组织、kind 和 code 唯一约束、组织行锁以及 MySQL 当前锁定读取共同保证多请求幂等；没有新增复制原文的表，也没有对正常业务库运行迁移。仍保留原路由与“已确认风险与抽查统计”。

## 验收与后续边界

真实接口验收结果：`.codex_tmp/piap_quality_demo/phase3-api-acceptance.json`。
真实浏览器验收结果与截图：同目录 `phase3-browser-acceptance.json`、`phase3-*.png`。测试未模拟接口或真实模型。

阶段四尚未实施：事项和版本关联的同单位协同、两名专家的独立演示复核、`demo_reviewed`、演示抽查建议。阶段五的可选实验室验证和独立研判报告也未实施。真实市场资料、覆盖完整性、模型调用与大规模数据性能仍需单独验收。
