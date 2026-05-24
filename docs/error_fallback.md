# 异常反馈与报告导出功能设计说明（PM 视角）

> 适用分支：`develop`  
> 适用项目：`Intelligent-Product-Inspection-Agent-Platform`  
> 目标：将“异常反馈”和“报告导出”从基础页面升级为可闭环、可分析、可导出的正式产品能力。  
> 重点：页面不要做成单个超长大页面，而是通过卡片、Tabs、抽屉、弹窗、分步流程、折叠区等方式提升空间利用率和可读性。

---

## 1. 当前功能现状

### 1.1 异常反馈现状

当前系统已经具备基础异常反馈能力：

- `ResultDetailView.vue` 中已经接入 `FeedbackWidget`。
- 用户可以对检测结果进行点赞、点踩、评分、选择分类、填写评论。
- `/app/feedbacks` 已经指向 `FeedbackListView.vue`。
- `FeedbackListView.vue` 当前展示的是“反馈流水”，并支持前端导出 CSV。

当前问题：

1. 页面更像“流水表”，不是“异常处理中心”。
2. 没有状态闭环，例如待处理、处理中、已解决、已关闭。
3. 没有严重程度、处理人、处理意见、处理时间线。
4. 没有详情抽屉，用户需要通过长表或跳转查看信息。
5. 反馈和检测结果、图片缺陷、推理链、Trace 链路之间的关联展示不够明显。
6. CSV 导出在前端完成，适合小数据量，不适合正式报告或大批量数据导出。

### 1.2 报告导出现状

当前 `/app/export` 仍然指向占位页：

```ts
{ 
  path: "export", 
  name: "app-export", 
  component: () => import("@/views/placeholder/PlaceholderPage.vue"), 
  meta: { title: "报告导出", roles: APP_ROLES } 
}
```

菜单中“报告导出”也仍然带有 `placeholder: true`，说明该功能尚未真正产品化。

当前问题：

1. 没有真实报告导出页面。
2. 没有报告类型选择。
3. 没有报告模板。
4. 没有导出格式选择。
5. 没有导出历史。
6. 没有异步生成任务。
7. 没有 PDF、Word、Excel 等正式报告文件。
8. 没有对质量分析、异常反馈、检测结果、证据溯源进行统一导出。

---

## 2. 产品定位

### 2.1 异常反馈的定位

异常反馈不是简单的点赞/点踩，而应该是：

> 用户发现检测结果或 AI 回复存在问题后，提交异常；专家或管理员查看、分派、处理、关闭；系统将这些反馈回灌到质量分析和模型治理中。

也就是说，异常反馈应该承担三个作用：

1. **问题入口**：用户发现问题后快速提交。
2. **处理闭环**：专家/管理员跟进处理。
3. **治理数据源**：反馈数据进入质量报告、模型评估和后续优化。

推荐产品名称：

- 异常反馈中心
- 反馈治理中心
- 质量异常处理中心

### 2.2 报告导出的定位

报告导出不应该只是下载按钮，而应该是：

> 将检测结果、质量分析、异常反馈、证据链路沉淀为可归档、可审阅、可对外交付的正式报告。

报告导出承担三个作用：

1. **结果归档**：单任务、批量任务检测结果导出。
2. **质量复盘**：质量趋势、模型表现、反馈分布导出。
3. **对外交付**：生成 PDF、Word、Excel 等正式文件。

推荐产品名称：

- 报告导出中心
- 检测报告中心
- 质量报告生成中心

---

## 3. 页面设计总原则

为了避免页面内容全部堆在一个大页面里，建议采用以下设计原则。

### 3.1 信息分层展示

不要把所有信息同时展开，而是分成三层：

| 层级 | 展示方式 | 内容 |
|---|---|---|
| 一级信息 | 卡片、表格、状态标签 | 用户最常看的核心信息 |
| 二级信息 | Tabs、展开行、详情抽屉 | 用户点击后才需要看的详情 |
| 三级信息 | 弹窗、JSON 折叠、跳转 Trace | 低频、复杂、技术性信息 |

