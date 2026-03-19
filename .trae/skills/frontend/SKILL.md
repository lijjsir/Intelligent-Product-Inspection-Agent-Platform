---
name: piap-frontend-codegen
description: >
  产品智能检测 Agent 平台前端代码生成技能（Vue 3 / Vite / Pinia / Element Plus）。
  当用户提出以下任意需求时，务必调用本技能：
  - 为 PIAP 平台生成任意前端代码（页面、组件、Store、API 封装、路由、Composable）
  - 生成 Vue 3 Composition API 组件（<script setup lang="ts">）
  - 编写 Pinia Store 模块（auth/task/stability/alert 等）
  - 实现 Axios API 封装、SSE 实时推送订阅
  - 生成 ECharts 图表组件（趋势图、雷达图、仪表盘、饼图）
  - 编写 Element Plus 表单、表格、弹窗、抽屉等交互组件
  - 实现图像上传（分片、进度条）、缺陷标注（Canvas）
  - 编写 TypeScript 类型定义、工具函数、路由配置
  - 任何涉及 piap-frontend/src/ 目录下文件的新增或修改
---

# PIAP 前端代码生成技能

本技能指导 Claude 按照 PIAP 平台前端架构规范生成可直接集成的 Vue 3 代码。
生成前须先确认目标文件所在层（views / components / stores / api / composables），再按对应模板输出。

---

## 一、架构层速查

| 关键词 | 目标层 | 输出文件位置 |
|--------|--------|-------------|
| 页面 / 列表页 / 详情页 | views/ | src/views/{domain}/{Name}View.vue |
| 业务组件 / 图表 / 标注 | components/business/ | src/components/business/{domain}/{Name}.vue |
| 通用组件 / UI 组件 | components/common/ | src/components/common/{Name}.vue |
| Store / 状态管理 | stores/ | src/stores/{name}.store.ts |
| API 封装 / 请求 | api/ | src/api/{resource}.api.ts |
| 组合式函数 / 逻辑复用 | composables/ | src/composables/use{Name}.ts |
| 类型定义 | types/ | src/types/{domain}.types.ts |
| 工具函数 | utils/ | src/utils/{name}.ts |
| 路由配置 | router/ | src/router/routes/{domain}.routes.ts |

---

## 二、各层代码模板

### 2.1 页面视图模板（Views）

```vue
<!-- src/views/{domain}/{Name}View.vue -->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { use{Name}Store } from '@/stores/{name}.store'
import { use{Name}Api }   from '@/api/{name}.api'
import { usePermission }  from '@/composables/usePermission'
import { usePagination }  from '@/composables/usePagination'
import PageHeader         from '@/components/common/PageHeader.vue'
import DataTable          from '@/components/common/DataTable.vue'
// 按需引入业务组件

const store      = use{Name}Store()
const { hasRole } = usePermission()
const { page, pageSize, total, onPageChange } = usePagination()

const loading = ref(false)
const filters = ref({ status: '', keyword: '' })

// ── 数据加载 ──────────────────────────────────────
onMounted(() => fetchData())

async function fetchData() {
  loading.value = true
  try {
    await store.fetch{Items}({ ...filters.value, page: page.value, pageSize: pageSize.value })
    total.value = store.total
  } finally {
    loading.value = false
  }
}

// ── 操作处理 ──────────────────────────────────────
async function handleCreate() {
  // 跳转或弹窗
}

async function handleDelete(id: string) {
  await store.delete{Item}(id)
  ElMessage.success('删除成功')
  fetchData()
}
</script>

<template>
  <div class="page-container">
    <PageHeader title="{页面标题}" subtitle="{描述}">
      <template #actions>
        <el-button v-if="hasRole('inspector')" type="primary" @click="handleCreate">
          + 新建
        </el-button>
      </template>
    </PageHeader>

    <!-- 筛选栏 -->
    <el-card class="mb-4" shadow="never">
      <el-form :model="filters" inline>
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部">
            <el-option label="待处理" value="pending" />
            <el-option label="已完成" value="done" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchData">查询</el-button>
          <el-button @click="filters = { status: '', keyword: '' }">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 数据表格 -->
    <DataTable
      :data="store.{items}"
      :loading="loading"
      :total="total"
      @page-change="onPageChange"
    >
      <el-table-column prop="id"     label="ID"   width="200" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <{Name}StatusBadge :status="row.status" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="$router.push(`/{path}/${row.id}`)">详情</el-button>
          <el-button link type="danger"  @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </DataTable>
  </div>
</template>

<style scoped>
.page-container { padding: 24px; background: #F3F4F6; min-height: 100%; }
</style>
```

