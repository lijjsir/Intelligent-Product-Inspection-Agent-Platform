# 证据溯源功能设计说明（避免长页面版）

> 适用项目：Intelligent-Product-Inspection-Agent-Platform  
> 适用分支：develop  
> 设计目标：把“证据溯源”做成检测结果中的深层操作能力，而不是左侧一级菜单；页面避免长滚动，通过按钮、Tabs、抽屉、弹窗、折叠面板、左右分栏等方式高效展示证据链。

---

## 1. 功能定位

### 1.1 证据溯源是什么

证据溯源的核心不是单纯展示检测结果，而是回答：

> 系统为什么得出这个检测结论？它用了哪些图片、缺陷框、标准依据、RAG 引用、模型推理、Trace 记录和人工复核信息？

它应该帮助用户追踪一条检测结果从输入到结论的全过程。

### 1.2 证据溯源要解决的问题

| 用户问题 | 证据溯源对应能力 |
|---|---|
| 这个结果为什么判定为通过或不通过？ | 展示结论摘要、异常分数、缺陷明细 |
| 模型看到了哪些缺陷？ | 展示图片标注、bbox、缺陷类型、置信度 |
| 判断依据是什么？ | 展示引用证据、标准条款、RAG 来源 |
| 模型是怎么推理的？ | 展示结构化推理链路 |
| 结果是否可靠？ | 展示可信度、幻觉风险、过度自信、引用状态 |
| 有没有人工复核？ | 展示复核人、复核时间、复核意见 |
| 用户有没有反馈异常？ | 展示点赞、点踩、异常反馈、处理状态 |
| 是否可以审计模型调用？ | 展示 Trace ID、Observation ID、Token、Langfuse 链接 |

---

## 2. 菜单设计建议

### 2.1 不建议作为一级菜单

当前仓库中“证据溯源”在用户菜单和专家菜单中使用的是：

```ts
{ title: "证据溯源", path: "/app/results/:id", placeholder: true }
```

这个设计不合理，因为 `/app/results/:id` 是动态详情页路径。左侧菜单点击时并不知道应该进入哪一条检测结果。

### 2.2 推荐设计

左侧菜单只保留：

```text
检测结果
异常反馈
报告导出
```

把“证据溯源”改成“检测结果”列表和详情页里的按钮。

推荐左侧菜单：

```text
AI 对话
会议室
任务管理
检测结果
异常反馈
报告导出
个人设置
```

检测结果列表中的操作：

```text
详情 | 证据溯源 | 异常反馈 | 导出报告
```

如果表格操作列空间不足，使用下拉菜单：

```text
操作 ▼
  - 查看详情
  - 证据溯源
  - 提交异常反馈
  - 导出报告
```

### 2.3 为什么这样更合理

| 方案 | 问题 |
|---|---|
| 证据溯源作为一级菜单 | 不知道用户要溯源哪一条结果 |
| 证据溯源作为检测结果按钮 | 用户先定位结果，再查看证据链，逻辑自然 |
| 证据溯源作为独立全局中心 | 后期可做，但当前会增加复杂度 |

当前阶段最推荐：

> 检测结果是入口，证据溯源是某条检测结果的深层操作。

---

## 3. 页面入口设计

### 3.1 检测结果列表入口

在 `ResultListView.vue` 的表格操作列中增加按钮：

```vue
<el-button
  link
  type="primary"
  size="small"
  @click="router.push(`/app/results/${scope.row.task_id}?tab=evidence`)"
>
  证据溯源
</el-button>
```

如果保留详情按钮：

```vue
<el-button link size="small" @click="router.push(`/app/results/${scope.row.task_id}`)">
  详情
</el-button>

<el-button link type="primary" size="small" @click="router.push(`/app/results/${scope.row.task_id}?tab=evidence`)">
  证据溯源
</el-button>
```

### 3.2 检测结果详情页入口

在结果详情页顶部增加快捷按钮：

```text
[返回] [证据溯源] [提交异常反馈] [导出报告]
```

点击“证据溯源”后滚动到证据区域不是最优方案，更推荐切换到证据 Tab。