### 3.2 页面布局建议

不要采用一个完整长页面从上往下堆内容，而应使用：

- 顶部概览卡片
- 左侧筛选面板
- 中间主表格
- 右侧详情抽屉
- 顶部 Tabs 切换不同视角
- 弹窗承载处理动作
- 步骤条承载导出流程
- 折叠面板承载低频配置

### 3.3 推荐交互组件

| 场景 | 推荐组件 |
|---|---|
| 查看统计概览 | 小卡片 |
| 查看列表 | 表格 + 分页 |
| 查看详情 | 右侧抽屉 Drawer |
| 填写反馈 | 弹窗 Dialog 或抽屉 |
| 处理反馈 | 小弹窗 |
| 查看证据链 | Tabs + 折叠面板 |
| 查看 JSON 推理链 | 代码块 + 折叠 |
| 报告配置 | Stepper 分步表单 |
| 报告预览 | 右侧预览面板 |
| 导出历史 | 独立 Tab |
| 高级筛选 | 可折叠筛选区 |

---

# 第一部分：异常反馈功能设计

---

## 4. 异常反馈页面整体结构

推荐路由：

```ts
/app/feedbacks
```

推荐页面：

```text
FeedbackCenterView.vue
```

页面不建议继续叫“反馈流水”，而应改成“异常反馈中心”。

---

## 5. 异常反馈页面布局

### 5.1 整体结构

推荐使用如下布局：

```text
┌──────────────────────────────────────────────┐
│ 异常反馈中心                                  │
│ 说明文字 + 快捷操作按钮                       │
├──────────────────────────────────────────────┤
│ 统计卡片区：今日新增 / 待处理 / 高风险 / 解决率 │
├──────────────────────────────────────────────┤
│ Tabs：全部反馈 | 待处理 | 高风险 | 我的反馈     │
├───────────────┬──────────────────────────────┤
│ 筛选面板       │ 反馈表格                       │
│ 时间范围       │ 时间 / 来源 / 类型 / 状态 / 操作 │
│ 状态           │                              │
│ 严重程度       │                              │
│ 来源           │                              │
└───────────────┴──────────────────────────────┘

点击表格行：
右侧打开反馈详情抽屉
```

### 5.2 为什么这样设计

这样设计的好处：

1. 首页不堆满详情，用户先看概览和列表。
2. 筛选条件放左侧或折叠区，避免占据主表格宽度。
3. 详情用右侧抽屉，不需要跳转页面。
4. 处理动作放弹窗，不打断用户当前上下文。
5. Tabs 可以让用户快速切换工作视角。

---

## 6. 异常反馈顶部概览卡片

建议展示 5 张卡片：

| 卡片 | 说明 |
|---|---|
| 今日新增 | 今天新增异常反馈数 |
| 待处理 | status = pending |
| 高风险 | severity = high / critical |
| 已解决率 | resolved / total |
| 平均处理时长 | resolved_at - created_at |

### 6.1 页面表现

每张卡片建议包含：

- 大数字
- 小标题
- 同比或环比变化
- 状态颜色

示例：

```text
┌──────────────┐
│ 今日新增       │
│  12           │
│ 较昨日 +20%   │
└──────────────┘
```

颜色建议：

| 状态 | 颜色 |
|---|---|
| 正常 | 蓝色 / 绿色 |
| 待处理较多 | 橙色 |
| 高风险 | 红色 |
| 无数据 | 灰色 |

---

## 7. 异常反馈列表设计

### 7.1 表格字段

推荐表格字段：

| 字段 | 展示方式 |
|---|---|
| 反馈时间 | 日期 + 时间 |
| 来源 | 标签：检测结果 / AI 对话 / 会议消息 |
| 关联对象 | result_id / task_id / message_id |
| 异常类型 | 标签 |
| 严重程度 | 彩色标签 |
| 评分 | 星级或数字 |
| 反馈摘要 | 单行省略 |
| 状态 | 待处理 / 处理中 / 已解决 / 已关闭 |
| 处理人 | 用户名 |
| 操作 | 查看 / 分派 / 处理 / 导出 |

