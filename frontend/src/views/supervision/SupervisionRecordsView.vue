<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { useAuthStore } from "@/stores/auth.store";
import { supervisionApi } from "@/api/supervision.api";
import { productMasterApi } from "@/api/product-master.api";
import { taskApi } from "@/api/task.api";
import { http } from "@/api/http";
import { formatServerDateTime } from "@/utils/date-time";
import SupervisionFields from "@/components/business/supervision/SupervisionFields.vue";
import SupervisionAssessment from "@/components/business/supervision/SupervisionAssessment.vue";
import SupervisionAgentRail from "@/components/business/supervision/SupervisionAgentRail.vue";
import SupervisionModuleHeader from "@/components/business/supervision/SupervisionModuleHeader.vue";
import BulkImportDialog from "@/components/business/supervision/BulkImportDialog.vue";
const importDialog = ref(false);
import { cleanFields, defaults, fields } from "@/components/business/supervision/form-fields";
import {
  KIND_LABELS,
  STATUS_LABELS,
  OP_LABELS,
  type SupervisionKind,
  type SupervisionRecord,
  type SupervisionRun,
} from "@/types/supervision.types";

const route = useRoute(),
  router = useRouter(),
  auth = useAuthStore();
const kind = computed(() => (route.meta.supervisionKind || "risk-cases") as SupervisionKind);
const title = computed(() => KIND_LABELS[kind.value]);
const moduleMeta = computed(() => {
  if (kind.value === "risk-cases") {
    return {
      index: "02",
      code: "VOC",
      agentName: "舆情监测 Agent",
      tone: "cyan" as const,
      description: "从投诉、舆情、图片与附件中分离事实、情绪和推测，形成可定位、可补证的风险线索。",
      principle: "舆情热度不等于质量风险 · 每个判断必须引用证据",
    };
  }
  if (kind.value === "sampling-plans") {
    return {
      index: "03",
      code: "SAM",
      agentName: "监督抽查 Agent",
      tone: "amber" as const,
      description: "依据已复核风险、产品覆盖和资源约束，制定可批准、可解释、可执行的监督抽查方案。",
      principle: "硬约束先于优化 · 未批准计划不得创建正式任务",
    };
  }
  return null;
});
const enabled = ref(false),
  loading = ref(false),
  saving = ref(false),
  dialog = ref(false);
const manualDialog = ref(false),
  manualLevel = ref("unknown"),
  manualEvidence = ref<string[]>([]),
  manualReason = ref("");
async function saveManual() {
  if (!selected.value) return;
  selected.value = (
    await supervisionApi.manualAssessment(selected.value.id, {
      version: selected.value.version,
      risk_level: manualLevel.value,
      evidence_ids: manualEvidence.value,
      reason: manualReason.value,
    })
  ).data.data;
  manualDialog.value = false;
  await load();
}
const rows = ref<SupervisionRecord[]>([]),
  selected = ref<SupervisionRecord | null>(null),
  run = ref<SupervisionRun | null>(null);
const page = ref(1),
  total = ref(0),
  keyword = ref(""),
  region = ref(""),
  form = ref<Record<string, any>>({}),
  name = ref(""),
  code = ref(""),
  editing = ref(false);
const options = ref<Record<string, { value: string; label: string }[]>>({
  enterpriseRoles: [
    { value: "manufacturer", label: "生产企业" },
    { value: "seller", label: "销售企业" },
    { value: "both", label: "生产与销售" },
  ],
  calibration: [
    { value: "valid", label: "有效" },
    { value: "expired", label: "已过期" },
    { value: "unknown", label: "未确认" },
  ],
  online: [
    { value: "online", label: "在线" },
    { value: "offline", label: "离线" },
    { value: "unknown", label: "未知" },
  ],
  sources: [
    { value: "complaint", label: "消费投诉" },
    { value: "public_opinion", label: "舆情" },
    { value: "inspection", label: "检测报告" },
    { value: "enterprise", label: "企业信息" },
    { value: "image", label: "图像证据" },
    { value: "standard", label: "标准条款" },
    { value: "device", label: "设备数据" },
    { value: "expert", label: "专家意见" },
  ],
  natures: [
    { value: "observed", label: "真实来源" },
    { value: "inferred", label: "推断候选" },
    { value: "synthetic", label: "模拟或合成" },
  ],
});
const runtimeEdit = computed(() => auth.role === "platform_operator" && kind.value === "devices");
const canCreate = computed(() =>
  ["regions", "enterprises", "devices"].includes(kind.value)
    ? auth.role === "admin"
    : kind.value === "baselines"
      ? ["admin", "algorithm_engineer"].includes(auth.role)
      : kind.value === "sampling-plans"
        ? auth.role === "expert"
        : ["user", "expert"].includes(auth.role),
);
const canEdit = computed(
  () =>
    !!selected.value &&
    !["approved", "signed", "closed", "archived"].includes(selected.value.status) &&
    (runtimeEdit.value ||
      (canCreate.value &&
        (auth.role !== "user" ||
          [selected.value.created_by, selected.value.assigned_to].includes(auth.userId)))),
);
const inputSpecs = computed(() =>
  runtimeEdit.value
    ? fields.devices.filter((f) =>
        ["online_status", "calibration_status", "calibration_expires_at", "capacity"].includes(
          f.key,
        ),
      )
    : fields[kind.value],
);
let timer: ReturnType<typeof setTimeout> | undefined;

