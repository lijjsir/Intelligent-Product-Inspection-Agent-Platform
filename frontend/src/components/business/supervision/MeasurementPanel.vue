<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { ElMessage, type UploadFile, type UploadUserFile } from "element-plus";
import { supervisionApi, type ReferenceLoader } from "@/api/supervision.api";
import { extractApiErrorMessage } from '@/api/http';
import { useRoute,useRouter } from 'vue-router';
import PagedReferenceSelect from './PagedReferenceSelect.vue';
import SupervisionFields from "./SupervisionFields.vue";
import SupervisionAssessment from "./SupervisionAssessment.vue";
import AdaptiveInspectionPanel from "./AdaptiveInspectionPanel.vue";
import { fields, cleanFields } from "./form-fields";
import { STATUS_LABELS, type SupervisionRecord } from "@/types/supervision.types";
import { useAuthStore } from "@/stores/auth.store";
import { inspectionExecutionApi } from '@/api/inspection-execution.api';
import type { ExecutionTaskContext } from '@/types/inspection-execution.types';

const props = defineProps<{
  taskId: string;
  productSkuId?: string | null;
  batchId?: string | null;
  preparationOnly?: boolean;
}>();
const emit=defineEmits<{ready:[]}>();
const auth = useAuthStore();
const route = useRoute();
const router=useRouter();
const sessionPage=ref(1),samplePage=ref(1),sessionTotal=ref(0),sampleTotal=ref(0),sessionSearch=ref(''),loadError=ref(''),reading=ref(false);
let epoch=0,previewEpoch=0;
const optionLoaders: Record<string,ReferenceLoader>=Object.fromEntries(['devices','samples','regions','plans','cases'].map(key=>[key,async query=>(await supervisionApi.referenceOptions(key,{...query,task_id:props.taskId})).data.data]));
const enrollmentDialog = ref(false),
  enrollmentDataset = ref("");
async function enroll() {
  if (!session.value) return;
  await supervisionApi.enrollDataset(session.value.id, enrollmentDataset.value);
  enrollmentDialog.value = false;
  ElMessage.success("已授权到指定数据集，算法工程师可按候选样本接收");
}
const canWrite = computed(() => ["user", "expert"].includes(auth.role));
const enabled = ref(false),
  sessions = ref<SupervisionRecord[]>([]),
  session = ref<SupervisionRecord | null>(null),
  taskSamples = ref<SupervisionRecord[]>([]),
  measurements = ref<any[]>([]),
  loading = ref(false);
const dialog = ref(false),
  sampleDialog = ref(false),
  form = ref<Record<string, any>>({}),
  sampleCode = ref(""),
  sampleRegion = ref("");
const taskContext=ref<ExecutionTaskContext|null>(null),sampledAt=ref<string|null>(null),sampleTarget=ref<SupervisionRecord|null>(null);
const scope=computed(()=>taskContext.value?.task_scope);
const sessionSpecs=computed(()=>fields['inspection-sessions']
  .filter(x=>!['task_id',...(props.preparationOnly?['case_id','plan_id','adaptive_enabled']:[])].includes(x.key))
  .map(x=>props.preparationOnly&&x.type==='array'?{...x,fields:x.fields?.filter(f=>['item','unit','method','standard_ref'].includes(f.key))}:x));
const options = ref<Record<string, { value: string; label: string }[]>>({}),
  file = ref<File | null>(null),
  uploadFiles=ref<UploadUserFile[]>([]),
  preview = ref<any>(null),
  sourceKey = ref("");