### 7.2 避免表格过宽的方法

表格不要把所有字段都展示出来，可以这样处理：

1. 默认展示核心字段。
2. 次要字段放到详情抽屉。
3. 评论只展示前 30 个字。
4. 关联 ID 使用短 ID，鼠标悬浮展示完整 ID。
5. 操作按钮使用“更多”下拉菜单。

示例：

```text
时间        来源      类型       严重程度  状态      摘要              操作
05-24 10:21 检测结果  判定错误   高       待处理    模型将不合格...   查看 更多
```

---

## 8. 异常反馈详情抽屉

点击列表行后，右侧打开详情抽屉。

### 8.1 抽屉宽度

推荐：

```text
width: 720px 或 780px
```

不要全屏，除非内容特别复杂。

### 8.2 抽屉结构

```text
右侧抽屉：反馈详情
├─ 顶部：状态、严重程度、处理按钮
├─ Tab 1：反馈内容
├─ Tab 2：关联结果
├─ Tab 3：证据链路
├─ Tab 4：处理记录
└─ 底部固定操作栏：分派 / 标记处理中 / 标记解决 / 关闭
```

### 8.3 Tab 1：反馈内容

展示：

- 反馈人
- 反馈时间
- 反馈类型
- 评分
- 分类
- 评论
- 附件或截图

### 8.4 Tab 2：关联结果

展示：

- 任务 ID
- 结果 ID
- 产品 ID
- 检测结论
- 异常分数
- 模型
- Prompt 版本
- Token 消耗
- 耗时

并提供按钮：

- 查看结果详情
- 导出该结果报告

### 8.5 Tab 3：证据链路

展示：

- 缺陷坐标
- 图片标注预览
- 引用证据 citations
- 推理链 reasoning_chain
- Trace ID
- Trace URL

这里不要直接把完整 JSON 全部展开，应使用：

- 折叠面板
- 代码块
- “复制 JSON”按钮
- “打开 Trace”按钮

### 8.6 Tab 4：处理记录

展示时间线：

```text
2026-05-24 10:21 用户提交反馈
2026-05-24 10:35 专家接单处理
2026-05-24 11:10 标记为判定错误
2026-05-24 11:20 已解决
```

处理记录不要放在主表格里，放在详情抽屉中更合适。

---

## 9. 异常反馈提交入口设计

### 9.1 检测结果详情中的反馈入口

当前 `ResultDetailView.vue` 已经展示“用户反馈”模块。

建议改造为：

```text
[反馈此结果] [导出报告]
```

点击“反馈此结果”后打开弹窗或抽屉，而不是一直把反馈表单铺在页面底部。

### 9.2 为什么用弹窗/抽屉

原因：

1. 不占用结果详情页空间。
2. 用户只有需要反馈时才打开。
3. 表单可分步骤填写。
4. 后续可以加入截图、缺陷区域标注等复杂功能。

### 9.3 反馈弹窗字段

推荐字段：

| 字段 | 类型 |
|---|---|
| 异常类型 | Select |
| 严重程度 | Radio |
| 用户认为正确结论 | Select |
| 评分 | Rate |
| 问题描述 | Textarea |
| 是否关联某个缺陷 | Select |
| 上传截图 | Upload |
| 提交按钮 | Button |

### 9.4 表单布局

建议采用两列布局：

```text
左侧：异常类型、严重程度、正确结论、评分
右侧：问题描述、附件上传
```

不要所有字段一列向下排，否则弹窗也会变成长页面。

---

## 10. 异常反馈状态流转

建议状态：

```text
pending       待处理
processing    处理中
resolved      已解决
closed        已关闭
reopened      重新打开
```

### 10.1 状态流转

```text
用户提交
  ↓
待处理 pending
  ↓
处理中 processing
  ↓
已解决 resolved
  ↓
已关闭 closed
```