### 3.3 推荐路由方式

短期复用现有结果详情页：

```text
/app/results/:task_id?tab=evidence
```

长期如果证据溯源内容越来越复杂，可以拆成独立详情页：

```text
/app/results/:task_id/evidence
```

---

## 4. 页面整体结构

### 4.1 避免长页面的原则

不要把结论摘要、图片、缺陷表、引用证据、推理链、Trace、复核、反馈全部纵向堆在一个页面里。

推荐采用：

```text
顶部摘要卡片
+
横向 Tabs
+
每个 Tab 内部左右分栏或折叠展示
```

### 4.2 推荐布局

```text
┌─────────────────────────────────────────────┐
│ 顶部：任务编号 / 结论 / 异常分数 / 模型 / 时间 │
├─────────────────────────────────────────────┤
│ Tabs：                                      │
│ 结论摘要 | 图像证据 | 引用证据 | 推理链路 | Trace | 复核反馈 │
├─────────────────────────────────────────────┤
│ 当前 Tab 内容区                              │
│ 内容区内部使用左右分栏 / 抽屉 / 折叠面板        │
└─────────────────────────────────────────────┘
```

### 4.3 页面不要超过一屏太多

推荐每个 Tab 内尽量控制在一屏内完成主要展示。低频信息使用：

- 折叠面板
- 查看更多按钮
- JSON 弹窗
- 详情抽屉
- 原文预览弹窗

---

## 5. 顶部摘要区设计

顶部摘要区只展示最关键的信息，不要做得过高。

### 5.1 展示内容

| 字段 | 展示方式 |
|---|---|
| 任务 ID | 短 ID + 复制按钮 |
| 结果 ID | 短 ID + 复制按钮 |
| 检测结论 | 彩色标签 |
| 异常分数 | 大数字 |
| 模型 | 文本标签 |
| Prompt 版本 | 文本 |
| 检测时间 | 日期 |
| Trace 状态 | 已同步 / 本地 / 缺失 |

### 5.2 推荐样式

```text
┌─────────────────────────────────────────────────────┐
│ 证据溯源详情                                         │
│ Task: xxx   Result: xxx   Model: qwen-vl             │
│ [不通过]  异常分数 92.3   Trace 已同步   2026-05-24   │
│                                                     │
│ [提交异常反馈] [导出报告] [打开 Trace]                │
└─────────────────────────────────────────────────────┘
```

### 5.3 为什么这样设计

顶部只承担“识别当前对象”和“快速操作”的作用，不承载大量详情。

---

## 6. Tab 1：结论摘要

### 6.1 功能定位

让用户快速知道：

- 当前检测结论是什么。
- 系统为什么给出这个结论。
- 是否需要人工复核。
- 是否存在高风险提示。

### 6.2 展示内容

| 内容 | 展示方式 |
|---|---|
| 判定结论 | 大标签 |
| 异常分数 | 进度条或仪表数字 |
| 结论解释 | 短文本 |
| 缺陷数量 | 小卡片 |
| 引用数量 | 小卡片 |
| 反馈数量 | 小卡片 |
| 复核状态 | 标签 |

### 6.3 页面结构

```text
左侧：结论卡片
右侧：关键指标卡片
底部：简短解释说明
```

### 6.4 避免长页面的方法

只放摘要，不放完整缺陷表、不放完整 JSON、不放完整引用内容。

---

## 7. Tab 2：图像证据

### 7.1 功能定位

展示模型识别到的图片缺陷及其位置。

### 7.2 展示内容

| 内容 | 说明 |
|---|---|
| 原图 | 支持缩放 |
| 缺陷框 | bbox 标注 |
| 缺陷类型 | 如破损、污渍、变形 |
| 置信度 | 百分比 |
| 缺陷描述 | 简短说明 |
| 样品编号 | 多样品场景区分 |

### 7.3 推荐布局

不要把所有图片从上到下铺开。推荐：

