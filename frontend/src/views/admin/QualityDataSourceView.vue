<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Plus, RefreshRight } from "@element-plus/icons-vue";
import { qualityRiskApi } from "@/api/quality-risk.api";
import type { QualityDataSource } from "@/types/quality-risk.types";

const rows = ref<QualityDataSource[]>([]);
const loading = ref(false);
const saving = ref(false);
const dialog = ref(false);
const editing = ref<QualityDataSource | null>(null);
const form = reactive({ code: "", name: "", source_type: "consumer_complaint", connector_type: "manual", status: "active" });
const sourceTypes = [
  ["consumer_complaint", "消费投诉"], ["supervision_inspection", "监督抽查"],
  ["enforcement_case", "执法案例"], ["enterprise_information", "企业信息"],
  ["public_opinion", "公开舆情"], ["inspection_report", "检测报告"],
  ["production_data", "生产数据"], ["policy_document", "政策文件"],
  ["standard_document", "标准文件"], ["device_observation", "设备观测"],
];
const connectorLabels: Record<string, string> = { manual: "人工登记", file: "文件导入", api: "API", webhook: "Webhook", database_sync: "数据库同步" };

async function load() {
  loading.value = true;
  try { rows.value = (await qualityRiskApi.sources()).data.data; }
  finally { loading.value = false; }
}
function openCreate() {
  editing.value = null;
  Object.assign(form, { code: "", name: "", source_type: "consumer_complaint", connector_type: "manual", status: "active" });
  dialog.value = true;
}
function openEdit(row: QualityDataSource) {
  editing.value = row;
  Object.assign(form, { code: row.code, name: row.name, source_type: row.source_type, connector_type: row.connector_type, status: row.status });
  dialog.value = true;
}
async function save() {
  if (!form.code.trim() || !form.name.trim()) { ElMessage.warning("请填写来源名称和编码"); return; }
  saving.value = true;
  try {
    const payload = { name: form.name, source_type: form.source_type, connector_type: form.connector_type, status: form.status, config: editing.value?.config || {} };
    if (editing.value) await qualityRiskApi.updateSource(editing.value.id, payload);
    else await qualityRiskApi.createSource({ code: form.code, ...payload });
    dialog.value = false;
    ElMessage.success(editing.value ? "数据来源已更新" : "数据来源已登记");
    await load();
  } finally { saving.value = false; }
}
onMounted(load);
</script>

<template>
  <main class="source-page">
    <header><div><p>QUALITY DATA SOURCES</p><h1>数据来源</h1><span>管理员只维护来源名称、数据类型、接入方式和启停状态；投诉、报告等具体资料由质监业务人员接入。</span></div><div><el-button :icon="RefreshRight" @click="load">刷新</el-button><el-button type="primary" :icon="Plus" @click="openCreate">登记来源</el-button></div></header>
    <section class="boundary"><div><strong>管理员</strong><span>配置“数据从哪里来”</span></div><i>→</i><div><strong>质监业务人员</strong><span>接入具体原文、文件和附件</span></div><i>→</i><div><strong>质监专家</strong><span>在风险研判中核验证据</span></div></section>
    <section class="table-card"><el-table :data="rows" v-loading="loading"><el-table-column label="来源"><template #default="{ row }"><div class="primary-cell"><strong>{{ row.name }}</strong><span>{{ row.code }}</span></div></template></el-table-column><el-table-column label="数据类型" width="150"><template #default="{ row }">{{ sourceTypes.find((item) => item[0] === row.source_type)?.[1] || row.source_type }}</template></el-table-column><el-table-column label="接入方式" width="140"><template #default="{ row }">{{ connectorLabels[row.connector_type] || row.connector_type }}</template></el-table-column><el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status === 'active' ? '启用' : '停用' }}</el-tag></template></el-table-column><el-table-column label="操作" width="100"><template #default="{ row }"><el-button link @click="openEdit(row)">编辑</el-button></template></el-table-column></el-table></section>
    <el-dialog v-model="dialog" :title="editing ? '编辑数据来源' : '登记数据来源'" width="min(680px, 94vw)" top="5vh" :close-on-click-modal="false"><el-form label-position="top"><div class="grid"><el-form-item label="来源编码" required><el-input v-model="form.code" :disabled="!!editing" placeholder="系统内唯一，如 12315-CQ" /></el-form-item><el-form-item label="来源名称" required><el-input v-model="form.name" placeholder="如：重庆12315投诉数据" /></el-form-item><el-form-item label="主要数据类型"><el-select v-model="form.source_type"><el-option v-for="item in sourceTypes" :key="item[0]" :label="item[1]" :value="item[0]" /></el-select></el-form-item><el-form-item label="接入方式"><el-select v-model="form.connector_type"><el-option v-for="(label, value) in connectorLabels" :key="value" :label="label" :value="value" /></el-select></el-form-item><el-form-item label="状态"><el-radio-group v-model="form.status"><el-radio-button value="active">启用</el-radio-button><el-radio-button value="inactive">停用</el-radio-button></el-radio-group></el-form-item></div><el-alert type="info" :closable="false" title="API、Webhook 和数据库同步的地址与凭据应在取得真实接口资料后通过受控连接配置，不在此处填写明文凭据。" /></el-form><template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template></el-dialog>
  </main>
</template>

<style scoped>
.source-page{max-width:1280px;margin:0 auto;padding:24px;color:#172b3a}.source-page>header{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;padding:28px;border:1px solid #d6e4e5;border-radius:16px;background:linear-gradient(120deg,#eef8f7,#fff)}header p{margin:0 0 8px;color:#08796f;font:700 11px ui-monospace,monospace;letter-spacing:.14em}h1{margin:0;font-size:34px}header span{display:block;max-width:720px;margin-top:8px;color:#627784;line-height:1.6}header>div:last-child{display:flex;gap:8px}.boundary{display:grid;grid-template-columns:1fr auto 1fr auto 1fr;align-items:center;gap:14px;margin:16px 0;padding:16px;border:1px solid #e1e9ea;border-radius:13px;background:#fff}.boundary div{display:grid;gap:4px}.boundary span,.boundary i{color:#71838e;font-size:12px}.boundary i{font-style:normal}.table-card{overflow:hidden;border:1px solid #dfe8e9;border-radius:14px;background:#fff}.primary-cell{display:grid;gap:4px}.primary-cell span{color:#71838e;font-size:12px}.grid{display:grid;grid-template-columns:1fr 1.4fr;gap:0 16px}.el-select{width:100%}@media(max-width:700px){.source-page{padding:12px}.source-page>header{align-items:flex-start;flex-direction:column}.boundary,.grid{grid-template-columns:1fr}.boundary i{display:none}header>div:last-child{width:100%}header>div:last-child :deep(.el-button){min-height:44px;flex:1}}
</style>