**页面层规则：**
- 不直接调用 API，通过 Store Action 获取数据
- 权限控制用 `usePermission().hasRole()` 包裹 `v-if`，不写条件业务逻辑
- loading 状态必须在 `finally` 中重置，防止接口报错后界面卡死
- 每个页面自带 `PageHeader` + 筛选区 + 数据展示区三段式结构

---

### 2.2 业务组件模板

```vue
<!-- src/components/business/{domain}/{Name}.vue -->
<script setup lang="ts">
import type { {TypeName} } from '@/types/{domain}.types'

// ── Props & Emits（必须有类型声明）──────────────────
interface Props {
  data:    {TypeName}
  size?:   'small' | 'default' | 'large'
  readonly?: boolean
}
interface Emits {
  (e: 'action', payload: {TypeName}): void
  (e: 'close'): void
}

const props = withDefaults(defineProps<Props>(), {
  size: 'default',
  readonly: false,
})
const emit = defineEmits<Emits>()

// ── 内部状态 ──────────────────────────────────────
// 业务组件可以引用 Store，但只读取不写入（写入由页面层负责）
// import { useTaskStore } from '@/stores/task.store'
// const store = useTaskStore()

// ── 计算属性 ──────────────────────────────────────
const displayConfig = computed(() => ({
  // 根据 props.data 计算展示配置
}))
</script>

<template>
  <!-- 组件模板 -->
</template>

<style scoped>
/* 仅使用 Tailwind 类或 scoped CSS，不写全局样式 */
</style>
```

**业务组件规则：**
- Props 和 Emits 必须有完整 TypeScript 接口声明
- 通用组件（`common/`）禁止引用任何 Store；业务组件可以读 Store，不能写
- 写操作通过 `emit` 通知父级页面处理，保持单向数据流

---

### 2.3 Pinia Store 模板

```typescript
// src/stores/{name}.store.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { {name}Api }    from '@/api/{name}.api'
import type { {Type}, {Type}ListQuery } from '@/types/{name}.types'

export const use{Name}Store = defineStore('{name}', () => {
  // ── State ────────────────────────────────────────
  const items      = ref<{Type}[]>([])
  const current    = ref<{Type} | null>(null)
  const total      = ref(0)
  const loading    = ref(false)

  // ── Getters ──────────────────────────────────────
  const count = computed(() => items.value.length)

  // ── Actions ──────────────────────────────────────
  async function fetch{Items}(query: {Type}ListQuery) {
    loading.value = true
    try {
      const { data } = await {name}Api.list(query)
      items.value = data.items
      total.value = data.total
    } finally {
      loading.value = false
    }
  }

  async function fetch{Item}(id: string) {
    const { data } = await {name}Api.get(id)
    current.value = data
    return data
  }

  async function create{Item}(payload: unknown) {
    const { data } = await {name}Api.create(payload)
    items.value.unshift(data)   // 乐观更新：新条目插入列表头
    total.value++
    return data
  }

  async function delete{Item}(id: string) {
    await {name}Api.delete(id)
    items.value = items.value.filter(i => i.id !== id)
    total.value--
  }

  function $reset() {
    items.value   = []
    current.value = null
    total.value   = 0
  }

  return { items, current, total, loading, count,
           fetch{Items}, fetch{Item}, create{Item}, delete{Item}, $reset }
})
```