async function load() {
  loading.value = true;
  try {
    const settings = await supervisionApi.settings();
    enabled.value = settings.data.data.enabled;
    if (!enabled.value) return;
    const result = await supervisionApi.list(kind.value, {
      page: page.value,
      size: 20,
      keyword: keyword.value || undefined,
      region_id: region.value || undefined,
    });
    rows.value = result.data.data.items;
    total.value = result.data.data.total;
    if (route.query.record)
      selected.value = (await supervisionApi.get(kind.value, String(route.query.record))).data.data;
    else if (selected.value)
      selected.value = rows.value.find((x) => x.id === selected.value?.id) || null;
    await loadOptions();
  } catch {
    /* API reports errors; disabled organizations show the setup state. */
  } finally {
    loading.value = false;
  }
}
async function loadOptions() {
  if (["admin", "user", "expert"].includes(auth.role))
    options.value.assignees = (await supervisionApi.assignees()).data.data;
  const allowed: SupervisionKind[] = ["regions", "devices"];
  if (["admin", "user", "expert", "platform_operator"].includes(auth.role))
    allowed.push("enterprises", "risk-cases", "sampling-plans", "samples");
  const keys: Record<string, string> = { "risk-cases": "cases", "sampling-plans": "plans" };
  await Promise.allSettled(
    allowed.map(async (k) => {
      const result = await supervisionApi.list(k, { size: 200 });
      options.value[keys[k] || k] = result.data.data.items
        .filter((x) => !["inactive", "archived"].includes(x.status))
        .map((x) => ({ value: x.id, label: `${x.code} · ${x.name}` }));
    }),
  );
  if (["admin", "user", "expert", "platform_operator"].includes(auth.role)) {
    const catalog = (await productMasterApi.catalog(true)).data.data;
    options.value.products = catalog.product_skus
      .filter((x) => x.is_active)
      .map((x) => ({ value: x.id, label: `${x.code} · ${x.name}` }));
    options.value.batches = catalog.product_batches
      .filter((x) => x.is_active)
      .map((x) => ({
        value: x.id,
        label: x.name && x.name !== x.batch_no ? `${x.batch_no} · ${x.name}` : x.batch_no,
        product_sku_id: x.product_sku_id,
      }));
    const standards = await http.get<any>("/v1/inspection-standards", {
      params: { size: 200 },
      suppressErrorToast: true,
    });
    options.value.standards = (standards.data.data.items || [])
      .filter((x: any) => x.is_active)
      .map((x: any) => ({ value: x.id, label: x.name }));
  }
  if (["user", "expert", "platform_operator"].includes(auth.role)) {
    const result = (await taskApi.list({ page: 1, size: 200 })).data.data;
    options.value.tasks = result.items.map((x) => ({
      value: x.id,
      label: `${x.product_name || x.product_id} · ${x.id.slice(-8)}`,
    }));
  }
}
function openCreate() {
  editing.value = false;
  name.value = "";
  code.value = "";
  form.value = structuredClone(defaults[kind.value]);
  dialog.value = true;
}
function openEdit() {
  if (!selected.value) return;
  editing.value = true;
  name.value = selected.value.name;
  code.value = selected.value.code;
  form.value = cleanFields(selected.value.data, inputSpecs.value);
  dialog.value = true;
}
async function save() {
  if (!code.value.trim() || !name.value.trim()) {
    ElMessage.warning("请填写编号和名称");
    return;
  }
  saving.value = true;
  try {
    const data = cleanFields(form.value, inputSpecs.value);
    let result;
    if (editing.value && selected.value)
      result = runtimeEdit.value
        ? await supervisionApi.runtime(selected.value.id, data)
        : await supervisionApi.update(kind.value, selected.value.id, {
            version: selected.value.version,
            name: name.value,
            data,
          });
    else
      result = await supervisionApi.create(kind.value, {
        code: code.value,
        name: name.value,
        data,
      });
    selected.value = result.data.data as SupervisionRecord;
    dialog.value = false;
    ElMessage.success("已保存");
    await load();
  } finally {
    saving.value = false;
  }
}
async function enable() {
  await supervisionApi.enable(true);
  await load();
}
async function select(row: SupervisionRecord) {
  selected.value = row;
  run.value = null;
  await router.replace({ query: { record: row.id } });
}
async function analyze(operation: string) {
  if (!selected.value) return;
  if (timer) clearTimeout(timer);
  run.value = (
    await supervisionApi.run(kind.value, selected.value.id, selected.value.version, operation)
  ).data.data;
  await poll();
}
async function poll() {
  if (!run.value) return;
  run.value = (await supervisionApi.runStatus(run.value.id)).data.data;
  if (["queued", "running"].includes(run.value.status)) timer = setTimeout(poll, 2500);
  else await load();
}
async function retryRun() {
  if (!run.value) return;
  await supervisionApi.retry(run.value.id);
  await poll();
}
async function cancelRun() {
  if (!run.value) return;
  await supervisionApi.cancel(run.value.id);
  await poll();
}
async function submit(operation: string) {
  if (!selected.value) return;
  await supervisionApi.review(kind.value, selected.value.id, selected.value.version, operation);
  ElMessage.success("已提交，其他专家可在质监工作台处理");
  await load();
}
async function archive(status: string) {
  if (!selected.value) return;
  await supervisionApi.update(kind.value, selected.value.id, {
    version: selected.value.version,
    status,
  });
  await load();
}
async function credential() {
  if (!selected.value) return;
  await ElMessageBox.confirm("生成后旧连接凭据立即失效。新凭据只显示一次。", "更新设备连接");
  const token = (await supervisionApi.connection(selected.value.id)).data.data.token;
  await ElMessageBox.alert(token, "设备连接凭据", {
    confirmButtonText: "已保存",
    closeOnClickModal: false,
  });
}
async function feedback() {
  if (!selected.value) return;
  const result = await ElMessageBox.prompt(
    "登记完整检测或实际处置结果。新证据会标记为需要重评估。",
    "补充反馈",
    { inputType: "textarea", inputValidator: (x: string) => !!x?.trim() || "请填写反馈" },
  );
  await supervisionApi.feedback(kind.value, selected.value.id, {
    version: selected.value.version,
    outcome: "new_evidence",
    text: result.value,
    occurred_at: new Date().toISOString(),
  });
  await load();
}
async function reassess() {
  if (!selected.value) return;
  const created = (await supervisionApi.reassessment(selected.value.id)).data.data;
  await select(created);
  await load();
}
function display(f: any, value: any): string {
  if (value == null || value === "") return "未登记";
  if (f.type === "date") return formatServerDateTime(String(value));
  if (f.type === "select")
    return (Array.isArray(value) ? value : [value])
      .map((v) => options.value[f.options]?.find((x) => x.value === v)?.label || v)
      .join("、");
  if (Array.isArray(value)) return value.join("、");
  return String(value);
}
watch(kind, () => {
  if (timer) clearTimeout(timer);
  run.value = null;
  selected.value = null;
  page.value = 1;
  load();
});
onMounted(load);
onUnmounted(() => {
  if (timer) clearTimeout(timer);
});
</script>
<template>
  <main class="supervision-page" v-loading="loading">
    <SupervisionModuleHeader
      v-if="moduleMeta"
      :index="moduleMeta.index"
      :code="moduleMeta.code"
      :title="title"
      :agent-name="moduleMeta.agentName"
      :tone="moduleMeta.tone"
      :description="moduleMeta.description"
      :principle="moduleMeta.principle"
    >
      <template #actions>
        <el-button
          v-if="enabled && canCreate && ['regions', 'risk-cases'].includes(kind)"
          @click="importDialog = true"
          >文件导入</el-button
        >
        <el-button v-if="enabled && canCreate" type="primary" @click="openCreate"
          >新增{{ title }}</el-button
        >
      </template>
    </SupervisionModuleHeader>
    <header v-else class="page-head">
      <div>
        <p class="context-label">质量监督 · 业务资料</p>
        <h1>{{ title }}</h1>
      </div>
      <div class="action-bar">
        <el-button
          v-if="enabled && canCreate && ['regions', 'risk-cases'].includes(kind)"
          @click="importDialog = true"
          >文件导入</el-button
        ><el-button v-if="enabled && canCreate" type="primary" @click="openCreate"
          >新增{{
            title === "地区字典" ? "地区" : title === "设备资源" ? "设备" : title
          }}</el-button
        >
      </div>
    </header>
    <SupervisionAgentRail v-if="moduleMeta" class="agent-navigation" />
    <el-result
      v-if="!enabled"
      icon="info"
      title="质监业务尚未启用"
      sub-title="启用后，可登记风险线索、设备测量与抽查计划。"
      ><template #extra
        ><el-button v-if="auth.role === 'admin'" type="primary" @click="enable"
          >为当前组织启用</el-button
        ><span v-else>请联系组织管理员启用</span></template
      ></el-result
    >
    <template v-else>
      <div class="filter-bar">
        <el-input
          v-model="keyword"
          placeholder="按名称搜索"
          clearable
          @keyup.enter="
            page = 1;
            load();
          "
        /><el-select v-model="region" placeholder="全部地区" clearable filterable
          ><el-option
            v-for="o in options.regions"
            :key="o.value"
            :label="o.label"
            :value="o.value" /></el-select
        ><el-button
          @click="
            page = 1;
            load();
          "
          >查询</el-button
        ><el-button @click="load">刷新</el-button>
      </div>
      <div class="record-grid" :class="{ 'has-detail': selected }">
        <section class="records-table">
          <el-table
            :data="rows"
            highlight-current-row
            empty-text="暂无记录，可新增或导入业务资料"
            @row-click="select"
            ><el-table-column prop="code" label="编号" min-width="100" /><el-table-column
              prop="name"
              label="名称"
              min-width="160" /><el-table-column label="状态" width="110"
              ><template #default="{ row }"
                ><el-tag
                  size="small"
                  :type="
                    ['awaiting_evidence', 'inactive'].includes(row.status) ? 'warning' : 'info'
                  "
                  >{{ STATUS_LABELS[row.status] || row.status }}</el-tag
                ></template
              ></el-table-column
            ><el-table-column prop="version" label="版本" width="60" /></el-table
          ><el-pagination
            v-model:current-page="page"
            :total="total"
            :page-size="20"
            layout="prev, pager, next"
            @current-change="load"
          />
        </section>
        <aside v-if="selected" class="record-detail">
          <div class="detail-title">
            <div>
              <h2>{{ selected.name }}</h2>
              <span>{{ selected.code }} · 版本 {{ selected.version }}</span>
            </div>
            <el-button
              text
              @click="
                selected = null;
                router.replace({ query: {} });
              "
              >收起</el-button
            >
          </div>
          <div class="action-bar">
            <el-button
              v-if="kind === 'risk-cases' && ['user', 'expert'].includes(auth.role)"
              size="small"
              @click="reassess"
              >新增重评估版本</el-button
            >
            <el-button
              v-if="canEdit && kind === 'risk-cases' && auth.role === 'expert'"
              size="small"
              @click="manualDialog = true"
              >人工研判</el-button
            >
            <el-button v-if="canEdit" size="small" @click="openEdit">{{
              runtimeEdit ? "更新运行情况" : "编辑与补证"
            }}</el-button>
            <template v-if="canEdit && kind === 'risk-cases'"
              ><el-button size="small" type="primary" @click="analyze('risk_monitoring')"
                >启动协同研判</el-button
              ><el-button v-if="selected.data.analysis" size="small" @click="submit('risk.review')"
                >提交风险复核</el-button
              ></template
            >
            <template v-if="canEdit && kind === 'sampling-plans' && auth.role === 'expert'"
              ><el-button size="small" type="primary" @click="analyze('sampling')"
                >生成抽查方案</el-button
              ><el-button
                v-if="selected.data.analysis?.status === 'completed'"
                size="small"
                @click="submit('sampling.approve')"
                >提交计划批准</el-button
              ></template
            >
            <template v-if="canEdit && kind === 'inspection-sessions'"
              ><el-button
                size="small"
                @click="
                  router.push({
                    path: '/app/tasks/' + selected.data.task_id,
                    query: { session: selected.id },
                  })
                "
                >测量与检测任务</el-button
              ><el-button size="small" type="primary" @click="analyze('laboratory')"
                >分析检测过程</el-button
              ><el-button
                v-if="selected.data.analysis"
                size="small"
                @click="submit('result.review')"
                >提交结果复核</el-button
              ><el-button
                v-if="selected.data.analysis"
                size="small"
                @click="submit('result.signoff')"
                >提交结果签发</el-button
              ></template
            >
            <el-button
              v-if="kind === 'devices' && ['admin', 'app_developer'].includes(auth.role)"
              size="small"
              @click="credential"
              >更新连接凭据</el-button
            >
            <template
              v-if="
                canEdit &&
                ['regions', 'enterprises', 'devices', 'baselines', 'exposures'].includes(kind) &&
                !runtimeEdit
              "
              ><el-button
                size="small"
                @click="archive(selected.status === 'active' ? 'inactive' : 'active')"
                >{{ selected.status === "active" ? "停用" : "启用" }}</el-button
              ><el-button size="small" @click="archive('archived')">归档</el-button></template
            >
            <el-button
              v-if="
                ['risk-cases', 'inspection-sessions'].includes(kind) &&
                ['user', 'expert'].includes(auth.role)
              "
              size="small"
              @click="feedback"
              >结果反馈</el-button
            >
          </div>
          <el-alert
            v-if="selected.data.knowledge_status === 'needs_reassessment'"
            type="warning"
            title="依据已发生变化，需要重评估"
            :closable="false"
          />
          <div v-if="run" class="run-status">
            <el-tag>{{ STATUS_LABELS[run.status] || run.status }}</el-tag
            ><span>{{ run.error || "分析记录已保存，可刷新查看进度" }}</span
            ><el-button v-if="run.status === 'failed' && run.iteration < 2" text @click="retryRun"
              >重试</el-button
            ><el-button v-if="['running', 'queued'].includes(run.status)" text @click="cancelRun"
              >取消</el-button
            >
          </div>
          <SupervisionAssessment
            v-if="selected.data.analysis"
            :output="selected.data.analysis"
            :review-status="selected.status"
          />
          <el-descriptions :column="1" border class="data-details"
            ><template v-for="f in fields[kind]" :key="f.key"
              ><el-descriptions-item v-if="f.type !== 'array'" :label="f.label">{{
                display(f, selected.data[f.key])
              }}</el-descriptions-item></template
            ></el-descriptions
          >
          <section
            v-for="f in fields[kind].filter((x) => x.type === 'array')"
            :key="f.key"
            class="detail-section"
          >
            <h3>{{ f.label }}</h3>
            <el-empty
              v-if="!selected.data[f.key]?.length"
              description="尚未登记"
              :image-size="32"
            />
            <div v-for="(item, i) in selected.data[f.key] || []" :key="i" class="evidence-block">
              <template v-for="field in f.fields || []" :key="field.key"
                ><p v-if="field.type !== 'array'">
                  <span>{{ field.label }}：</span>{{ display(field, item[field.key]) }}
                </p>
                <div v-else>
                  <p v-for="(t, ti) in item[field.key] || []" :key="ti">
                    {{ t.item }} · {{ t.unit }} · {{ t.method }} ·
                    {{ t.standard_ref || "未登记标准" }}
                  </p>
                </div></template
              >
            </div>
          </section>
          <section v-if="selected.data.review_decisions?.length">
            <h3>复核与批准记录</h3>
            <p v-for="(r, i) in selected.data.review_decisions" :key="i">
              {{ OP_LABELS[r.operation] }} · {{ r.decision === "accept" ? "通过" : r.decision }} ·
              {{ r.comment }}
            </p>
          </section>
        </aside>
      </div>
    </template>
    <el-dialog
      v-model="dialog"
      :title="(editing ? '编辑' : '新增') + title"
      width="min(860px, 94vw)"
      :close-on-click-modal="false"
      ><el-form label-position="top"
        ><div class="identity-fields">
          <el-form-item label="编号" required
            ><el-input v-model="code" :disabled="editing" /></el-form-item
          ><el-form-item label="名称" required><el-input v-model="name" /></el-form-item>
        </div>
        <SupervisionFields v-model="form" :specs="inputSpecs" :options="options" /></el-form
      ><template #footer
        ><el-button @click="dialog = false">取消</el-button
        ><el-button type="primary" :loading="saving" @click="save">保存</el-button></template
      ></el-dialog
    >
    <el-dialog v-model="manualDialog" title="人工舆情风险研判" width="min(560px,94vw)"
      ><el-form label-position="top"
        ><el-form-item label="风险等级"
          ><el-select v-model="manualLevel"
            ><el-option
              v-for="(label, value) in {
                low: '低',
                medium: '中',
                high: '高',
                critical: '严重',
                unknown: '未知',
              }"
              :key="value"
              :value="value"
              :label="label" /></el-select></el-form-item
        ><el-form-item label="引用真实来源证据"
          ><el-select v-model="manualEvidence" multiple
            ><el-option
              v-for="e in (selected?.data.evidence || []).filter(
                (x: any) => x.nature === 'observed',
              )"
              :key="e.evidence_id"
              :value="e.evidence_id"
              :label="e.evidence_id + ' · ' + e.source_id" /></el-select></el-form-item
        ><el-form-item label="判断依据与冲突处理说明"
          ><el-input v-model="manualReason" type="textarea" :rows="5" /></el-form-item></el-form
      ><template #footer
        ><el-button @click="manualDialog = false">取消</el-button
        ><el-button
          type="primary"
          :disabled="!manualEvidence.length || !manualReason.trim()"
          @click="saveManual"
          >保存并等待独立复核</el-button
        ></template
      ></el-dialog
    >
    <BulkImportDialog v-model="importDialog" :kind="kind" @imported="load" />
  </main>
