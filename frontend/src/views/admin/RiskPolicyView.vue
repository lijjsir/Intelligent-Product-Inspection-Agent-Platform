<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Plus, RefreshRight } from "@element-plus/icons-vue";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { useAuthStore } from "@/stores/auth.store";

const auth = useAuthStore();
const rows = ref<any[]>([]);
const loading = ref(false);
const saving = ref(false);
const dialog = ref(false);
const form = reactive({
  code: "RISK-GENERAL",
  name: "通用质量风险等级规则",
  version: "v1",
  evidenceMinimum: 80,
  severityLow: 1,
  severityMedium: 2,
  severityHigh: 3,
  severityCritical: 4,
  likelihoodRare: 1,
  likelihoodPossible: 2,
  likelihoodLikely: 3,
  exposureLimited: 1,
  exposureRegional: 2,
  exposureWidespread: 3,
  mediumMin: 3,
  highMin: 5,
  criticalMin: 8,
  maximumScore: 12,
  conflictReview: true,
  safetyReview: true,
});

function nextVersion(value: string) {
  const match = String(value || "").match(/^(.*?)(\d+)$/);
  return match ? `${match[1]}${Number(match[2]) + 1}` : `${value || "v"}2`;
}

function hydrateFromPolicy(policy?: any) {
  const rules = policy?.rules || {};
  Object.assign(form, {
    code: policy?.code || "RISK-GENERAL",
    name: policy?.name || "通用质量风险等级规则",
    version: policy ? nextVersion(policy.version) : "v1",
    evidenceMinimum: Math.round(Number(rules.evidence_sufficiency?.minimum ?? 0.8) * 100),
    severityLow: Number(rules.severity?.low ?? 1),
    severityMedium: Number(rules.severity?.medium ?? 2),
    severityHigh: Number(rules.severity?.high ?? 3),
    severityCritical: Number(rules.severity?.critical ?? 4),
    likelihoodRare: Number(rules.likelihood?.rare ?? 1),
    likelihoodPossible: Number(rules.likelihood?.possible ?? 2),
    likelihoodLikely: Number(rules.likelihood?.likely ?? 3),
    exposureLimited: Number(rules.exposure?.limited ?? 1),
    exposureRegional: Number(rules.exposure?.regional ?? 2),
    exposureWidespread: Number(rules.exposure?.widespread ?? 3),
    mediumMin: Number(rules.level_mapping?.medium?.[0] ?? 3),
    highMin: Number(rules.level_mapping?.high?.[0] ?? 5),
    criticalMin: Number(rules.level_mapping?.critical?.[0] ?? 8),
    maximumScore: Number(rules.level_mapping?.critical?.[1] ?? 12),
    conflictReview: Boolean(rules.manual_review?.on_conflict ?? true),
    safetyReview: Boolean(rules.manual_review?.on_safety_baseline ?? true),
  });
}