**Store 规则：**
- 使用 Setup Store 写法（`() => {}`），不使用 Options Store
- `loading` 状态在 Store 内管理，不在组件内重复定义
- 写操作成功后做乐观更新，不重新请求整个列表（减少接口调用）
- 导出 `$reset()` 方法，登出时清空所有 Store
- Store 间通信通过 Pinia 实例直接引用，不使用 EventBus

---

### 2.4 API 封装模板

```typescript
// src/api/{resource}.api.ts
import { client } from './client'
import type { {Type}, {Type}Create, {Type}ListQuery } from '@/types/{resource}.types'
import type { PagedResponse, ResponseEnvelope } from '@/types/common.types'

export const {resource}Api = {

  list(query: {Type}ListQuery) {
    return client.get<ResponseEnvelope<PagedResponse<{Type}>>>('/{resources}', { params: query })
  },

  get(id: string) {
    return client.get<ResponseEnvelope<{Type}>>(`/{resources}/${id}`)
  },

  create(payload: {Type}Create) {
    return client.post<ResponseEnvelope<{Type}>>('/{resources}', payload)
  },

  update(id: string, payload: Partial<{Type}Create>) {
    return client.patch<ResponseEnvelope<{Type}>>(`/{resources}/${id}`, payload)
  },

  delete(id: string) {
    return client.delete<ResponseEnvelope<void>>(`/{resources}/${id}`)
  },

  // SSE 订阅（返回 EventSource 实例，由 useSSE 管理生命周期）
  streamProgress(taskId: string, token: string): EventSource {
    return new EventSource(`/api/v1/tasks/${taskId}/stream?token=${token}`)
  },
}
```

---

### 2.5 组合式函数模板

```typescript
// src/composables/use{Name}.ts
import { ref, onUnmounted } from 'vue'

/**
 * {功能描述}
 * @param {参数说明}
 * @example
 * const { data, loading, execute } = use{Name}(options)
 */
export function use{Name}(options: {OptionsType}) {
  const data    = ref<{DataType} | null>(null)
  const loading = ref(false)
  const error   = ref<Error | null>(null)

  async function execute() {
    loading.value = true
    error.value   = null
    try {
      // 实现逻辑
    } catch (e) {
      error.value = e as Error
      throw e   // 抛出让调用方决定是否处理
    } finally {
      loading.value = false
    }
  }

  // 清理副作用（定时器、EventSource、ResizeObserver 等）
  onUnmounted(() => {
    // cleanup()
  })

  return { data, loading, error, execute }
}
```

**常用 Composable 说明：**

```typescript
// useSSE — SSE 连接管理
const { messages, connected, connect, disconnect } = useSSE(url, {
  onMessage: (msg) => { /* 处理推理链节点消息 */ },
  onError:   () => { /* 指数退避重连 */ },
  autoReconnect: true,
  maxRetries: 5,
})

// usePagination — 分页状态
const { page, pageSize, total, onPageChange, resetPage } = usePagination({ defaultSize: 20 })

// usePermission — 权限检查
const { hasRole, hasPermission } = usePermission()
if (!hasRole('org_admin')) router.push('/403')

// useECharts — ECharts 实例管理（响应式 resize）
const { chartRef, chart, setOption } = useECharts()
setOption({ /* ECharts option */ })
```

---

### 2.6 ECharts 图表组件模板