如果用户或管理员认为处理不充分：

```text
已解决 resolved
  ↓
重新打开 reopened
  ↓
处理中 processing
```

### 10.2 操作设计

| 操作 | 展现方式 |
|---|---|
| 分派处理人 | 弹窗 |
| 标记处理中 | 按钮 |
| 标记已解决 | 弹窗填写处理结论 |
| 关闭反馈 | 二次确认 |
| 重新打开 | 弹窗填写原因 |

---

## 11. 异常反馈需要新增的数据字段

建议扩展当前反馈表或新增统一反馈表。

### 11.1 推荐字段

| 字段 | 说明 |
|---|---|
| id | 反馈 ID |
| org_id | 组织 ID |
| source_type | result / chat / meeting |
| target_id | 结果 ID 或消息 ID |
| task_id | 任务 ID |
| actor_id | 提交人 |
| feedback_type | up / down |
| category | 异常分类 |
| severity | low / medium / high / critical |
| rating | 1-5 |
| comment | 反馈内容 |
| expected_verdict | 用户认为正确结论 |
| actual_verdict | 系统原结论 |
| status | 状态 |
| assigned_to | 处理人 |
| resolution | 处理结论 |
| resolved_at | 解决时间 |
| attachments | 附件 |
| created_at | 创建时间 |
| updated_at | 更新时间 |

---

## 12. 异常反馈接口设计

### 12.1 当前已有接口

当前已有：

```text
POST /v1/feedbacks/results/{result_id}
GET  /v1/feedbacks
POST /v1/feedbacks/messages/{target_type}/{target_id}
GET  /v1/feedbacks/messages
```

### 12.2 建议新增接口

```text
GET   /v1/feedbacks/summary
GET   /v1/feedbacks/{id}
PATCH /v1/feedbacks/{id}/status
PATCH /v1/feedbacks/{id}/assign
POST  /v1/feedbacks/{id}/comments
GET   /v1/feedbacks/export
```

### 12.3 前端 API 文件建议

修改：

```text
frontend/src/api/feedback.api.ts
```

增加：

```ts
summary(params)
detail(id)
updateStatus(id, payload)
assign(id, payload)
addComment(id, payload)
export(params)
```

---

# 第二部分：报告导出功能设计

---

## 13. 报告导出页面整体结构

推荐路由：

```text
/app/export
```

推荐页面：

```text
ReportExportView.vue
```

不要继续使用 `PlaceholderPage.vue`。

---

## 14. 报告导出页面布局

报告导出不建议做成长表单，而应该做成“分步式导出向导”。

### 14.1 整体布局

```text
┌────────────────────────────────────────────┐
│ 报告导出中心                                │
│ 选择报告类型、配置范围、预览内容并生成文件   │
├────────────────────────────────────────────┤
│ Step 1 选择报告类型                         │
│ Step 2 配置数据范围                         │
│ Step 3 选择格式和模板                       │
│ Step 4 预览并生成                           │
├──────────────────────┬─────────────────────┤
│ 左侧：当前步骤表单     │ 右侧：报告预览目录     │
└──────────────────────┴─────────────────────┘
```

### 14.2 为什么使用分步式

1. 避免所有配置项挤在一个页面里。
2. 用户知道自己处于哪一步。
3. 每一步只展示当前需要填写的信息。
4. 右侧预览可以实时显示将导出的章节。
5. 导出历史可以放到独立 Tab，不干扰新建导出。

---

## 15. 报告导出页面推荐结构

页面顶部使用 Tabs：

```text
新建导出 | 导出历史 | 报告模板
```

### 15.1 新建导出

使用步骤条：

```text
① 报告类型 → ② 数据范围 → ③ 内容配置 → ④ 预览生成
```

### 15.2 导出历史

展示历史导出任务：

