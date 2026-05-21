<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useInspectionSpecStore } from "@/stores/inspection_spec.store";
import type { InspectionSpec, InspectionSpecItemPayload, InspectionSpecPayload } from "@/types/governance.types";
import { ROLE_ADMIN, ROLE_PLATFORM_OPERATOR } from "@/constants/roles";
import { useAuthStore } from "@/stores/auth.store";

interface RuleForm {
  defect_type: string;
  severity: string;
  disposition: string;
  confidence_threshold: number;
  zone_name: string;
  max_count: number | null;
  description: string;
}

const store = useInspectionSpecStore();
const auth = useAuthStore();

const drawerOpen = ref(false);
const previewOpen = ref(false);
const editingId = ref("");
const previewing = ref<InspectionSpec | null>(null);
const scopeMode = ref<"org" | "global">("org");
const filters = reactive({
  productId: "",
  scope: "all" as "all" | "org" | "global",
});
const form = reactive({
  spec_code: "",
  name: "",
  version: "v1",
  product_id: "",
  required_image_count: 1,
  ai_gate_confidence_threshold: 0.72,
  ai_gate_evidence_threshold: 0.5,
  ai_gate_traceability_threshold: 0.5,
  auto_pass_enabled: false,
  is_active: true,
  items: [] as RuleForm[],
});

const canManageGlobal = computed(() => {
  const allRoles = [...auth.roles, auth.role].filter(Boolean);
  return allRoles.includes(ROLE_ADMIN);
});
const isReadonly = computed(() => {
  const allRoles = [...auth.roles, auth.role].filter(Boolean);
  return allRoles.includes(ROLE_PLATFORM_OPERATOR) && !allRoles.includes(ROLE_ADMIN);
});
const productOptions = computed(() =>
  Array.from(new Set(store.items.map((item) => item.product_id).filter(Boolean) as string[])).sort(),
);
const filteredItems = computed(() =>
  store.items.filter((item) => {
    const matchesProduct = !filters.productId || item.product_id === filters.productId;
    const matchesScope =
      filters.scope === "all" ||
      (filters.scope === "org" && Boolean(item.org_id)) ||
      (filters.scope === "global" && !item.org_id);
    return matchesProduct && matchesScope;
  }),
);
const totalRules = computed(() => filteredItems.value.reduce((sum, item) => sum + item.items.length, 0));
const activeCount = computed(() => filteredItems.value.filter((item) => item.is_active).length);
const autopassCount = computed(() => filteredItems.value.filter((item) => item.auto_pass_enabled).length);

function buildDefaultRule(): RuleForm {
  return {
    defect_type: "",
    severity: "major",
    disposition: "fail",
    confidence_threshold: 0.55,
    zone_name: "",
    max_count: 1,
    description: "",
  };
}

function resetForm() {
  editingId.value = "";
  scopeMode.value = "org";
  Object.assign(form, {
    spec_code: "",
    name: "",
    version: "v1",
    product_id: "",
    required_image_count: 1,
    ai_gate_confidence_threshold: 0.72,
    ai_gate_evidence_threshold: 0.5,
    ai_gate_traceability_threshold: 0.5,
    auto_pass_enabled: false,
    is_active: true,
    items: [buildDefaultRule()],
  });
}

function openCreate() {
  resetForm();
  drawerOpen.value = true;
}

function openPreview(row: InspectionSpec) {
  previewing.value = row;
  previewOpen.value = true;
}

function openEdit(row: InspectionSpec) {
  editingId.value = row.id;
  scopeMode.value = row.org_id ? "org" : "global";
  Object.assign(form, {
    spec_code: row.spec_code,
    name: row.name,
    version: row.version,
    product_id: row.product_id ?? "",
    required_image_count: row.required_image_count,
    ai_gate_confidence_threshold: row.ai_gate_confidence_threshold,
    ai_gate_evidence_threshold: row.ai_gate_evidence_threshold,
    ai_gate_traceability_threshold: row.ai_gate_traceability_threshold,
    auto_pass_enabled: row.auto_pass_enabled,
    is_active: row.is_active,
    items: row.items.map((item) => ({
      defect_type: item.defect_type,
      severity: item.severity,
      disposition: item.disposition,
      confidence_threshold: item.confidence_threshold,
      zone_name: item.zone_name ?? "",
      max_count: item.max_count ?? 1,
      description: item.description ?? "",
    })),
  });
  drawerOpen.value = true;
}