```vue
<!-- src/components/business/analytics/PassRateTrendChart.vue -->
<script setup lang="ts">
import { watch } from 'vue'
import { useECharts } from '@/composables/useECharts'
import type { TrendPoint } from '@/types/analytics.types'

interface Props {
  data: TrendPoint[]
  loading?: boolean
}
const props = withDefaults(defineProps<Props>(), { loading: false })

const { chartRef, setOption } = useECharts()

// 数据变化时重绘
watch(() => props.data, (newData) => {
  setOption({
    tooltip: { trigger: 'axis', formatter: '{b}: {c}%' },
    xAxis: {
      type: 'category',
      data: newData.map(d => d.date),
      axisLine: { lineStyle: { color: '#E5E7EB' } },
    },
    yAxis: {
      type: 'value',
      min: 80, max: 100,
      axisLabel: { formatter: '{value}%' },
    },
    series: [{
      type: 'line',
      data: newData.map(d => d.pass_rate * 100),
      smooth: true,
      lineStyle: { color: '#2563A8', width: 2.5 },
      areaStyle: { color: { type: 'linear', x:0,y:0,x2:0,y2:1,
        colorStops: [
          { offset: 0, color: 'rgba(37,99,168,0.15)' },
          { offset: 1, color: 'rgba(37,99,168,0)' },
        ]
      }},
      symbol: 'circle', symbolSize: 5,
    }],
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
  })
}, { immediate: true })
</script>

<template>
  <div v-loading="loading" class="w-full h-full">
    <div ref="chartRef" class="w-full" style="height: 200px" />
  </div>
</template>
```

**图表规范：**
- 颜色体系与风险等级对齐：通过率用 `#2563A8`，幻觉率用 `#D97706`，RED 用 `#DC2626`
- 所有图表通过 `useECharts` 管理 resize observer，不直接 `new ECharts()`
- 数据通过 Props 传入，图表内不调用 Store 或 API

---

### 2.7 风险等级相关组件

```vue
<!-- src/components/business/stability/RiskLevelBadge.vue -->
<script setup lang="ts">
import type { RiskLevel } from '@/types/stability.types'

const props = defineProps<{ level: RiskLevel; showScore?: boolean; score?: number }>()

// 颜色配置（与设计规范一致，不可修改）
const CONFIG: Record<RiskLevel, { color: string; bg: string; label: string }> = {
  GREEN:  { color: '#16A34A', bg: '#16A34A18', label: '低风险'  },
  YELLOW: { color: '#D97706', bg: '#D9770618', label: '中风险'  },
  ORANGE: { color: '#EA580C', bg: '#EA580C18', label: '高风险'  },
  RED:    { color: '#DC2626', bg: '#DC262618', label: '极高风险' },
}
const cfg = computed(() => CONFIG[props.level])
</script>

<template>
  <span
    :style="{ color: cfg.color, background: cfg.bg,
              border: `1px solid ${cfg.color}40` }"
    class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-semibold"
  >
    <span :style="{ background: cfg.color }" class="w-1.5 h-1.5 rounded-full" />
    {{ cfg.label }}
    <span v-if="showScore && score !== undefined" class="opacity-70">{{ score }}</span>
  </span>
</template>
```

---

### 2.8 TypeScript 类型定义模板

```typescript
// src/types/{domain}.types.ts

// ── 枚举（与后端 domain/ 层对齐）────────────────────
export type TaskStatus    = 'pending' | 'running' | 'done' | 'failed' | 'reviewing'
export type Verdict       = 'pass'    | 'fail'    | 'uncertain' | 'manual_required'
export type RiskLevel     = 'GREEN'   | 'YELLOW'  | 'ORANGE'    | 'RED'
export type Role          = 'super_admin' | 'org_admin' | 'inspector' | 'analyst' | 'api_service' | 'auditor'

// ── 领域实体 ──────────────────────────────────────
export interface InspectionTask {
  id:          string        // UUIDv7 字符串格式
  org_id:      string
  product_id:  string
  spec_id:     string
  status:      TaskStatus
  priority:    number
  image_urls:  string[]
  metadata:    Record<string, unknown> | null
  created_at:  string        // ISO 8601
  updated_at:  string
}

export interface StabilityReport {
  id:                  string
  result_id:           string
  risk_score:          number          // [0, 100]
  risk_level:          RiskLevel
  evidence_score:      number          // [0, 1]
  consistency_score:   number
  confidence_score:    number
  traceability_score:  number
  anomaly_score:       number
  dimension_detail:    Record<string, unknown> | null
  sampling_results:    unknown[] | null
  root_cause:          string | null
}

// ── 请求/响应 ─────────────────────────────────────
export interface TaskCreate {
  product_id:  string
  spec_id:     string
  image_urls:  string[]
  priority?:   number
  metadata?:   Record<string, unknown>
}

export interface TaskListQuery extends PageParams {
  status?:     TaskStatus
  product_id?: string
}
```