```text
┌───────────────────────────┬─────────────────────┐
│ 左侧：图片预览 + 缺陷框      │ 右侧：缺陷列表        │
│                           │ 缺陷1                │
│                           │ 缺陷2                │
│                           │ 缺陷3                │
└───────────────────────────┴─────────────────────┘
底部：图片缩略图 Carousel
```

### 7.4 交互设计

| 操作 | 说明 |
|---|---|
| 点击缺陷列表 | 图片中高亮对应 bbox |
| 点击 bbox | 右侧定位到缺陷详情 |
| 缩放图片 | 查看细节 |
| 切换缩略图 | 查看不同样品 |
| 查看原图 | 弹窗打开大图 |

### 7.5 避免长页面的方法

- 多张图片用缩略图切换。
- 缺陷详情放右侧列表。
- 原图大图用弹窗。
- 多缺陷列表限制高度，内部滚动。

---

## 8. Tab 3：引用证据

### 8.1 功能定位

展示模型引用了哪些标准、文档、知识库片段作为判断依据。

### 8.2 展示内容

| 内容 | 说明 |
|---|---|
| 文档名称 | 标准或知识库文件名 |
| 引用位置 | 页码、章节、条款 |
| 引用片段 | 命中的文本 |
| 相关度 | 相似度或分数 |
| 是否过期 | 标准是否已过期 |
| 证据类型 | 标准、规则、历史案例、说明文档 |
| 操作 | 查看原文、复制引用 |

### 8.3 推荐布局

```text
┌──────────────────────┬────────────────────────┐
│ 左侧：引用来源列表      │ 右侧：当前引用详情        │
│ - GB 标准 A           │ 文档名称                 │
│ - 企业规范 B          │ 条款内容                 │
│ - 历史案例 C          │ 命中片段                 │
└──────────────────────┴────────────────────────┘
```

### 8.4 交互设计

- 点击左侧引用来源，右侧展示对应片段。
- “查看原文”用弹窗或新窗口。
- “复制引用”复制规范格式。
- “查看原始 citations JSON”放折叠区。

### 8.5 避免长页面的方法

不要把所有引用全文直接铺开。只展示当前选中的引用，其他引用作为列表。

---

## 9. Tab 4：推理链路

### 9.1 功能定位

把原本难读的 `reasoning_chain` JSON 转换为用户能理解的过程链路。

### 9.2 推荐结构

```text
输入解析 → 图像识别 → 证据检索 → 标准匹配 → 模型判断 → 结论生成 → 风险评分
```

### 9.3 展示内容

每个步骤展示：

| 字段 | 说明 |
|---|---|
| 步骤名称 | 如“证据检索” |
| 状态 | 成功 / 失败 / 跳过 |
| 输入摘要 | 简略内容 |
| 输出摘要 | 简略内容 |
| 关联证据 | 引用、缺陷、图片 |
| 耗时 | ms |
| 风险提示 | 如缺证据、低置信度 |

### 9.4 推荐布局

使用纵向时间线：

```text
● 输入解析
  识别到任务类型：包装缺陷检测

● 图像识别
  发现 3 个疑似缺陷

● 证据检索
  命中 2 条标准依据

● 模型判断
  判定为不通过

● 风险评分
  幻觉风险：低
```

### 9.5 原始 JSON 怎么处理

不要默认展示完整 JSON。建议：

```text
[查看原始 reasoning_chain JSON]
```

点击后打开弹窗，或者在折叠面板中展示。

### 9.6 避免长页面的方法

- 时间线默认只展示摘要。
- 每个节点点击后在右侧小面板展示详情。
- 原始 JSON 放弹窗。
- 长文本折叠显示。

---

## 10. Tab 5：Trace 信息

### 10.1 功能定位

展示模型调用链路和可观测性信息。

### 10.2 展示内容

| 内容 | 字段 |
|---|---|
| Trace ID | trace_id |
| Observation ID | observation_id |
| 模型 | model_key |
| Token 使用 | total_tokens |
| 可信度 | trust_score |
| 幻觉风险 | hallucination_risk |
| 过度自信 | overconfidence |
| 是否有引用 | has_citation |
| Langfuse 状态 | synced / local_only / missing |
| Trace 链接 | trace_url |