</template>
<style scoped>
.supervision-page {
  max-width: 1520px;
  margin: 0 auto;
  padding: 18px 18px 40px;
}
.agent-navigation {
  margin: 16px 0 18px;
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}
.context-label {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin: 0 0 6px;
}
h1 {
  font-size: 24px;
  margin: 0;
}
h2 {
  font-size: 18px;
  margin: 0 0 5px;
}
h3 {
  font-size: 14px;
  margin: 20px 0 12px;
}
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  padding: 14px;
  border: 1px solid #dce6f0;
  border-radius: 13px;
  background: #fff;
  box-shadow: 0 7px 20px rgba(16, 42, 67, 0.04);
}
.filter-bar .el-input {
  max-width: 260px;
}
.filter-bar .el-select {
  width: 220px;
}
.record-grid {
  display: grid;
  gap: 20px;
}
.record-grid.has-detail {
  grid-template-columns: minmax(300px, 0.85fr) minmax(360px, 1.15fr);
}
.records-table {
  min-width: 0;
  overflow: hidden;
  padding: 10px 12px 16px;
  border: 1px solid #dce6f0;
  border-radius: 14px;
  background: #fff;
}
.el-pagination {
  margin-top: 18px;
}
.record-detail {
  min-width: 0;
  padding: 20px;
  border: 1px solid #dce6f0;
  border-top: 4px solid #0b63ce;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 10px 28px rgba(16, 42, 67, 0.06);
}
.detail-title {
  display: flex;
  justify-content: space-between;
}
.detail-title span {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.action-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 18px 0;
}
.action-bar .el-button + .el-button {
  margin-left: 0;
}
.data-details {
  margin-top: 20px;
}
.identity-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
.evidence-block {
  padding: 12px 14px;
  border-left: 2px solid var(--el-border-color);
  background: var(--el-fill-color-light);
  margin: 8px 0;
  overflow-wrap: anywhere;
}
.evidence-block p {
  margin: 6px 0;
  line-height: 1.5;
  font-size: 13px;
}
.evidence-block span {
  color: var(--el-text-color-secondary);
}
.run-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin: 12px 0;
}
@media (max-width: 1000px) {
  .record-grid.has-detail {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 640px) {
  .supervision-page {
    padding: 14px;
  }
  .filter-bar {
    flex-wrap: wrap;
  }
  .identity-fields {
    grid-template-columns: 1fr;
  }
  .record-detail {
    padding: 14px;
  }
}
</style>