---

## 三、跨层生成规范

### 3.1 新增一个完整页面功能的标准顺序
```
1. src/types/{domain}.types.ts        （类型先行，无依赖）
2. src/api/{resource}.api.ts          （API 封装）
3. src/stores/{name}.store.ts         （状态管理）
4. src/components/business/{domain}/  （子组件）
5. src/views/{domain}/{Name}View.vue  （页面）
6. src/router/routes/{domain}.routes.ts （注册路由）
```

### 3.2 SSE 推理链进度集成

```vue
<script setup lang="ts">
import { useSSE }      from '@/composables/useSSE'
import { useAuthStore } from '@/stores/auth.store'

const props = defineProps<{ taskId: string }>()
const auth  = useAuthStore()

interface NodeLog { node: string; status: 'running' | 'done' | 'error'; summary?: string }
const logs = ref<NodeLog[]>([])
const done = ref(false)

const { connect, disconnect } = useSSE(
  `/api/v1/tasks/${props.taskId}/stream?token=${auth.token}`,
  {
    onMessage(raw: string) {
      const msg = JSON.parse(raw)
      if (msg.type === 'node_start') {
        logs.value.push({ node: msg.data.node, status: 'running' })
      } else if (msg.type === 'node_done') {
        const log = logs.value.find(l => l.node === msg.data.node)
        if (log) { log.status = 'done'; log.summary = msg.data.summary }
      } else if (msg.type === 'complete') {
        done.value = true
        disconnect()
      }
    },
  }
)

onMounted(() => connect())
onUnmounted(() => disconnect())
</script>
```

### 3.3 颜色常量（必须从 constants/ 引入，不可硬编码）

```typescript
// src/constants/risk.ts
export const RISK_COLOR: Record<RiskLevel, string> = {
  GREEN:  '#16A34A',
  YELLOW: '#D97706',
  ORANGE: '#EA580C',
  RED:    '#DC2626',
}

export const STATUS_COLOR: Record<TaskStatus, string> = {
  pending:   '#9CA3AF',
  running:   '#3B82F6',
  done:      '#16A34A',
  failed:    '#DC2626',
  reviewing: '#D97706',
}
```

### 3.4 Element Plus 表单校验规范

```typescript
// 每个表单必须定义 ElFormInstance 和 rules
const formRef = ref<InstanceType<typeof ElForm>>()
const rules: FormRules = {
  product_id: [
    { required: true, message: '产品编号不能为空', trigger: 'blur' },
    { max: 64, message: '产品编号不超过 64 个字符', trigger: 'blur' },
  ],
  image_urls: [
    { required: true, type: 'array', min: 1, message: '至少上传 1 张图像', trigger: 'change' },
  ],
}

// 提交前必须调用验证
async function handleSubmit() {
  await formRef.value?.validate()   // 验证失败自动抛出，不需要手动判断
  // 验证通过后继续
}
```

---

## 四、代码质量检查清单

生成代码后自我检查：

- [ ] 组件是否使用 `<script setup lang="ts">`
- [ ] Props 和 Emits 是否有完整 TypeScript 接口声明
- [ ] 页面是否只通过 Store 获取数据，没有直接调用 API
- [ ] 通用组件是否未引用任何 Store
- [ ] 异步操作是否有 loading 状态，且在 `finally` 中重置
- [ ] ECharts 组件是否使用 `useECharts`，没有直接 `new ECharts()`
- [ ] SSE 是否在 `onUnmounted` 中调用了 `disconnect()`
- [ ] 颜色值是否从 `constants/` 引入，没有在模板中硬编码
- [ ] 新页面是否已注册到对应的 `*.routes.ts` 文件
- [ ] 路由 `meta.roles` 是否配置了最低权限角色
