<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import areaData from "china-area-data";
import { supervisionApi } from "@/api/supervision.api";
import { qualityRiskApi } from "@/api/quality-risk.api";
import type { SupervisionRecord } from "@/types/supervision.types";
import BulkImportDialog from "@/components/business/supervision/BulkImportDialog.vue";
import { formatServerDateTime } from "@/utils/date-time";

const loading = ref(false), saving = ref(false), dialog = ref(false), importDialog = ref(false);
const rows = ref<SupervisionRecord[]>([]), editing = ref<SupervisionRecord | null>(null);
const keyword = ref(""), page = ref(1), total = ref(0);
const deletingId = ref("");
async function remove(row: SupervisionRecord) {
  try { await ElMessageBox.confirm(`删除企业“${row.name}”？已被业务记录引用的企业不能删除。`, "删除企业", { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }); }
  catch { return; }
  deletingId.value = row.id;
  try {
    await qualityRiskApi.deleteEnterprise(row.id);
    if (rows.value.length === 1 && page.value > 1) page.value -= 1;
    ElMessage.success("企业已删除"); await load();
  } catch { return; }
  finally { deletingId.value = ""; }
}
const form = reactive({ name: "", credit_code: "", region: [] as string[], address: "" });
function children(code: string): any[] {
  return Object.entries(areaData[code] || {}).map(([value, label]) => ({ value, label,
    children: Object.keys(areaData[value] || {}).length ? children(value) : undefined }));
}
const regions = children("86");
const similar = computed(() => rows.value.filter(row => row.id !== editing.value?.id &&
  (row.name === form.name.trim() || (form.credit_code.trim() && row.data.credit_code === form.credit_code.trim()))));
function locationLabel(row: SupervisionRecord) {
  const loc = row.data.location || {};
  const codes = [loc.province_code, loc.city_code, loc.district_code].filter(Boolean);
  return codes.map((code, i) => areaData[i ? codes[i - 1] : "86"]?.[code]).filter(Boolean).join(" / ") || "未提供";
}
async function load() {
  loading.value = true;
  try {
    const data = (await supervisionApi.list("enterprises", { keyword: keyword.value || undefined, page: page.value, size: 20 })).data.data;
    rows.value = data.items; total.value = data.total;
  } finally { loading.value = false; }
}
function search() { page.value = 1; void load(); }
function open(row?: SupervisionRecord) {
  editing.value = row || null;
  const loc = row?.data.location || {};
  Object.assign(form, { name: row?.name || "", credit_code: row?.data.credit_code || "",
    region: [loc.province_code, loc.city_code, loc.district_code].filter(Boolean),
    address: loc.formatted_address || row?.data.address || "" });
  dialog.value = true;
}
async function save() {
  if (!form.name.trim()) { ElMessage.warning("请填写企业名称"); return; }
  saving.value = true;
  try {
    const previous = editing.value?.data || {};
    const data = { ...previous, credit_code: form.credit_code.trim() || null,
      address: form.address.trim() || null,
      location: { ...(previous.location || {}), province_code: form.region[0] || null,
        city_code: form.region[1] || null, district_code: form.region[2] || null,
        formatted_address: form.address.trim() || null,
        location_method: form.region.length || form.address.trim() ? "manual" : "unknown" } };
    if (editing.value) await supervisionApi.update("enterprises", editing.value.id,
      { version: editing.value.version, name: form.name.trim(), data });
    else await supervisionApi.create("enterprises", { name: form.name.trim(), data });
    dialog.value = false; ElMessage.success("企业档案已保存"); await load();
  } finally { saving.value = false; }
}
onMounted(load);
</script>

<template>
  <main class="archive-page">
    <header class="page-heading"><div><h1>企业档案</h1><p>维护企业身份信息，供产品、报告和业务记录关联。</p></div>
      <div class="actions"><el-button @click="importDialog = true">批量导入</el-button><el-button type="primary" @click="open()">新增企业</el-button></div>
    </header>
    <section class="records-card">
      <div class="filter-bar"><el-input v-model="keyword" clearable placeholder="搜索企业名称" aria-label="搜索企业名称" @keyup.enter="search" /><el-button @click="search">查询</el-button><el-button @click="load">刷新</el-button></div>
      <el-table v-loading="loading" :data="rows" empty-text="暂无企业档案，可新增或批量导入">
        <el-table-column prop="name" label="企业名称" min-width="210" />
        <el-table-column label="统一社会信用代码" min-width="190"><template #default="{ row }">{{ row.data.credit_code || '未提供' }}</template></el-table-column>
        <el-table-column label="所在地区" min-width="190"><template #default="{ row }">{{ locationLabel(row) }}</template></el-table-column>
        <el-table-column label="更新时间" min-width="165"><template #default="{ row }">{{ formatServerDateTime(row.updated_at) }}</template></el-table-column>
        <el-table-column label="操作" width="170" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="open(row)">查看 / 编辑</el-button><el-button link type="danger" :loading="deletingId === row.id" :disabled="!!deletingId && deletingId !== row.id" @click="remove(row)">删除</el-button></template></el-table-column>
      </el-table>
      <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" @current-change="load" />
    </section>
    <el-dialog v-model="dialog" :title="editing ? '编辑企业档案' : '新增企业档案'" width="min(620px,94vw)" :close-on-click-modal="false">
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item label="企业名称" required><el-input v-model="form.name" maxlength="255" placeholder="填写资料中的企业名称" /></el-form-item>
        <el-form-item label="统一社会信用代码（选填）"><el-input v-model="form.credit_code" maxlength="32" /></el-form-item>
        <el-form-item label="所在地区（选填）"><el-cascader v-model="form.region" :options="regions" clearable filterable placeholder="选择省、市、区县" /></el-form-item>
        <el-collapse><el-collapse-item title="补充信息" name="extra">
          <el-form-item label="详细地址（选填）"><el-input v-model="form.address" maxlength="500" /></el-form-item>
          <p class="system-number">系统编号：{{ editing?.display_no || editing?.code || '保存后自动生成' }}</p>
        </el-collapse-item></el-collapse>
        <el-alert v-if="similar.length" class="duplicate-hint" type="warning" :closable="false" title="当前列表已有同名或同信用代码企业，请确认是否需要新增。" />
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>
    <BulkImportDialog v-model="importDialog" kind="enterprises" @imported="search" />
  </main>
</template>

<style scoped>
.archive-page{max-width:1440px;margin:auto;padding:28px;color:#172d44}.page-heading{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:24px}h1{margin:0;font-size:28px;font-weight:650}.page-heading p{margin:8px 0 0;color:#687b90;font-size:14px}.actions{display:flex;gap:8px}.records-card{background:white;border:1px solid #dce5ef;border-radius:12px;overflow:hidden;padding:20px}.filter-bar{display:flex;gap:10px;margin-bottom:20px}.filter-bar .el-input{max-width:380px}.el-pagination{justify-content:flex-end;margin-top:20px}.el-cascader{width:100%}.system-number{font-size:13px;color:#75859a}.duplicate-hint{margin-top:16px}@media(max-width:640px){.archive-page{padding:16px}.page-heading{align-items:flex-start;flex-direction:column}.filter-bar{flex-wrap:wrap}.records-card{padding:12px}.actions{width:100%}}
</style>