### 10.3 推荐布局

```text
左侧：Trace 基本信息
右侧：质量评分卡片
底部：操作按钮
```

操作按钮：

```text
[打开 Langfuse] [复制 Trace ID] [刷新状态]
```

### 10.4 避免长页面的方法

Trace 只展示关键指标，详细 observation、prompt、completion 不在页面展开，而是通过“打开 Langfuse”查看。

---

## 11. Tab 6：复核与反馈

### 11.1 功能定位

展示该结果后续有没有被人修正、有没有被用户反馈异常。

### 11.2 展示内容

| 内容 | 说明 |
|---|---|
| 用户反馈 | 点赞、点踩、评分、评论 |
| 异常反馈 | 异常类型、严重程度、状态 |
| 人工复核 | 复核结论、复核人、复核时间 |
| 复核备注 | 专家说明 |
| 处理记录 | 时间线 |

### 11.3 推荐布局

```text
上方：反馈统计卡片
中间：人工复核记录
下方：处理时间线
右侧：提交异常反馈按钮
```

### 11.4 避免长页面的方法

- 反馈明细默认展示最近 3 条。
- 更多反馈放弹窗或抽屉。
- 处理记录用时间线折叠。
- 提交反馈用弹窗，不在页面直接铺表单。

---

## 12. 证据溯源详情页的推荐最终形态

```text
┌──────────────────────────────────────────────┐
│ 顶部摘要区：结论、分数、模型、Trace 状态        │
├──────────────────────────────────────────────┤
│ Tabs：摘要 | 图像 | 引用 | 推理 | Trace | 反馈   │
├──────────────────────────────────────────────┤
│ 当前 Tab 内容                                │
└──────────────────────────────────────────────┘
```

每个 Tab 内部控制信息密度：

| Tab | 推荐展示方式 |
|---|---|
| 摘要 | 卡片 + 简短说明 |
| 图像 | 左图右列表 + 缩略图 |
| 引用 | 左列表右详情 |
| 推理 | 时间线 + 右侧详情 |
| Trace | 指标卡片 + 外链按钮 |
| 反馈 | 时间线 + 弹窗表单 |

---

## 13. 检测结果列表如何增加按钮

### 13.1 操作列推荐

当前检测结果列表已经有操作列。建议改为：

```vue
<el-table-column label="操作" width="220" fixed="right">
  <template #default="scope">
    <el-button
      link
      type="primary"
      size="small"
      @click="router.push(`/app/results/${scope.row.task_id}`)"
    >
      详情
    </el-button>

    <el-button
      link
      type="primary"
      size="small"
      @click="router.push(`/app/results/${scope.row.task_id}?tab=evidence`)"
    >
      证据溯源
    </el-button>

    <el-dropdown>
      <el-button link size="small">更多</el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item>提交异常反馈</el-dropdown-item>
          <el-dropdown-item>导出报告</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </template>
</el-table-column>
```

### 13.2 如果操作列太宽

可以改成：

```vue
<el-dropdown trigger="click">
  <el-button link type="primary" size="small">操作</el-button>
  <template #dropdown>
    <el-dropdown-menu>
      <el-dropdown-item>查看详情</el-dropdown-item>
      <el-dropdown-item>证据溯源</el-dropdown-item>
      <el-dropdown-item>提交异常反馈</el-dropdown-item>
      <el-dropdown-item>导出报告</el-dropdown-item>
    </el-dropdown-menu>
  </template>
</el-dropdown>
```

这样表格更清爽。

---

## 14. 路由和菜单改造建议

### 14.1 菜单修改

删除用户菜单和专家菜单中的：

```ts
{ title: "证据溯源", path: "/app/results/:id", placeholder: true }
```

保留：

```ts
{ title: "检测结果", path: "/app/results" }
{ title: "异常反馈", path: "/app/feedbacks" }
{ title: "报告导出", path: "/app/export" }
```

### 14.2 路由保留

现有：