| 字段 | 内容 |
|---|---|
| 报告名称 | 文件名 |
| 报告类型 | 单任务 / 批量 / 质量 / 反馈 |
| 格式 | PDF / Word / Excel / CSV |
| 状态 | 生成中 / 成功 / 失败 |
| 创建人 | 用户 |
| 创建时间 | 时间 |
| 操作 | 下载 / 重新生成 / 删除 |

### 15.3 报告模板

展示可用模板：

- 官方标准模板
- 简洁版模板
- 详细版模板
- 质检归档模板
- 异常反馈模板

后期可以支持模板管理。

---

## 16. Step 1：选择报告类型

使用卡片式选择，不要用普通下拉框。

### 16.1 报告类型卡片

| 类型 | 说明 |
|---|---|
| 单任务检测报告 | 导出某一次检测结果 |
| 批量检测汇总报告 | 导出一段时间内的检测统计 |
| 质量分析报告 | 导出幻觉率、可信度、模型表现 |
| 异常反馈报告 | 导出用户反馈和处理闭环 |
| 证据溯源报告 | 导出 Trace、引用和推理链 |

### 16.2 页面展示

```text
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ 单任务报告   │ │ 批量汇总报告 │ │ 质量分析报告 │
│ 适合单次归档 │ │ 适合周期复盘 │ │ 适合模型治理 │
└─────────────┘ └─────────────┘ └─────────────┘

┌─────────────┐ ┌─────────────┐
│ 异常反馈报告 │ │ 证据溯源报告 │
│ 适合闭环复盘 │ │ 适合审计追踪 │
└─────────────┘ └─────────────┘
```

卡片选中后高亮，并在右侧预览面板更新章节。

---

## 17. Step 2：配置数据范围

根据报告类型动态展示配置项。

### 17.1 单任务检测报告

字段：

| 字段 | 说明 |
|---|---|
| 任务 ID | 必填 |
| 是否包含图片 | 开关 |
| 是否包含缺陷坐标 | 开关 |
| 是否包含推理链 | 开关 |
| 是否包含引用证据 | 开关 |
| 是否包含用户反馈 | 开关 |
| 是否包含人工复核 | 开关 |

### 17.2 批量检测汇总报告

字段：

| 字段 | 说明 |
|---|---|
| 时间范围 | 必填 |
| 产品 ID | 可选 |
| 判定结果 | 可选 |
| 模型 | 可选 |
| Prompt 版本 | 可选 |
| 是否只导出异常样本 | 开关 |

### 17.3 质量分析报告

字段：

| 字段 | 说明 |
|---|---|
| 时间范围 | 必填 |
| 数据来源 | all / inspection / chat |
| 模型 | 可选 |
| 是否包含趋势图 | 开关 |
| 是否包含模型对比 | 开关 |
| 是否包含 Trace 明细 | 开关 |

### 17.4 异常反馈报告

字段：

| 字段 | 说明 |
|---|---|
| 时间范围 | 必填 |
| 状态 | 可选 |
| 严重程度 | 可选 |
| 异常类型 | 可选 |
| 处理人 | 可选 |
| 是否包含处理记录 | 开关 |
| 是否包含原始检测结果 | 开关 |

---

## 18. Step 3：选择格式和模板

### 18.1 格式选择

| 格式 | 使用场景 |
|---|---|
| PDF | 正式归档、对外提交 |
| DOCX | 需要人工编辑 |
| XLSX | 数据分析 |
| CSV | 原始明细 |
| JSON | 系统对接 |

### 18.2 模板选择

使用小卡片：

```text
┌──────────────┐
│ 标准报告模板   │
│ 封面+目录+正文 │
└──────────────┘

┌──────────────┐
│ 简洁模板       │
│ 只含核心结论   │
└──────────────┘

┌──────────────┐
│ 审计模板       │
│ 含证据链和日志 │
└──────────────┘
```

### 18.3 内容配置

用折叠面板展示高级选项：

```text
基础内容
  - 检测结论
  - 任务信息
  - 统计摘要

证据内容
  - 图片标注
  - 缺陷坐标
  - 引用证据

技术内容
  - 推理链
  - Trace ID
  - Token 消耗
  - 模型参数
```