async function load() {
  loading.value = true;
  try {
    rows.value = (await qualityRiskApi.policies()).data.data;
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  hydrateFromPolicy(rows.value[0]);
  dialog.value = true;
}

async function save() {
  if (!form.code.trim() || !form.name.trim() || !form.version.trim()) {
    ElMessage.warning("请填写政策编码、名称和版本");
    return;
  }
  if (!(form.mediumMin < form.highMin && form.highMin < form.criticalMin && form.criticalMin <= form.maximumScore)) {
    ElMessage.warning("风险等级起始分必须依次递增，严重风险起始分不能超过最高分");
    return;
  }
  saving.value = true;
  try {
    await qualityRiskApi.createPolicy({
      code: form.code,
      name: form.name,
      version: form.version,
      rules: {
        severity: {
          low: form.severityLow,
          medium: form.severityMedium,
          high: form.severityHigh,
          critical: form.severityCritical,
        },
        likelihood: {
          rare: form.likelihoodRare,
          possible: form.likelihoodPossible,
          likely: form.likelihoodLikely,
        },
        exposure: {
          limited: form.exposureLimited,
          regional: form.exposureRegional,
          widespread: form.exposureWidespread,
        },
        evidence_sufficiency: { minimum: form.evidenceMinimum / 100 },
        level_mapping: {
          low: [0, form.mediumMin - 1],
          medium: [form.mediumMin, form.highMin - 1],
          high: [form.highMin, form.criticalMin - 1],
          critical: [form.criticalMin, form.maximumScore],
        },
        manual_review: {
          on_conflict: form.conflictReview,
          on_safety_baseline: form.safetyReview,
        },
      },
    });
    dialog.value = false;
    ElMessage.success("风险等级规则草稿已创建，需由管理员发布后生效");
    await load();
  } finally {
    saving.value = false;
  }
}

async function publish(row: any) {
  await qualityRiskApi.publishPolicy(row.id);
  ElMessage.success("风险等级规则已发布");
  await load();
}

function thresholdSummary(row: any) {
  const mapping = row.rules?.level_mapping || {};
  return `中 ${mapping.medium?.[0] ?? "-"} · 高 ${mapping.high?.[0] ?? "-"} · 严重 ${mapping.critical?.[0] ?? "-"}`;
}

onMounted(load);
</script>

<template>
  <main class="policy-page">
    <header class="policy-hero">
      <div><p>RISK LEVEL RULES</p><h1>风险等级规则</h1><span>只用于把投诉、舆情、抽查等多源线索划分为低、中、高或严重风险，不参与产品合格与否的判定。</span></div>
      <div class="hero-actions"><el-button :icon="RefreshRight" @click="load">刷新</el-button><el-button v-if="['admin','expert'].includes(auth.role)" type="primary" :icon="Plus" @click="openCreate">新建等级规则版本</el-button></div>
    </header>

    <section class="policy-flow" aria-label="风险等级规则使用流程"><div><b>1</b><span>专家设置分级口径</span></div><i>→</i><div><b>2</b><span>保存为草稿</span></div><i>→</i><div><b>3</b><span>管理员复核发布</span></div><i>→</i><div><b>4</b><span>风险研判引用版本</span></div></section>

    <section class="table-card">
      <el-table :data="rows" v-loading="loading">
        <el-table-column label="政策"><template #default="{ row }"><div class="primary-cell"><strong>{{ row.name }}</strong><span>{{ row.code }}</span></div></template></el-table-column>
        <el-table-column prop="version" label="版本" width="90" />
        <el-table-column label="证据门槛" width="120"><template #default="{ row }">{{ Math.round(Number(row.rules?.evidence_sufficiency?.minimum || 0) * 100) }}%</template></el-table-column>
        <el-table-column label="等级起始分" min-width="210"><template #default="{ row }">{{ thresholdSummary(row) }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'published' ? 'success' : 'info'">{{ row.status === 'published' ? '已发布' : row.status === 'superseded' ? '已替代' : '草稿' }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="100"><template #default="{ row }"><el-button v-if="auth.role === 'admin' && row.status === 'draft'" link @click="publish(row)">发布</el-button></template></el-table-column>
      </el-table>
    </section>

    <el-dialog v-model="dialog" title="新建风险等级规则版本" width="min(880px, 95vw)" top="3vh" :close-on-click-modal="false">
      <el-form label-position="top">
        <section class="form-section"><h3>基本信息</h3><div class="form-grid three"><el-form-item label="政策编码" required><el-input v-model="form.code" /></el-form-item><el-form-item label="政策名称" required><el-input v-model="form.name" /></el-form-item><el-form-item label="新版本" required><el-input v-model="form.version" /></el-form-item></div></section>
        <section class="form-section"><div class="section-title"><h3>证据与人工复核门槛</h3><span>先过证据门槛，再讨论风险等级</span></div><div class="form-grid three"><el-form-item class="evidence-field" label="最低证据充分度"><el-input-number v-model="form.evidenceMinimum" :min="0" :max="100" controls-position="right" /><span class="unit">%</span></el-form-item><el-form-item label="存在关键证据冲突"><el-switch v-model="form.conflictReview" active-text="必须人工复核" /></el-form-item><el-form-item label="触及安全底线"><el-switch v-model="form.safetyReview" active-text="必须人工复核" /></el-form-item></div></section>
        <section class="form-section"><div class="section-title"><h3>三个评分维度</h3><span>分值由专家定义，正式研判只允许引用已发布版本</span></div><div class="score-groups"><fieldset><legend>严重度</legend><label>低 <el-input-number v-model="form.severityLow" :min="0" :controls="false" /></label><label>中 <el-input-number v-model="form.severityMedium" :min="0" :controls="false" /></label><label>高 <el-input-number v-model="form.severityHigh" :min="0" :controls="false" /></label><label>严重 <el-input-number v-model="form.severityCritical" :min="0" :controls="false" /></label></fieldset><fieldset><legend>发生可能性</legend><label>少见 <el-input-number v-model="form.likelihoodRare" :min="0" :controls="false" /></label><label>可能 <el-input-number v-model="form.likelihoodPossible" :min="0" :controls="false" /></label><label>较可能 <el-input-number v-model="form.likelihoodLikely" :min="0" :controls="false" /></label></fieldset><fieldset><legend>影响范围</legend><label>有限 <el-input-number v-model="form.exposureLimited" :min="0" :controls="false" /></label><label>区域性 <el-input-number v-model="form.exposureRegional" :min="0" :controls="false" /></label><label>广泛 <el-input-number v-model="form.exposureWidespread" :min="0" :controls="false" /></label></fieldset></div></section>
        <section class="form-section"><div class="section-title"><h3>风险等级分界</h3><span>达到相应起始分后进入该等级</span></div><div class="form-grid four"><el-form-item label="中风险起始分"><el-input-number v-model="form.mediumMin" :min="1" :controls="false" /></el-form-item><el-form-item label="高风险起始分"><el-input-number v-model="form.highMin" :min="1" :controls="false" /></el-form-item><el-form-item label="严重风险起始分"><el-input-number v-model="form.criticalMin" :min="1" :controls="false" /></el-form-item><el-form-item label="最高分"><el-input-number v-model="form.maximumScore" :min="1" :controls="false" /></el-form-item></div></section>
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存草稿</el-button></template>
    </el-dialog>
  </main>
</template>

<style scoped>
.policy-page{max-width:1320px;margin:0 auto;padding:24px;color:#172b3a}.policy-hero{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;padding:28px;border:1px solid #d8e5ec;border-radius:16px;background:linear-gradient(120deg,#f2f8fb,#fff)}.policy-hero p{margin:0 0 8px;color:#a8560c;font:700 11px ui-monospace,monospace;letter-spacing:.14em}.policy-hero h1{margin:0;font-size:34px}.policy-hero span{display:block;max-width:760px;margin-top:8px;color:#62798a;line-height:1.6}.hero-actions{display:flex;gap:8px}.policy-flow{display:flex;align-items:center;justify-content:center;gap:14px;margin:16px 0;padding:16px;border:1px solid #e1e8ec;border-radius:13px;background:#fff}.policy-flow div{display:flex;align-items:center;gap:8px}.policy-flow b{display:grid;width:26px;height:26px;place-items:center;border-radius:50%;background:#e9f3fa;color:#12629a}.policy-flow i{color:#91a1ab;font-style:normal}.table-card{overflow:hidden;border:1px solid #dfe8ed;border-radius:14px;background:#fff}.primary-cell{display:grid;gap:4px}.primary-cell span{color:#718391;font-size:12px}.form-section{padding:4px 0 18px}.form-section+.form-section{padding-top:18px;border-top:1px solid #e5ecef}.form-section h3{margin:0 0 14px;font-size:16px}.section-title{display:flex;align-items:baseline;justify-content:space-between;gap:16px}.section-title span{color:#718391;font-size:12px}.form-grid{display:grid;gap:0 14px}.form-grid.three{grid-template-columns:1fr 1.4fr .7fr}.form-grid.four{grid-template-columns:repeat(4,1fr)}.score-groups{display:grid;grid-template-columns:1.15fr 1fr 1fr;gap:12px}.score-groups fieldset{display:grid;grid-template-columns:1fr;gap:10px;margin:0;padding:14px;border:1px solid #dfe8eb;border-radius:10px}.score-groups legend{padding:0 6px;font-weight:700}.score-groups label{display:flex;align-items:center;justify-content:space-between;gap:8px;color:#526876}.score-groups :deep(.el-input-number){width:140px}.form-grid :deep(.el-input-number){width:100%}.evidence-field :deep(.el-form-item__content){flex-wrap:nowrap}.evidence-field :deep(.el-input-number){width:calc(100% - 28px)}.unit{margin-left:6px}@media(max-width:800px){.policy-hero{align-items:flex-start;flex-direction:column}.policy-flow{align-items:flex-start;flex-direction:column}.policy-flow i{display:none}.form-grid.three,.form-grid.four,.score-groups{grid-template-columns:1fr 1fr}}@media(max-width:560px){.policy-page{padding:12px}.form-grid.three,.form-grid.four,.score-groups{grid-template-columns:1fr}.score-groups fieldset{grid-template-columns:1fr}.hero-actions{width:100%}.hero-actions :deep(.el-button){min-height:44px;flex:1}}
</style>