const mapping = ref<Record<string, string>>({});
const columns = [
  { key: "event_id", label: "来源事件编号" },
  { key: "sample_id", label: "样品编号" },
  { key: "device_id", label: "设备编号" },
  { key: "item", label: "项目" },
  { key: "measured_at", label: "采集时间" },
  { key: "value", label: "数值" },
  { key: "unit", label: "单位" },
  { key: "method", label: "方法" },
  { key: "quality_flag", label: "质量标记" },
  { key: 'conditions', label: '试验条件（JSON）' },
  { key: 'uncertainty', label: '测量不确定度（如原记录提供）' },
];
const unlocked = computed(
  () => canWrite.value && session.value && !['signed','closed','archived'].includes(session.value.status),
);
const plannedSamples = computed(() =>
  taskSamples.value.filter((sample) => !sample.data.sampled_at),
);
async function load() {
  const key=++epoch,target=props.taskId,selectedId=session.value?.id || (typeof route.query.session==='string'?route.query.session:undefined);
  reading.value=true;loadError.value='';measurements.value=[];taskSamples.value=[];preview.value=null;
  try {
    const settings = (await supervisionApi.settings()).data.data;
    enabled.value = settings.enabled;
    if (!enabled.value) return;
    const [batchResult,sampleResult,datasets,context]=await Promise.all([
      supervisionApi.list('inspection-sessions',{page:sessionPage.value,size:20,task_id:target,keyword:sessionSearch.value}),
      supervisionApi.list('samples',{page:samplePage.value,size:20,task_id:target}),
      canWrite.value&&!props.preparationOnly?supervisionApi.datasetTargets():Promise.resolve(null),
      props.preparationOnly?inspectionExecutionApi.context(target,{suppressErrorToast:true}):Promise.resolve(null),
    ]);
    let active=selectedId?batchResult.data.data.items.find(row=>row.id===selectedId)|| (await supervisionApi.get('inspection-sessions',selectedId,{suppressErrorToast:true})).data.data:batchResult.data.data.items[0]||null;
    if(active && active.data.task_id!==target)throw new Error('检测批次不属于当前任务');
    const values=active?(await supervisionApi.measurements(active.id)).data.data:[];
    if(key!==epoch||target!==props.taskId)return;
    sessions.value=batchResult.data.data.items;sessionTotal.value=batchResult.data.data.total;
    taskSamples.value=sampleResult.data.data.items;sampleTotal.value=sampleResult.data.data.total;
    session.value=active;measurements.value=values;
    if(context)taskContext.value=context.data.data;
    if(datasets)options.value.datasets=datasets.data.data;
  } catch(e) {
    if(key===epoch){taskContext.value=null;session.value=null;sessions.value=[];taskSamples.value=[];sessionTotal.value=0;sampleTotal.value=0;loadError.value=extractApiErrorMessage(e,'无法读取测量资料，请重试');}
  } finally {if(key===epoch)reading.value=false;}
}
function newSession() {
  form.value = {
    task_id: props.taskId,
    sample_ids: [],
    device_ids: [],
    required_items: [],
    candidate_items: [],
    adaptive_enabled: !props.preparationOnly,
    ...(props.preparationOnly?{product_category:scope.value?.product_category||'',production_date:scope.value?.production_date||null}:{}),
  };
  dialog.value = true;
}
async function createSession() {
  if(loading.value)return;
  const target=props.taskId;
  loading.value = true;
  try {
    const created = (
      await supervisionApi.create("inspection-sessions", {
        name: "检测会话",
        data: {...cleanFields(form.value, fields["inspection-sessions"]),...(props.preparationOnly?{product_category:form.value.product_category||null,production_date:form.value.production_date||null,adaptive_enabled:false}:{})},
      })
    ).data.data;
    if(target!==props.taskId)return;
    session.value=created;
    dialog.value = false;
    await load();
  } catch(e) {
    loadError.value=extractApiErrorMessage(e,'会话未创建，请核对样品、设备和项目');
  } finally {
    loading.value = false;
  }
}
function openSample(sample?:SupervisionRecord){sampleTarget.value=sample||null;sampleCode.value=sample?.name||'';sampleRegion.value=sample?.data.sampling_region_id||'';sampledAt.value=sample?.data.sampled_at||null;sampleDialog.value=true;}
async function registerSample() {
  if(loading.value)return;
  if(!sampledAt.value){ElMessage.warning('请按实际记录填写采样时间');return;}
  const target=props.taskId,context=scope.value;
  if(props.preparationOnly&&(!context||context.issues.length)){ElMessage.warning('任务对象尚未核对，请刷新并整理任务对象');return;}
  if(!props.preparationOnly&&(!props.productSkuId||!props.batchId)){ElMessage.warning('任务尚未关联产品或批次');return;}
  loading.value=true;loadError.value='';
  try{
  const data=props.preparationOnly?{
    task_id:target,product_sku_id:context?.product_sku_id||null,batch_id:context?.batch_id||null,
    quality_product_id:context?.quality_product_id||null,quality_batch_id:context?.quality_batch_id||null,
    production_batch_ref:context?.production_batch_ref||null,unit_serial_ref:context?.unit_serial_ref||null,
    sampled_at:sampledAt.value,sampling_region_id:sampleRegion.value||null,
  }:{task_id:target,product_sku_id:props.productSkuId,batch_id:props.batchId,sampled_at:sampledAt.value,sampling_region_id:sampleRegion.value||null};
  const existing=sampleTarget.value;
  const created = (
    existing?await supervisionApi.update('samples',existing.id,{version:existing.version,name:sampleCode.value.trim()||existing.name,data}):await supervisionApi.create("samples", {
      code: sampleCode.value.trim() || undefined,
      name: sampleCode.value.trim() || "实物样品",
      data,
    })
  ).data.data;
  if(target!==props.taskId)return;
  sampleDialog.value = false;
  await load();
  if(!existing&&!session.value){newSession();form.value.sample_ids=[created.id];}
  }catch(e){if(target===props.taskId)loadError.value=extractApiErrorMessage(e,'样品未保存，请核对对象及采样信息');}
  finally{if(target===props.taskId)loading.value=false;}
}
async function confirmPlannedSamples() {
  const sampledAt = new Date().toISOString();
  await Promise.all(
    plannedSamples.value.map((sample) =>
      supervisionApi.update("samples", sample.id, {
        version: sample.version,
        data: { sampled_at: sampledAt },
      }),
    ),
  );
  ElMessage.success(`已确认本页 ${plannedSamples.value.length} 个计划样品完成抽样`);
  await load();
}
function fileChanged(upload: UploadFile) {
  ++previewEpoch;
  file.value = upload.raw || null;
  preview.value = null;
  sourceKey.value = upload.name;
}
async function previewFile() {
  if (!session.value || !file.value || loading.value) return;
  const target=props.taskId,selected=session.value.id,key=epoch;
  const request=++previewEpoch;
  loading.value = true;
  try {
    const result=(await supervisionApi.preview(selected, file.value, mapping.value)).data.data;
    if(target===props.taskId&&selected===session.value?.id&&key===epoch&&request===previewEpoch)preview.value=result;
  }catch(e){if(key===epoch)loadError.value=extractApiErrorMessage(e,'文件预览失败，请核对文件与会话');
  } finally {
    if(key===epoch)loading.value = false;
  }
}
async function confirmFile() {
  if (!session.value || !preview.value || !sourceKey.value.trim()) return;
  if(loading.value)return;
  const target=props.taskId,selected=session.value.id;
  loading.value = true;
  try {
    await supervisionApi.confirm(selected, preview.value.preview_id, sourceKey.value);
    if(target!==props.taskId||selected!==session.value?.id)return;
    preview.value = null;
    file.value = null;
    uploadFiles.value=[];
    ElMessage.success("测量已入库");
    await load();
  }catch(e){loadError.value=extractApiErrorMessage(e,'导入未完成，请重新核对来源和预览');
  } finally {
    loading.value = false;
  }
}
async function template() {
  const blob = (await supervisionApi.template()).data;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "测量导入模板.csv";
  a.click();
  URL.revokeObjectURL(url);
}
async function analyze() {
  if (!session.value) return;
  await supervisionApi.run(
    "inspection-sessions",
    session.value.id,
    session.value.version,
    "laboratory",
  );
  ElMessage.success("已提交过程分析，可刷新查看进度");
  await load();
}
async function review(operation: string) {
  if (!session.value) return;
  await supervisionApi.review(
    "inspection-sessions",
    session.value.id,
    session.value.version,
    operation,
  );
  ElMessage.success("已进入业务待办");
}
async function prepareExecution(){if(!session.value)return;await router.replace({query:{...route.query,session:session.value.id}});emit('ready');}
watch(()=>sourceKey.value,()=>{++previewEpoch;preview.value=null;});
watch(mapping,()=>{++previewEpoch;preview.value=null;},{deep:true});
watch(()=>props.taskId,()=>{++epoch;loading.value=false;file.value=null;uploadFiles.value=[];taskContext.value=null;sessionPage.value=1;samplePage.value=1;sessionSearch.value='';session.value=null;dialog.value=false;sampleDialog.value=false;preview.value=null;void load();},{immediate:true});
onBeforeUnmount(()=>{++epoch;});
</script>
<template>
  <section v-if="loadError || (enabled && (!preparationOnly || ['measurement','mixed'].includes(scope?.input_mode||'')))" class="measurement-panel" v-loading="loading || reading">
    <header>
      <div>
        <h2>{{ preparationOnly?'样品与原始测量准备':'检测过程与测量' }}</h2>
        <p>{{ preparationOnly?'登记实际样品 → 配置采集会话 → 预览并导入原始测量 → 核对检测项目与独立复核。':'测量关联样品、设备和检测计划，提前提示与正式签发分别记录。' }}</p>
      </div>
      <el-button @click="load">刷新</el-button>
    </header>
    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" />
    <template v-if="preparationOnly&&scope"><p>产品：{{ scope.product_name }}；生产批次：{{ scope.production_batch_ref||'未知' }}；单件：{{ scope.unit_serial_ref||'未知' }}</p><el-alert v-for="issue in scope.issues" :key="issue" :title="issue" type="warning" :closable="false" /><el-alert title="保存样品、创建会话和导入文件只记录已有事实，不启动设备或模型。测量接收后，仍须核对已发布要求并由另一位专家复核检测结果。" type="info" :closable="false" /></template>
    <div class="controls"><el-input v-model="sessionSearch" aria-label="检测批次搜索" placeholder="按批次编号或名称搜索" clearable @keyup.enter="sessionPage=1;load()" /><el-button @click="sessionPage=1;load()">搜索批次</el-button><el-button :disabled="reading||sessionPage<=1" @click="sessionPage--;load()">上一页批次</el-button><span>第 {{ sessionPage }} 页 · 共 {{ sessionTotal }} 批</span><el-button :disabled="reading||sessionPage*20>=sessionTotal" @click="sessionPage++;load()">下一页批次</el-button></div>
    <div class="controls">
      <el-select
        v-if="sessions.length || session"
        v-model="session"
        value-key="id"
        placeholder="选择检测批次"
        @change="load"
        ><el-option
          v-for="s in (session && !sessions.some(row=>row.id===session?.id) ? [session,...sessions] : sessions)"
          :key="s.id"
          :label="s.name + ' · ' + (STATUS_LABELS[s.status] || s.status)"
          :value="s" /></el-select
      ><el-button v-if="canWrite" type="primary" @click="openSample()"
        >登记实物样品</el-button
      ><el-button v-if="canWrite && plannedSamples.length && !preparationOnly" @click="confirmPlannedSamples"
        >确认本页计划样品已抽取（{{ plannedSamples.length }}）</el-button
      ><el-button v-if="canWrite && sampleTotal" @click="newSession">配置采集会话</el-button>
    </div>
    <div class="controls"><span>任务样品第 {{ samplePage }} 页 · 共 {{ sampleTotal }} 个</span><el-button :disabled="reading||samplePage<=1" @click="samplePage--;load()">上一页样品</el-button><el-button :disabled="reading||samplePage*20>=sampleTotal" @click="samplePage++;load()">下一页样品</el-button></div>
    <el-table v-if="preparationOnly" :data="taskSamples" aria-label="任务实物样品"><el-table-column prop="name" label="实物标签" min-width="130" /><el-table-column prop="id" label="导入用样品编号" min-width="290" /><el-table-column prop="data.sampled_at" label="实际采样时间" min-width="180" /><el-table-column label="登记" width="100"><template #default="{row}"><el-button v-if="canWrite" link @click="openSample(row)">核对登记</el-button></template></el-table-column></el-table>
    <el-empty
      v-if="!session"
      description="先登记实际样品，再配置采集会话中的样品、设备和检测项目"
    />
    <template v-else>
      <div class="controls"><el-button v-if="session.data.case_id && auth.hasPermission('quality_material_read_business')" @click="router.push({path:'/app/risk-assessments',query:{case_id:session.data.case_id}})">返回来源研判</el-button><el-button v-if="session.data.plan_id && auth.role==='expert'" @click="router.push({path:'/app/sampling-plans',query:{record:session.data.plan_id}})">查看来源抽查计划</el-button></div>
      <el-alert
        v-if="session.status === 'signed'"
        type="success"
        title="此会话已签发，测量与结论版本已锁定"
        :closable="false"
      />
      <AdaptiveInspectionPanel v-if="!preparationOnly" :session="session" />
      <div v-if="preparationOnly" class="session-source"><p>当前会话：{{ session.id }}</p><p>样品编号：{{ session.data.sample_ids.join('、') }}</p><p>设备编号：{{ session.data.device_ids.join('、') }}</p><el-table :data="session.data.test_items"><el-table-column prop="item" label="项目标识" /><el-table-column prop="unit" label="单位" /><el-table-column prop="method" label="方法" /></el-table><p>文件中的样品、设备、项目、单位和方法须与本会话一致；未知采样、测量时间不能用提交时间代替。</p></div>
      <div v-if="unlocked" class="import-box">
        <div class="controls">
          <el-upload v-model:file-list="uploadFiles" :auto-upload="false" :limit="1" accept=".csv,.xlsx" :on-change="fileChanged" :on-remove="()=>{file=null;preview=null;}"
            ><el-button>选择测量文件</el-button></el-upload
          ><el-button @click="template">下载模板</el-button
          ><el-input v-model="sourceKey" placeholder="来源批次编号" /><el-button
            :disabled="!file"
            @click="previewFile"
            >校验与预览</el-button
          >
        </div>
        <el-collapse
          ><el-collapse-item title="自定义文件列名"
            ><div class="mapping">
              <el-form-item v-for="c in columns" :key="c.key" :label="c.label"
                ><el-input v-model="mapping[c.key]" :placeholder="c.key"
              /></el-form-item></div></el-collapse-item
        ></el-collapse>
        <template v-if="preview"
          ><p>有效 {{ preview.valid_count }} 行，错误 {{ preview.errors.length }} 行</p>
          <el-table v-if="preview.errors.length" :data="preview.errors"
            ><el-table-column prop="row" label="文件行号" width="100" /><el-table-column
              prop="message"
              label="需修正内容" /></el-table
          ><el-table :data="preview.rows"
            ><el-table-column prop="item" label="项目" /><el-table-column
              prop="value"
              label="数值" /><el-table-column prop="unit" label="单位" /><el-table-column
              prop="event_id"
              label="来源事件" /></el-table
          ><el-button type="primary" :disabled="!preview.can_confirm" @click="confirmFile"
            >确认导入</el-button
          ></template
        >
      </div>
      <el-button v-if="preparationOnly&&measurements.length" type="primary" @click="prepareExecution">使用本会话核对检测项目与复核</el-button>
      <div v-if="unlocked&&!preparationOnly" class="controls">
        <el-button type="primary" @click="analyze">分析检测过程</el-button
        ><el-button v-if="session.data.analysis" @click="review('result.review')"
          >提交专家复核</el-button
        ><el-button v-if="session.data.analysis" @click="review('result.signoff')"
          >提交正式签发</el-button
        >
      </div>
      <SupervisionAssessment
        v-if="session.data.analysis&&!preparationOnly"
        :output="session.data.analysis"
        :review-status="session.status"
      />
      <el-table :data="measurements"
        ><el-table-column prop="event_id" label="来源事件" min-width="120" /><el-table-column
          prop="item"
          label="检测项目" /><el-table-column prop="value" label="值" /><el-table-column
          prop="unit"
          label="单位" /><el-table-column prop="method" label="方法" /><el-table-column
          prop="measured_at"
          label="采集时间"
          min-width="170" /><el-table-column prop="quality_flag" label="质量标记"
      /></el-table>
    </template>
    <el-dialog v-model="dialog" title="配置检测批次" width="min(850px,94vw)" top="3vh"
      ><el-form label-position="top"
        ><SupervisionFields
          v-model="form"
          :specs="sessionSpecs"
          :options="options" :option-loaders="optionLoaders" /><template v-if="preparationOnly"><el-form-item label="产品类别（按档案核对）"><el-input v-model="form.product_category" :readonly="!!scope?.product_category" /></el-form-item><el-form-item label="实际生产日期（未知则留空，判定前须补齐依据）"><el-date-picker v-model="form.production_date" type="date" value-format="YYYY-MM-DD" :disabled="!!scope?.production_date" /></el-form-item></template></el-form
      ><template #footer
        ><el-button @click="dialog = false">取消</el-button
        ><el-button type="primary" :disabled="loading" @click="createSession">保存采集会话</el-button></template
      ></el-dialog
    >
    <el-dialog v-model="sampleDialog" title="登记实物样品" width="min(480px,94vw)" top="3vh"
      ><p v-if="preparationOnly&&scope">请核对本实物与任务对象一致：{{ scope.product_name }}；批次 {{ scope.production_batch_ref||'未知' }}；单件 {{ scope.unit_serial_ref||'未知' }}。</p><el-form label-position="top"
        ><el-form-item label="实物标签或外部样品号（选填）"><el-input v-model="sampleCode" placeholder="留空时由系统生成编号" /></el-form-item
        ><el-form-item label="实际采样时间" required><el-date-picker v-model="sampledAt" type="datetime" value-format="YYYY-MM-DDTHH:mm:ssZ" placeholder="按原始采样记录填写" /></el-form-item><el-form-item label="抽样地"
          ><PagedReferenceSelect v-model="sampleRegion" label="抽样地" :loader="optionLoaders.regions!" :context-key="taskId" /></el-form-item></el-form
      ><template #footer
        ><el-button @click="sampleDialog = false">取消</el-button
        ><el-button type="primary" @click="registerSample"
          >登记</el-button
        ></template
      ></el-dialog
    >
    <el-button v-if="!preparationOnly&&canWrite && session?.status === 'signed'" @click="enrollmentDialog = true"
      >授权数据集样本</el-button
    >
    <el-dialog v-model="enrollmentDialog" title="授权已签发版本到数据集" width="min(520px,94vw)" top="3vh"
      ><el-select v-model="enrollmentDataset" filterable placeholder="选择接收数据集"
        ><el-option
          v-for="d in options.datasets"
          :key="d.value"
          :value="d.value"
          :label="d.label" /></el-select
      ><template #footer
        ><el-button @click="enrollmentDialog = false">取消</el-button
        ><el-button type="primary" :disabled="!enrollmentDataset" @click="enroll"
          >授权候选样本</el-button
        ></template
      ></el-dialog
    >
  </section>
</template>
<style scoped>
.measurement-panel {
  min-width:0;
  width:100%;
  max-width:100%;
  box-sizing:border-box;
  overflow-wrap:anywhere;
  border-top: 2px solid var(--el-border-color-light);
  margin-top: 24px;
  padding-top: 20px;
}
.measurement-panel header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
h2 {
  font-size: 18px;
  margin: 0;
}
header p {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.controls {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  margin: 14px 0;
}
.controls .el-input {
  max-width: 220px;
}
.controls .el-select{min-width:0;max-width:100%;width:300px;}
.controls .el-button + .el-button {
  margin-left: 0;
}
.import-box {
  border: 1px solid var(--el-border-color-light);
  padding: 14px;
  border-radius: 6px;
  margin-bottom: 16px;
}
.mapping {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.measurement-panel .el-table {
  margin-top: 14px;
}
.session-source{overflow-wrap:anywhere;}
@media (max-width: 640px) {
  .mapping {
    grid-template-columns: 1fr;
  }
  header {
    align-items: flex-start !important;
  }
}
</style>