```ts
{
  path: "results/:id",
  name: "app-result-detail",
  component: () => import("@/views/ResultDetailView.vue"),
  meta: { title: "证据溯源", roles: [...] }
}
```

可以改标题为：

```ts
meta: { title: "检测结果详情" }
```

页面内部再使用 Tab 区分“结果详情”和“证据溯源”。

### 14.3 详情页支持 query tab

建议在 `ResultDetailView.vue` 中读取：

```ts
const activeTab = ref((route.query.tab as string) || "summary");
```

支持：

```text
/app/results/:task_id?tab=summary
/app/results/:task_id?tab=image
/app/results/:task_id?tab=citation
/app/results/:task_id?tab=reasoning
/app/results/:task_id?tab=trace
/app/results/:task_id?tab=feedback
```

---

## 15. 数据来源设计

### 15.1 当前可复用数据

| 数据 | 来源 |
|---|---|
| 检测结果 | result detail |
| 任务图片 | task detail |
| 缺陷框 | defects |
| 引用证据 | citations |
| 推理链 | reasoning_chain |
| 模型信息 | llm_model、prompt_version |
| 性能数据 | tokens_used、latency_ms |
| 人工复核 | reviewed_by、reviewed_at、review_note |
| 用户反馈 | feedbacks |
| Trace 信息 | reasoning_chain.trace 或 quality traces |

### 15.2 前端类型建议

```ts
interface EvidenceViewModel {
  resultId: string;
  taskId: string;
  verdict: string;
  score: number;
  model: string;
  promptVersion: string;
  tokensUsed?: number;
  latencyMs?: number;
  defects: Defect[];
  citations: Citation[];
  reasoningSteps: ReasoningStep[];
  trace?: TraceInfo;
  review?: ReviewInfo;
  feedbacks: Feedback[];
}
```

---

## 16. 组件拆分建议

为了避免 `ResultDetailView.vue` 越来越大，建议拆组件。

```text
frontend/src/components/business/evidence/
├─ EvidenceHeader.vue
├─ EvidenceSummaryTab.vue
├─ EvidenceImageTab.vue
├─ EvidenceCitationTab.vue
├─ EvidenceReasoningTab.vue
├─ EvidenceTraceTab.vue
├─ EvidenceFeedbackTab.vue
├─ EvidenceJsonDialog.vue
└─ EvidenceExportButton.vue
```

`ResultDetailView.vue` 只负责：

- 获取数据
- 管理 activeTab
- 组合各个 Tab 组件

---

## 17. MVP 实现顺序

### 第一阶段：菜单与入口调整

1. 删除左侧菜单中的“证据溯源”。
2. 保留“检测结果”菜单。
3. 在检测结果列表增加“证据溯源”按钮。
4. 跳转到 `/app/results/:task_id?tab=evidence`。

### 第二阶段：详情页结构优化

1. 将当前长页面改成 Tabs。
2. 顶部保留摘要区。
3. 图像、缺陷、引用、推理、复核、反馈分别放入不同 Tab。
4. 原始 JSON 改成弹窗或折叠面板。

### 第三阶段：证据链增强

1. 推理链 JSON 转换成时间线。
2. 引用证据做成左列表右详情。
3. 图片证据做成左图右缺陷列表。
4. Trace 信息接入 Langfuse 跳转。
5. 支持单条证据报告导出。

---

## 18. 最终推荐方案

最终结构建议：

```text
左侧菜单
├─ 任务管理
├─ 检测结果
├─ 异常反馈
├─ 报告导出
└─ 个人设置

检测结果列表
├─ 查看详情
├─ 证据溯源
├─ 提交异常反馈
└─ 导出报告

证据溯源详情页
├─ 顶部摘要
├─ 结论摘要 Tab
├─ 图像证据 Tab
├─ 引用证据 Tab
├─ 推理链路 Tab
├─ Trace 信息 Tab
└─ 复核反馈 Tab
```

一句话总结：

> 证据溯源不作为一级菜单，而是作为检测结果的深层按钮；页面不做成长滚动，而是通过顶部摘要 + Tabs + 分栏 + 弹窗 + 折叠面板来组织证据内容。
