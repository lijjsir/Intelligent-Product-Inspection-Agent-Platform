<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { ElMessage, type UploadFile, type UploadFiles } from "element-plus";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { useAuthStore } from "@/stores/auth.store";
import KnowledgeSubmitDialog from '@/components/business/KnowledgeSubmitDialog.vue';
import MaterialTaskDraftDialog from '@/components/business/MaterialTaskDraftDialog.vue';
import { formatServerDateTime } from "@/utils/date-time";
import { RECORD_TYPE_LABELS, type QualityAttachment, type QualityRecordType, type QualitySourceRecord } from "@/types/quality-risk.types";
defineProps<{ embedded?: boolean }>();
const auth = useAuthStore();
const smallScreen=ref(window.innerWidth<=650);
const onResize=()=>{smallScreen.value=window.innerWidth<=650;};
const ownOnly = computed(() => !auth.hasPermission("quality_material_read_business"));
const canCreate = computed(() => auth.hasPermission("quality_material_submit"));
const canImport = computed(() => auth.hasPermission("quality_ingestion_manage"));
const records = ref<QualitySourceRecord[]>([]);
const total = ref(0), page = ref(1), loading = ref(false), saving = ref(false), importing = ref(false);
const recordDialog = ref(false), importDialog = ref(false);
const selected = ref<QualitySourceRecord | null>(null);
const knowledgeSubmitOpen=ref(false),taskDraftOpen=ref(false);
const selectedAttachments = ref<QualityAttachment[]>([]);
const files = ref<UploadFiles>([]), uploaded = ref<QualityAttachment[]>([]);
const keyword = ref(""), recordType = ref<QualityRecordType | "">("");
const importFile = ref<File | null>(null), importPreview = ref<any>(null), importRequestKey = ref("");
const importMapping = ref<Record<string,string>>({}), importColumns = ref<string[]>([]);
const form = reactive({ record_type:"consumer_complaint" as QualityRecordType, text:"", origin_label:"", occurred_at:"", external_record_id:"", product_description:"", enterprise_name:"", production_batch_ref:"" });
const importForm = reactive({ origin_label:"", record_type:"consumer_complaint" });
const types = Object.entries(RECORD_TYPE_LABELS);
const submissionTypes = types.filter(([type])=>type!=="standard_document");
const mappingFields = [["text","原始内容"],["record_type","资料类型"],["occurred_at","发生时间"],["origin_label","原始出处"],["external_record_id","外部编号"],["enterprise_name","企业名称"],["product_id","已有产品ID"],["category_id","已有类别ID"],["production_batch_ref","真实批次号"],["unit_serial_ref","单件序列号"]];
async function loadRecords() {
  loading.value=true;
  try { const response=await qualityRiskApi.records({page:page.value,size:20,record_type:recordType.value||undefined,keyword:keyword.value||undefined}); records.value=response.data.data.items; total.value=response.data.data.total; }
  finally { loading.value=false; }
}
function openRecord() { Object.assign(form,{record_type:"consumer_complaint",text:"",origin_label:"",occurred_at:"",external_record_id:"",product_description:"",enterprise_name:"",production_batch_ref:""});files.value=[];uploaded.value=[];recordDialog.value=true; }
function fileChanged(_file:UploadFile,list:UploadFiles) { files.value=list;uploaded.value=[]; }
async function saveRecord() {
  if(!form.text.trim()&&!files.value.length){ElMessage.warning("请填写原始内容或选择附件");return;}
  saving.value=true;
  try {
    if(files.value.length&&!uploaded.value.length) uploaded.value=(await qualityRiskApi.uploadAttachments(files.value.map(x=>x.raw).filter((x):x is NonNullable<typeof x>=>!!x))).data.data;
    const response=await qualityRiskApi.createEvent({record_type:form.record_type,origin_label:form.origin_label||null,occurred_at:form.occurred_at?new Date(form.occurred_at).toISOString():null,external_record_id:form.external_record_id||null,content:{...(form.text.trim()?{text:form.text}:{}),...(form.product_description?{product_description:form.product_description}:{})},enterprise_ref:form.enterprise_name?{name:form.enterprise_name}:{},product_ref:form.production_batch_ref?{production_batch_ref:form.production_batch_ref}:{},attachment_ids:uploaded.value.map(x=>x.id),provenance:{channel:"manual_form"}});
    recordDialog.value=false;ElMessage.success(`资料已受理：${response.data.data.display_no||response.data.data.id}`);await loadRecords();
  } finally {saving.value=false;}
}
function openImport(){importFile.value=null;importPreview.value=null;importMapping.value={};importColumns.value=[];importRequestKey.value=crypto.randomUUID();importDialog.value=true;}
function importChanged(file:UploadFile){importFile.value=file.raw||null;importPreview.value=null;importMapping.value={};importColumns.value=[];importRequestKey.value=crypto.randomUUID();}
function mappingChanged(){importRequestKey.value=crypto.randomUUID();importPreview.value=null;}
async function previewImport(){
  if(!importFile.value){ElMessage.warning("请选择CSV、XLSX或JSON文件");return;}
  importing.value=true;
  try{importPreview.value=(await qualityRiskApi.previewImport(null,importRequestKey.value,importFile.value,importMapping.value,importForm.origin_label||null,importForm.record_type)).data.data;importMapping.value={...importPreview.value.mapping};importColumns.value=importPreview.value.source_columns;}
  finally{importing.value=false;}
}
async function confirmImport(){importing.value=true;try{const result=(await qualityRiskApi.confirmImport(importPreview.value.id)).data.data;importPreview.value=result;ElMessage.success(`导入完成：新建 ${result.created_count}，重复 ${result.duplicate_count}，失败 ${result.failed_count}`);await loadRecords();}finally{importing.value=false;}}
async function cancelImport(){if(importPreview.value?.status==="preview")await qualityRiskApi.cancelImport(importPreview.value.id);importDialog.value=false;}
async function downloadTemplate(){const blob=(await qualityRiskApi.importTemplate()).data as unknown as Blob;const url=URL.createObjectURL(blob),anchor=document.createElement("a");anchor.href=url;anchor.download="质量资料导入模板.csv";anchor.click();URL.revokeObjectURL(url);}
async function showRecord(row:QualitySourceRecord){selected.value=row;selectedAttachments.value=[];const evidence=(await qualityRiskApi.evidence(row.id)).data.data as Array<{attachment_id?:string}>;const ids=[...new Set(evidence.map(x=>x.attachment_id).filter((x):x is string=>!!x))];selectedAttachments.value=await Promise.all(ids.map(async id=>(await qualityRiskApi.attachment(id)).data.data));}
async function downloadAttachment(file:QualityAttachment){const blob=(await qualityRiskApi.downloadAttachment(file.id)).data as unknown as Blob;const url=URL.createObjectURL(blob),anchor=document.createElement("a");anchor.href=url;anchor.download=file.file_name;anchor.click();URL.revokeObjectURL(url);}
function closeDetail(value:boolean){if(!value)selected.value=null;}
onMounted(()=>{window.addEventListener("resize",onResize);void loadRecords();});
onBeforeUnmount(()=>window.removeEventListener("resize",onResize));
</script>
<template>
  <main class="intake-page" :class="{embedded}">
    <header class="page-head"><div><h1>{{ownOnly?"本人质量资料":"质量资料接入"}}</h1><p>保存投诉、抽检和报告等业务资料，供风险研判引用；未知对象信息可以留空。</p></div><div class="actions"><el-button v-if="canImport" @click="openImport">文件导入</el-button><el-button v-if="canCreate" type="primary" @click="openRecord">提交资料</el-button></div></header>
    <div class="filters"><el-input v-model="keyword" clearable placeholder="搜索原始内容或外部编号" @keyup.enter="loadRecords"/><el-select v-model="recordType" clearable placeholder="全部资料类型" @change="loadRecords"><el-option v-for="[value,label] in types" :key="value" :label="label" :value="value"/></el-select><el-button @click="loadRecords">查询</el-button><el-button @click="loadRecords">刷新</el-button></div>
    <div v-if="smallScreen" class="mobile-records"><button v-for="row in records" :key="row.id" class="mobile-record" @click="showRecord(row)"><strong>{{row.content.text || row.content.description || "附件资料"}}</strong><span>{{RECORD_TYPE_LABELS[row.record_type]}} · {{row.provenance.origin_label || "出处未知"}}</span><small>{{row.display_no || "历史资料"}}</small></button></div>
    <el-table v-else :data="records" v-loading="loading" @row-click="showRecord">
      <el-table-column label="受理编号" min-width="220"><template #default="{row}">{{row.display_no||"历史资料"}}</template></el-table-column>
      <el-table-column label="类型" width="130"><template #default="{row}">{{RECORD_TYPE_LABELS[row.record_type as QualityRecordType]}}</template></el-table-column>
      <el-table-column label="原始材料" min-width="250"><template #default="{row}">{{row.content.text||row.content.description||(row.attachment_ids.length?"附件资料":"结构化资料")}}</template></el-table-column>
      <el-table-column label="原始出处" min-width="160"><template #default="{row}">{{row.provenance.origin_label||"未知"}}</template></el-table-column>
      <el-table-column label="接收时间" width="175"><template #default="{row}">{{formatServerDateTime(row.received_at)}}</template></el-table-column>
      <el-table-column label="状态" width="100"><template #default><el-tag type="info">已保存原件</el-tag></template></el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" @current-change="loadRecords"/>
    <el-drawer :model-value="!!selected" title="原始资料详情" size="min(620px,96vw)" append-to-body @update:model-value="closeDetail">
      <template v-if="selected"><h2>{{selected.display_no||"历史资料"}}</h2><p class="raw-text">{{selected.content.text||JSON.stringify(selected.content,null,2)}}</p><el-descriptions :column="1" border><el-descriptions-item label="出处">{{selected.provenance.origin_label||"未知"}}</el-descriptions-item><el-descriptions-item label="发生时间">{{selected.occurred_at?formatServerDateTime(selected.occurred_at):"未知"}}</el-descriptions-item><el-descriptions-item label="接收时间">{{formatServerDateTime(selected.received_at)}}</el-descriptions-item><el-descriptions-item label="外部真实编号">{{selected.external_record_id||"未提供"}}</el-descriptions-item><el-descriptions-item label="来源文件行号">{{selected.provenance.import_row||"不适用"}}</el-descriptions-item><el-descriptions-item label="真实生产批次">{{selected.product_ref.production_batch_ref||"未知"}}</el-descriptions-item><el-descriptions-item label="数据性质">{{selected.data_nature}}</el-descriptions-item></el-descriptions><div class="attachments"><el-button v-if="auth.hasPermission('knowledge_candidate_submit')" @click="knowledgeSubmitOpen=true">从资料提出知识候选</el-button><el-button v-if="['user','expert'].includes(auth.primaryRole)&&auth.hasPermission('task')" @click="taskDraftOpen=true">复用附件创建任务草稿</el-button><el-button v-for="file in selectedAttachments" :key="file.id" @click="downloadAttachment(file)">下载 {{file.file_name}}</el-button></div><p class="muted">保存原件不代表已解析、已确认对象或已形成检测结论。</p></template>
    </el-drawer>
    <KnowledgeSubmitDialog v-if="selected" v-model="knowledgeSubmitOpen" source-kind="intake_record" :source-id="selected.id"/>
    <MaterialTaskDraftDialog v-if="selected" v-model="taskDraftOpen" :record-id="selected.id"/>
    <el-dialog v-model="recordDialog" class="quality-intake-form" top="3vh" title="提交质量资料" width="min(700px,94vw)" append-to-body :close-on-click-modal="false">
      <el-form label-position="top"><el-form-item label="资料类型" required><el-select v-model="form.record_type"><el-option v-for="[value,label] in submissionTypes" :key="value" :label="label" :value="value"/></el-select></el-form-item><el-form-item label="原始内容或附件（至少一种）"><el-input v-model="form.text" type="textarea" :rows="4" placeholder="保留原话或原始材料内容"/><el-upload v-model:file-list="files" :auto-upload="false" multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.txt,.csv,.xlsx,.json" :on-change="fileChanged" :on-remove="fileChanged"><el-button>选择资料文件</el-button><template #tip>单文件不超过50MB；文件选择后由系统保存。</template></el-upload></el-form-item><el-form-item label="原始出处（选填）"><el-input v-model="form.origin_label" placeholder="如某单位提供的抽检资料；不知道时留空"/></el-form-item><el-collapse><el-collapse-item title="对象与发生时间（已有信息再填）"><el-form-item label="产品原始描述"><el-input v-model="form.product_description" placeholder="品牌、名称、型号可以直接按原资料描述"/></el-form-item><div class="form-grid"><el-form-item label="涉及企业"><el-input v-model="form.enterprise_name"/></el-form-item><el-form-item label="真实生产批次号"><el-input v-model="form.production_batch_ref"/></el-form-item><el-form-item label="实际发生时间"><el-date-picker v-model="form.occurred_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" placeholder="未知可空"/></el-form-item><el-form-item label="外部报告／投诉编号"><el-input v-model="form.external_record_id"/></el-form-item></div></el-collapse-item></el-collapse><p class="muted">受理编号、提交人和接收时间自动生成。标准文件请在标准库上传，本次检测材料在新建任务中提供。</p></el-form>
      <template #footer><el-button @click="recordDialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="saveRecord">提交</el-button></template>
    </el-dialog>
    <el-dialog v-model="importDialog" class="quality-intake-form" top="3vh" title="导入现有结构化资料" width="min(880px,96vw)" append-to-body :close-on-click-modal="false">
      <el-form label-position="top"><div class="form-grid"><el-form-item label="默认资料类型"><el-select v-model="importForm.record_type" @change="mappingChanged"><el-option v-for="[value,label] in submissionTypes" :key="value" :label="label" :value="value"/></el-select></el-form-item><el-form-item label="共同出处（选填，逐行出处优先）"><el-input v-model="importForm.origin_label" @change="mappingChanged"/></el-form-item></div><el-upload :auto-upload="false" :limit="1" accept=".csv,.xlsx,.json" :on-change="importChanged"><el-button>选择CSV、XLSX或JSON</el-button></el-upload><p class="muted">最多5000条、20MB。PDF和图片通过“提交资料”保存原件。</p><el-button @click="downloadTemplate">下载模板</el-button><el-button :loading="importing" :disabled="!importFile" @click="previewImport">校验并预览</el-button></el-form>
      <el-collapse v-if="importColumns.length"><el-collapse-item title="核对列映射（中文列名会自动建议）"><div class="form-grid"><el-form-item v-for="[field,label] in mappingFields" :key="field" :label="label"><el-select v-model="importMapping[field]" clearable @change="mappingChanged"><el-option v-for="column in importColumns" :key="column" :label="column" :value="column"/></el-select></el-form-item></div></el-collapse-item></el-collapse>
      <template v-if="importPreview"><el-alert :closable="false" :type="importPreview.error_count?'warning':'success'" :title="`${importPreview.import_batch_code}：有效 ${importPreview.valid_count} 条，错误 ${importPreview.error_count} 条`"/><el-table v-if="importPreview.errors.length" :data="importPreview.errors"><el-table-column prop="row" label="源行／条目" width="100"/><el-table-column prop="message" label="错误"/></el-table><el-table v-else-if="importPreview.status==='preview'" :data="importPreview.preview_rows"><el-table-column label="内容"><template #default="{row}">{{row.content.text||"结构化材料"}}</template></el-table-column><el-table-column label="出处"><template #default="{row}">{{row.origin_label||"未知"}}</template></el-table-column><el-table-column label="对象"><template #default="{row}">{{row.product_ref.production_batch_ref||row.enterprise_ref.name||row.product_ref.product_id||"待确认"}}</template></el-table-column></el-table><el-alert v-if="importPreview.status==='confirmed'" :closable="false" type="success" :title="`已完成：新建 ${importPreview.created_count}，重复 ${importPreview.duplicate_count}，失败 ${importPreview.failed_count}`"/></template>
      <template #footer><el-button @click="cancelImport">{{importPreview?.status==='confirmed'?'关闭':'取消'}}</el-button><el-button type="primary" :loading="importing" :disabled="!importPreview||importPreview.error_count>0||!importPreview.valid_count||importPreview.status!=='preview'" @click="confirmImport">确认导入</el-button></template>
    </el-dialog>
  </main>