默认只展开“基础内容”，其他折叠，避免页面过长。

---

## 19. Step 4：预览并生成

### 19.1 右侧预览面板

右侧固定展示报告目录：

```text
报告预览
├─ 封面
├─ 1. 检测概览
├─ 2. 结果统计
├─ 3. 异常样本
├─ 4. 缺陷明细
├─ 5. 引用证据
├─ 6. 推理链路
├─ 7. 用户反馈
└─ 附录
```

### 19.2 生成按钮

底部固定按钮：

```text
[上一步] [保存配置] [生成报告]
```

点击生成后：

1. 创建导出任务。
2. 弹出任务创建成功提示。
3. 切换到“导出历史”Tab。
4. 前端轮询任务状态。
5. 成功后显示下载按钮。

---

## 20. 报告导出历史设计

### 20.1 表格字段

| 字段 | 说明 |
|---|---|
| 报告名称 | 文件名 |
| 报告类型 | 单任务 / 批量 / 质量 / 反馈 |
| 格式 | PDF / DOCX / XLSX / CSV / JSON |
| 状态 | 等待中 / 生成中 / 成功 / 失败 |
| 创建人 | 用户 |
| 创建时间 | 时间 |
| 文件大小 | MB |
| 有效期 | 过期时间 |
| 操作 | 下载 / 重新生成 / 删除 |

### 20.2 状态标签

| 状态 | 颜色 |
|---|---|
| pending | 灰色 |
| running | 蓝色 |
| success | 绿色 |
| failed | 红色 |
| expired | 灰色 |

### 20.3 失败处理

如果导出失败，点击“查看原因”打开小弹窗：

```text
失败原因：
图片资源下载失败，无法生成 PDF。
建议：
1. 检查 MinIO 文件是否存在。
2. 尝试不包含图片重新导出。
3. 联系管理员查看后台日志。
```

---

## 21. 报告中应该展示什么内容

### 21.1 单任务检测报告

| 模块 | 内容 |
|---|---|
| 封面 | 报告名称、生成时间、生成用户、组织 |
| 任务信息 | task_id、product_id、创建时间 |
| 检测结论 | verdict、overall_score |
| 缺陷明细 | type、confidence、bbox、description |
| 图片标注 | 原图、缺陷框 |
| 模型信息 | llm_model、prompt_version、tokens_used、latency_ms |
| 引用证据 | citations |
| 推理链路 | reasoning_chain 摘要 |
| 人工复核 | reviewed_by、reviewed_at、review_note |
| 用户反馈 | feedback_type、rating、category、comment |
| Trace 信息 | trace_id、trace_url |

### 21.2 批量检测汇总报告

| 模块 | 内容 |
|---|---|
| 总检测数 | total |
| 合格率 | pass / total |
| 不合格率 | fail / total |
| 人工复核率 | manual_required / total |
| 平均异常分数 | average overall_score |
| 缺陷类型分布 | defect.type 统计 |
| 模型表现 | 按模型聚合 |
| 异常样本列表 | 高风险样本 |
| 趋势图 | 日期维度统计 |

### 21.3 质量分析报告

| 模块 | 内容 |
|---|---|
| 总结果数 | total_results |
| 幻觉率 | hallucination_rate |
| 点赞率 | thumbs_up_rate |
| 点踩率 | thumbs_down_rate |
| 平均风险分 | avg_risk_score |
| 反馈分布 | feedback_distribution |
| 模型指标 | model_metrics |
| 聊天可信度 | chat_avg_trust_score |
| 过度自信率 | chat_overconfidence_rate |
| 引用率 | chat_citation_rate |
| 趋势图 | hallucination_trend、thumbs_up_trend、thumbs_down_trend |

### 21.4 异常反馈报告