function buildDuplicateCode(row: InspectionSpec) {
  const suffix = `${Date.now()}`.slice(-4);
  return `${row.spec_code}-COPY-${suffix}`.slice(0, 64);
}

async function duplicateSpec(row: InspectionSpec) {
  const payload: InspectionSpecPayload = {
    org_id: row.org_id,
    spec_code: buildDuplicateCode(row),
    name: `${row.name}（副本）`,
    version: row.version,
    product_id: row.product_id,
    required_image_count: row.required_image_count,
    ai_gate_confidence_threshold: row.ai_gate_confidence_threshold,
    ai_gate_evidence_threshold: row.ai_gate_evidence_threshold,
    ai_gate_traceability_threshold: row.ai_gate_traceability_threshold,
    auto_pass_enabled: false,
    is_active: false,
    items: row.items.map((item) => ({
      defect_type: item.defect_type,
      severity: item.severity,
      disposition: item.disposition,
      confidence_threshold: item.confidence_threshold,
      zone_name: item.zone_name,
      max_count: item.max_count,
      description: item.description,
    })),
  };
  await store.createOne(payload);
  ElMessage.success("检测标准已复制为草稿副本");
}

function addRule() {
  form.items.push(buildDefaultRule());
}

function removeRule(index: number) {
  if (form.items.length <= 1) {
    ElMessage.warning("至少保留一条规则");
    return;
  }
  form.items.splice(index, 1);
}

function buildPayload(): InspectionSpecPayload {
  const items: InspectionSpecItemPayload[] = form.items.map((item) => ({
    defect_type: item.defect_type.trim(),
    severity: item.severity,
    disposition: item.disposition,
    confidence_threshold: Number(item.confidence_threshold),
    zone_name: item.zone_name.trim() || null,
    max_count: item.max_count || null,
    description: item.description.trim() || null,
  }));

  return {
    org_id: canManageGlobal.value && scopeMode.value === "global" ? null : (auth.orgId || ""),
    spec_code: form.spec_code.trim(),
    name: form.name.trim(),
    version: form.version.trim() || "v1",
    product_id: form.product_id.trim() || null,
    required_image_count: Number(form.required_image_count),
    ai_gate_confidence_threshold: Number(form.ai_gate_confidence_threshold),
    ai_gate_evidence_threshold: Number(form.ai_gate_evidence_threshold),
    ai_gate_traceability_threshold: Number(form.ai_gate_traceability_threshold),
    auto_pass_enabled: form.auto_pass_enabled,
    is_active: form.is_active,
    items,
  };
}

function validatePayload(payload: InspectionSpecPayload) {
  if (!payload.spec_code || !payload.name) {
    throw new Error("请填写标准编码和标准名称");
  }
  if (payload.items.some((item) => !item.defect_type)) {
    throw new Error("每条规则都需要填写缺陷类型");
  }
}

async function submit() {
  const payload = buildPayload();
  validatePayload(payload);

  if (editingId.value) {
    await store.updateOne(editingId.value, payload);
    ElMessage.success("检测标准已更新");
  } else {
    await store.createOne(payload);
    ElMessage.success("检测标准已创建");
  }
  drawerOpen.value = false;
}

async function remove(id: string) {
  await ElMessageBox.confirm("删除后将移除该标准及其规则项，是否继续？", "删除标准", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  });
  await store.removeOne(id);
  ElMessage.success("检测标准已删除");
}

function formatScope(row: InspectionSpec) {
  return row.org_id ? "组织" : "全局";
}

function resetFilters() {
  filters.productId = "";
  filters.scope = "all";
}

onMounted(() => {
  resetForm();
  store.fetchAll();
});
</script>