</template>
<style scoped>
.intake-page{padding:24px;color:#20364a}.embedded{padding:0}.page-head{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:22px}h1{font-size:24px;margin:0}h2{font-size:18px}.page-head p,.muted{color:#607386;font-size:13px}.actions,.filters,.attachments{display:flex;gap:10px;flex-wrap:wrap}.filters{margin-bottom:16px}.filters .el-input{max-width:360px}.filters .el-select{width:180px}.el-pagination{margin-top:16px}.el-select,.el-date-editor{width:100%}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 18px}.raw-text{white-space:pre-wrap;overflow-wrap:anywhere}.attachments{margin:20px 0}.el-alert,.el-collapse,.el-table{margin-top:14px}.el-form-item{margin-top:12px}@media(max-width:650px){.intake-page{padding:14px}.embedded{padding:0}.page-head{flex-direction:column}.form-grid{grid-template-columns:1fr}.filters .el-input,.filters .el-select{max-width:none;width:100%}}
</style>

<style>
.quality-intake-form.el-dialog{background:#fff!important;max-height:94dvh;overflow:hidden}.quality-intake-form .el-dialog__body{max-height:calc(94dvh - 150px);overflow:auto}.mobile-records{display:grid;gap:8px}.mobile-record{display:grid;gap:5px;text-align:left;border:1px solid #dce4ec;padding:12px;background:white;border-radius:5px;color:#20364a;cursor:pointer}.mobile-record strong{font-weight:500;overflow-wrap:anywhere}.mobile-record span,.mobile-record small{color:#607386;font-size:12px}
</style>