| 模块 | 内容 |
|---|---|
| 反馈总数 | 总数量 |
| 待处理数量 | status = pending |
| 高风险数量 | severity = high / critical |
| 类型分布 | category 分布 |
| 状态分布 | pending / processing / resolved / closed |
| 平均处理时长 | resolved_at - created_at |
| 明细表 | 每条反馈详情 |
| 典型案例 | 高风险或重复反馈 |
| 处理记录 | 操作时间线 |

---

## 22. 前端实现建议

### 22.1 需要新增或修改的文件

| 文件 | 处理方式 |
|---|---|
| `frontend/src/views/quality/FeedbackListView.vue` | 升级为异常反馈中心 |
| `frontend/src/components/business/result/FeedbackWidget.vue` | 改成弹窗/抽屉式反馈入口 |
| `frontend/src/views/ReportExportView.vue` | 新增报告导出中心 |
| `frontend/src/api/report.api.ts` | 新增报告导出接口 |
| `frontend/src/stores/reportExport.store.ts` | 新增导出任务状态管理 |
| `frontend/src/api/feedback.api.ts` | 扩展详情、状态、分派、导出接口 |
| `frontend/src/stores/feedback.store.ts` | 扩展 summary、detail、status |
| `frontend/src/router/routes/app.routes.ts` | 报告导出路由指向真实页面 |
| `frontend/src/composables/useMenu.ts` | 移除报告导出的 placeholder |

### 22.2 路由修改

将：

```ts
{
  path: "export",
  name: "app-export",
  component: () => import("@/views/placeholder/PlaceholderPage.vue"),
  meta: { title: "报告导出", roles: APP_ROLES }
}
```

改为：

```ts
{
  path: "export",
  name: "app-export",
  component: () => import("@/views/ReportExportView.vue"),
  meta: { title: "报告导出", roles: APP_ROLES }
}
```

### 22.3 菜单修改

将：

```ts
{ title: "报告导出", path: "/app/export", placeholder: true }
```

改为：

```ts
{ title: "报告导出", path: "/app/export" }
```

---

## 23. 后端实现建议

### 23.1 建议新增模块

```text
backend/app/api/v1/reports.py
backend/app/services/report_export_service.py
backend/app/schemas/reports.py
backend/app/models/report_export.py
backend/app/repositories/report_export_repo.py
worker/tasks/report_export_task.py
```

### 23.2 建议新增接口

```text
POST   /v1/reports/exports
GET    /v1/reports/exports
GET    /v1/reports/exports/{id}
GET    /v1/reports/exports/{id}/download
DELETE /v1/reports/exports/{id}
GET    /v1/reports/templates
```

### 23.3 导出任务表

| 字段 | 说明 |
|---|---|
| id | 导出任务 ID |
| org_id | 组织 ID |
| created_by | 创建人 |
| report_type | 报告类型 |
| format | 文件格式 |
| template_key | 模板 |
| params_json | 查询参数 |
| sections_json | 选择的章节 |
| status | pending / running / success / failed |
| file_key | MinIO 文件路径 |
| file_name | 文件名 |
| file_size | 文件大小 |
| error_message | 失败原因 |
| created_at | 创建时间 |
| started_at | 开始时间 |
| finished_at | 完成时间 |
| expires_at | 过期时间 |

### 23.4 推荐生成流程

```text
前端点击生成报告
    ↓
POST /v1/reports/exports
    ↓
后端创建导出任务 status=pending
    ↓
Celery 异步处理
    ↓
聚合 results / feedbacks / quality / traces 数据
    ↓
生成 PDF / DOCX / XLSX / CSV / JSON
    ↓
上传到 MinIO
    ↓
更新任务 status=success
    ↓
前端轮询状态并展示下载按钮
```

---

## 24. 页面美观优化重点

### 24.1 异常反馈中心

推荐设计：

1. 顶部 Hero 区不要太高，避免占用空间。
2. 统计卡片横向排布，宽屏 5 张，小屏自动换行。
3. Tabs 用于切换“全部 / 待处理 / 高风险 / 我的反馈”。
4. 筛选区默认只展示常用筛选，高级筛选折叠。
5. 表格只放核心信息，长内容省略。
6. 详情用右侧抽屉。
7. 处理动作使用弹窗。
8. 技术信息放 Tabs 或折叠面板。
9. JSON 推理链默认折叠，不直接铺开。
10. 底部操作栏固定在抽屉底部。