<template>
  <div class="flex flex-col gap-5">
    <section class="hero">
      <div>
        <p class="eyebrow">Inspection Governance</p>
        <h2>检测标准配置</h2>
        <p>维护缺陷判定标准、AI 门禁阈值和自动放行策略，支撑 `inspection_specs` 主链路。</p>
      </div>
      <el-button type="primary" @click="openCreate">新增标准</el-button>
    </section>

    <section class="metrics">
      <el-card shadow="never" class="metric-card">
        <span class="metric-label">筛选后标准</span>
        <strong class="metric-value">{{ filteredItems.length }}</strong>
      </el-card>
      <el-card shadow="never" class="metric-card">
        <span class="metric-label">启用标准</span>
        <strong class="metric-value">{{ activeCount }}</strong>
      </el-card>
      <el-card shadow="never" class="metric-card">
        <span class="metric-label">规则项总数</span>
        <strong class="metric-value">{{ totalRules }}</strong>
      </el-card>
      <el-card shadow="never" class="metric-card accent">
        <span class="metric-label">自动放行配置</span>
        <strong class="metric-value">{{ autopassCount }}</strong>
      </el-card>
    </section>

    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="card-header">
          <div>
            <h3>标准列表</h3>
            <p>支持全局标准与组织标准共存，默认按当前治理视角展示。</p>
          </div>
        </div>
      </template>

      <div class="filters">
        <el-select v-model="filters.productId" clearable placeholder="按产品线筛选" style="width: 220px">
          <el-option v-for="product in productOptions" :key="product" :label="product" :value="product" />
        </el-select>
        <el-segmented
          v-model="filters.scope"
          :options="[
            { label: '全部范围', value: 'all' },
            { label: '组织标准', value: 'org' },
            { label: '全局标准', value: 'global' },
          ]"
        />
        <el-button @click="resetFilters">重置</el-button>
      </div>

      <el-table :data="filteredItems" v-loading="store.loading">
        <el-table-column prop="spec_code" label="标准编码" min-width="160" />
        <el-table-column prop="name" label="标准名称" min-width="180" />
        <el-table-column prop="version" label="版本" width="100" />
        <el-table-column label="范围" width="100">
          <template #default="{ row }">
            <el-tag :type="row.org_id ? 'primary' : 'warning'">{{ formatScope(row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="product_id" label="产品线" min-width="120" />
        <el-table-column label="规则数" width="90">
          <template #default="{ row }">{{ row.items.length }}</template>
        </el-table-column>
        <el-table-column label="必需图片" width="100">
          <template #default="{ row }">{{ row.required_image_count }}</template>
        </el-table-column>
        <el-table-column label="自动放行" width="100">
          <template #default="{ row }">
            <el-tag :type="row.auto_pass_enabled ? 'success' : 'info'">
              {{ row.auto_pass_enabled ? "开启" : "关闭" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">
              {{ row.is_active ? "启用" : "停用" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button link @click="openPreview(row)">预览</el-button>
            <template v-if="!isReadonly">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link @click="duplicateSpec(row)">复制</el-button>
              <el-button link type="danger" @click="remove(row.id)">删除</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="previewOpen" title="标准详情预览" size="680px">
      <template v-if="previewing">
        <div class="preview-panel">
          <section class="preview-hero">
            <div>
              <p class="preview-code">{{ previewing.spec_code }}</p>
              <h3>{{ previewing.name }}</h3>
              <p class="preview-meta">
                {{ previewing.version }} · {{ formatScope(previewing) }} · {{ previewing.product_id || "未指定产品线" }}
              </p>
            </div>
            <div class="preview-tags">
              <el-tag :type="previewing.is_active ? 'success' : 'info'">{{ previewing.is_active ? "启用" : "停用" }}</el-tag>
              <el-tag :type="previewing.auto_pass_enabled ? 'success' : 'warning'">
                {{ previewing.auto_pass_enabled ? "自动放行开启" : "自动放行关闭" }}
              </el-tag>
            </div>
          </section>

          <el-card shadow="never" class="preview-section">
            <template #header>AI 门禁参数</template>
            <div class="preview-grid">
              <div class="preview-stat">
                <span>必需图片数</span>
                <strong>{{ previewing.required_image_count }}</strong>
              </div>
              <div class="preview-stat">
                <span>置信度阈值</span>
                <strong>{{ previewing.ai_gate_confidence_threshold.toFixed(4) }}</strong>
              </div>
              <div class="preview-stat">
                <span>证据阈值</span>
                <strong>{{ previewing.ai_gate_evidence_threshold.toFixed(4) }}</strong>
              </div>
              <div class="preview-stat">
                <span>溯源阈值</span>
                <strong>{{ previewing.ai_gate_traceability_threshold.toFixed(4) }}</strong>
              </div>
            </div>
          </el-card>

          <el-card shadow="never" class="preview-section">
            <template #header>规则项清单</template>
            <el-table :data="previewing.items" size="small">
              <el-table-column prop="defect_type" label="缺陷类型" min-width="140" />
              <el-table-column prop="severity" label="严重度" width="100" />
              <el-table-column prop="disposition" label="处置方式" width="140" />
              <el-table-column label="阈值" width="110">
                <template #default="{ row }">{{ row.confidence_threshold.toFixed(2) }}</template>
              </el-table-column>
              <el-table-column prop="zone_name" label="区域" width="120" />
              <el-table-column prop="max_count" label="最大数量" width="100" />
              <el-table-column prop="description" label="说明" min-width="180" />
            </el-table>
          </el-card>
        </div>
      </template>
      <template #footer>
        <el-button @click="previewOpen = false">关闭</el-button>
        <el-button
          type="primary"
          @click="
            previewing && (previewOpen = false, openEdit(previewing))
          "
        >
          转到编辑
        </el-button>
      </template>
    </el-drawer>

    <el-drawer v-model="drawerOpen" :title="editingId ? '编辑检测标准' : '新增检测标准'" size="760px">
      <div class="drawer-body">
        <el-card shadow="never" class="drawer-section">
          <template #header>标准主信息</template>
          <el-form label-position="top" class="grid-form">
            <el-form-item label="标准编码">
              <el-input v-model="form.spec_code" placeholder="如 SCREW-A-2026-V1" />
            </el-form-item>
            <el-form-item label="标准名称">
              <el-input v-model="form.name" placeholder="请输入标准名称" />
            </el-form-item>
            <el-form-item label="版本">
              <el-input v-model="form.version" placeholder="v1" />
            </el-form-item>
            <el-form-item label="产品线">
              <el-input v-model="form.product_id" placeholder="如 screw-line-a" />
            </el-form-item>
            <el-form-item label="标准范围">
              <el-segmented
                v-model="scopeMode"
                :options="[
                  { label: '组织标准', value: 'org' },
                  { label: '全局标准', value: 'global', disabled: !canManageGlobal },
                ]"
              />
            </el-form-item>
            <el-form-item label="必需图片数">
              <el-input-number v-model="form.required_image_count" :min="1" :max="20" />
            </el-form-item>
            <el-form-item label="置信度阈值">
              <el-input-number v-model="form.ai_gate_confidence_threshold" :min="0" :max="1" :step="0.01" :precision="4" />
            </el-form-item>
            <el-form-item label="证据阈值">
              <el-input-number v-model="form.ai_gate_evidence_threshold" :min="0" :max="1" :step="0.01" :precision="4" />
            </el-form-item>
            <el-form-item label="溯源阈值">
              <el-input-number v-model="form.ai_gate_traceability_threshold" :min="0" :max="1" :step="0.01" :precision="4" />
            </el-form-item>
            <el-form-item label="自动放行">
              <el-switch v-model="form.auto_pass_enabled" active-text="开启" inactive-text="关闭" />
            </el-form-item>
            <el-form-item label="状态">
              <el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" />
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="never" class="drawer-section">
          <template #header>
            <div class="rules-header">
              <div>
                <h4>规则项</h4>
                <p>定义缺陷类型、处置方式和门限。更新时会整包替换。</p>
              </div>
              <el-button plain @click="addRule">新增规则</el-button>
            </div>
          </template>

          <div class="rule-list">
            <div v-for="(item, index) in form.items" :key="index" class="rule-card">
              <div class="rule-card-header">
                <span>规则 {{ index + 1 }}</span>
                <el-button link type="danger" @click="removeRule(index)">删除</el-button>
              </div>
              <div class="rule-grid">
                <el-input v-model="item.defect_type" placeholder="缺陷类型，如 scratch" />
                <el-select v-model="item.severity" placeholder="严重度">
                  <el-option label="critical" value="critical" />
                  <el-option label="major" value="major" />
                  <el-option label="minor" value="minor" />
                </el-select>
                <el-select v-model="item.disposition" placeholder="处置方式">
                  <el-option label="fail" value="fail" />
                  <el-option label="manual_required" value="manual_required" />
                  <el-option label="pass" value="pass" />
                  <el-option label="uncertain" value="uncertain" />
                </el-select>
                <el-input-number v-model="item.confidence_threshold" :min="0" :max="1" :step="0.01" :precision="4" />
                <el-input v-model="item.zone_name" placeholder="区域名称，可选" />
                <el-input-number v-model="item.max_count" :min="1" :max="999" />
                <el-input v-model="item.description" class="rule-desc" placeholder="规则说明，可选" />
              </div>
            </div>
          </div>
        </el-card>
      </div>

      <template #footer>
        <el-button @click="drawerOpen = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>

.hero {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 16px;
  padding: 20px 24px;
 border-radius: 24px;
  background:
    radial-gradient(circle at top left, rgba(14, 116, 144, 0.18), transparent 34%),
    linear-gradient(135deg, #10263d 0%, #1b3a5c 52%, #2563a8 100%);
  color: #f8fafc;
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(224, 242, 254, 0.86);
}

.hero h2 {
  margin: 0;
  font-size: 28px;
}

.hero p:last-child {
  margin: 8px 0 0;
  max-width: 680px;
  color: rgba(226, 232, 240, 0.9);
}

.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.metric-card {
 border-radius: 18px;
}

.metric-card.accent {
  background: linear-gradient(135deg, #ecfeff 0%, #dbeafe 100%);
}

.metric-label {
  display: block;
  color: #64748b;
  font-size: 13px;
}

.metric-value {
  display: block;
  margin-top: 10px;
  color: #1b3a5c;
  font-size: 30px;
  font-weight: 700;
}

.table-card :deep(.el-card__header) {
  padding-bottom: 8px;
}

.filters {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.card-header h3,
.rules-header h4 {
  margin: 0;
  color: #1b3a5c;
}

.card-header p,
.rules-header p {
  margin: 6px 0 0;
  color: #64748b;
}

.drawer-body {
  display: grid;
  gap: 16px;
}

.preview-panel {
  display: grid;
  gap: 16px;
}

.preview-hero {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px;
 border-radius: 20px;
  background: linear-gradient(135deg, #eff6ff 0%, #ecfeff 100%);
}

.preview-code {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #0e7490;
}

.preview-hero h3 {
  margin: 0;
  color: #1b3a5c;
}

.preview-meta {
  margin: 8px 0 0;
  color: #64748b;
}

.preview-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: end;
}

.preview-section {
 border-radius: 18px;
}

.preview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.preview-stat {
  padding: 14px;
 border-radius: 16px;
  background: #f8fafc;
}

.preview-stat span {
  display: block;
  color: #64748b;
  font-size: 12px;
}

.preview-stat strong {
  display: block;
  margin-top: 8px;
  color: #1b3a5c;
  font-size: 20px;
}

.drawer-section {
 border-radius: 18px;
}

.grid-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}

.rules-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.rule-list {
  display: grid;
  gap: 12px;
}

.rule-card {
  padding: 16px;
 border: 1px solid #dbe2ea;
 border-radius: 16px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbfd 100%);
}

.rule-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  color: #1b3a5c;
  font-weight: 600;
}

.rule-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.rule-desc {
  grid-column: 1 / -1;
}

@media (max-width: 1200px) {
  .metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .hero {
    align-items: start;
    flex-direction: column;
  }

  .metrics,
  .grid-form,
  .rule-grid,
  .preview-grid {
    grid-template-columns: 1fr;
  }

  .preview-hero {
    flex-direction: column;
  }
}
</style>