### 24.2 报告导出中心

推荐设计：

1. 使用分步导出，不要做成长表单。
2. 报告类型用卡片选择。
3. 数据范围根据报告类型动态展示。
4. 高级内容配置默认折叠。
5. 右侧固定报告预览目录。
6. 导出历史独立 Tab。
7. 生成中用进度条或状态标签。
8. 失败原因用弹窗展示。
9. 下载、重新生成、删除放在操作列。
10. 支持保存导出配置，方便重复生成。

### 24.3 视觉风格建议

整体保持当前系统已有风格：

- 卡片圆角：16px - 20px
- 页面间距：16px - 24px
- 主色：深蓝 / 青绿色
- 高风险：红色
- 警告：橙色
- 成功：绿色
- 次要信息：灰色
- 表格行高不要过大
- 标签颜色保持统一

---

## 25. 推荐组件拆分

### 25.1 异常反馈组件

```text
FeedbackCenterView.vue
FeedbackSummaryCards.vue
FeedbackFilterPanel.vue
FeedbackTable.vue
FeedbackDetailDrawer.vue
FeedbackStatusDialog.vue
FeedbackAssignDialog.vue
FeedbackTimeline.vue
FeedbackEvidencePanel.vue
```

### 25.2 报告导出组件

```text
ReportExportView.vue
ReportTypeSelector.vue
ReportScopeForm.vue
ReportSectionSelector.vue
ReportTemplateSelector.vue
ReportPreviewPanel.vue
ReportExportHistory.vue
ReportExportStatusTag.vue
ReportFailureDialog.vue
```

---

## 26. MVP 落地顺序

### 第一阶段：把功能从“能用”做成“像产品”

1. 修复 `FeedbackWidget.vue` 开头多余字符问题。
2. `FeedbackListView.vue` 改名或升级为异常反馈中心。
3. 增加概览卡片、筛选区、分页表格。
4. 增加反馈详情抽屉。
5. `/app/export` 替换占位页，新增 `ReportExportView.vue`。
6. 报告导出先支持 CSV、JSON。
7. 单任务检测结果支持 PDF 导出。

### 第二阶段：做闭环

1. 反馈表增加 `status`、`severity`、`assigned_to`、`resolution`。
2. 增加分派、状态流转、处理记录。
3. 详情抽屉关联结果、图片、证据、Trace。
4. 异常反馈数据接入质量分析。
5. 导出历史接入后端任务。

### 第三阶段：做正式报告能力

1. 支持 DOCX、XLSX、PDF 模板。
2. Celery 异步生成报告。
3. 文件上传 MinIO。
4. 支持导出历史、重新生成、过期清理。
5. 支持管理员全组织导出，普通用户按权限导出。

---

## 27. 最终推荐的信息流

```text
检测结果 / AI 对话 / 会议消息
        ↓
用户点击“反馈”
        ↓
弹窗或抽屉填写异常反馈
        ↓
异常反馈中心形成待处理事项
        ↓
专家/管理员分派、处理、关闭
        ↓
质量分析中心统计反馈和模型问题
        ↓
报告导出中心生成正式报告
```

---

## 28. 总结

异常反馈和报告导出应该形成一条完整链路：

- 异常反馈负责发现和处理问题。
- 质量分析负责统计和解释问题。
- 报告导出负责沉淀和交付结果。

页面上不要做成超长大页面，而要把信息拆成：

- 概览卡片
- 筛选区
- 表格列表
- 详情抽屉
- 处理弹窗
- Tabs 分组
- 折叠面板
- 分步导出
- 右侧预览
- 导出历史

这样既能充分利用页面空间，又能让用户按需查看信息，避免所有内容挤在一页里只能靠滚轮向下找。
