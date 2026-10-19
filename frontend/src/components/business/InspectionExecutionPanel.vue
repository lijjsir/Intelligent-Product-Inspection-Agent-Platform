<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {useRouter,useRoute} from 'vue-router';
import { useAuthStore } from "@/stores/auth.store";
import { extractApiErrorMessage } from "@/api/http";
import { inspectionExecutionApi as api } from "@/api/inspection-execution.api";
import type { ExecutionRun,ExecutionTaskContext } from "@/types/inspection-execution.types";
import KnowledgeSubmitDialog from "./KnowledgeSubmitDialog.vue";
import PagedReferenceSelect from './supervision/PagedReferenceSelect.vue';
import type {ReferenceLoader} from '@/api/supervision.api';

const props = defineProps<{ taskId: string }>();
const auth = useAuthStore();
const router=useRouter();
const route=useRoute();
let contextEpoch=0,loadEpoch=0;
const sessionOptions:ReferenceLoader=async query=>(await api.referencePage(props.taskId,'sessions',query)).data.data;
const policyOptions:ReferenceLoader=async query=>(await api.referencePage(props.taskId,'policies',query)).data.data;
const sampleOptions:ReferenceLoader=async query=>{
  const additional=(taskContext.value?.samples||[]).filter(sample=>sample.kind!=='platform_sample');
  const extraIds=new Set(additional.map(sample=>sample.id));
  const result=(await api.referencePage(props.taskId,'samples',{...query,selected_ids:query.selected_ids.filter(id=>!extraIds.has(id))})).data.data;
  const extra=additional.map(sample=>({value:sample.id,label:`${sample.label} · ${sample.kind==='report_sample'?'报告原样品':'实物样品'}`}));
  const matching=extra.filter(item=>!query.keyword||item.label.includes(query.keyword));
  if(query.page===1)result.items.unshift(...matching);
  result.selected.push(...extra.filter(item=>query.selected_ids.includes(item.value)));
  if(result.total!==null)result.total+=matching.length;
  return result;
};
async function refreshSelectedContext(){
  const key=++contextEpoch,target=props.taskId;
  busy.value=true;error.value='';
  try{const result=(await api.selectedContext(target,{session_id:form.session_id||null,sample_ids:form.samples,policy_id:form.policy_id||null})).data.data;
    if(key===contextEpoch&&target===props.taskId)applyContext(result);
  }catch(e){if(key===contextEpoch){taskContext.value=null;error.value=extractApiErrorMessage(e,'所选任务资料无法核对，请重新打开执行表单');}}
  finally{if(key===contextEpoch)busy.value=false;}
}
const rows = ref<ExecutionRun[]>([]);
const runPage=ref(1),runTotal=ref(0),runKeyword=ref('');
const requirements = ref<any[]>([]);
const selected = ref<string[]>([]);
const current = ref<ExecutionRun | null>(null);
const busy = ref(false);
const loading = ref(false);
const error = ref("");
const dialog = ref(false);
const drawer = ref(false);
const reviewOpen = ref(false);
const knowledgeOpen = ref(false);
const taskContext=ref<ExecutionTaskContext|null>(null);
const reportLinkOpen=ref(false);
const reportCandidates=ref<any[]>([]);
const reportLink=reactive({selected:'',samples:'',reason:''});

const form = reactive({
  product_category: "",
  production_date: null as string | null,
  session_id: "",
  samples: [] as string[],
  policy_id: "",
  imageViews:{} as Record<string,string>,
  evidence: [] as EvidenceDraft[],
});

const reviewForm = reactive({
  decision: "accept",
  reason: "",
  evidence: "",
  reportVerified: false,
  verifiedIds: [] as string[],
});
const reportOpen=ref(false);
const reportUrl=ref("");
const reportTitle=ref("");
const reportObservations=computed(()=>Array.from(new Map((current.value?.snapshot.observations || [])
  .filter((item:any)=>item.kind==='report_attachment').map((item:any)=>[item.evidence_id,item])).values()) as any[]);
const reviewReady=computed(()=>reviewForm.reason.trim().length>=4 && (reviewForm.decision!=='accept' ||
  (reviewAcceptAllowed.value && !!reviewForm.evidence.trim() && (!reportObservations.value.length ||
    (reviewForm.reportVerified && reportObservations.value.every(item=>reviewForm.verifiedIds.includes(item.evidence_id)))))));

async function openReport(item:any){
  if(!current.value)return;
  try{
    const result=await api.report(current.value.id,item.attachment_id);
    if(reportUrl.value)URL.revokeObjectURL(reportUrl.value.split('#')[0]!);
    reportUrl.value=URL.createObjectURL(result.data as unknown as Blob)+`#page=${item.report_page}`;
    reportTitle.value=`${item.file_name} · 第 ${item.report_page} 页`;
    reportOpen.value=true;
  }catch(cause){error.value=extractApiErrorMessage(cause,"原报告无法取得，请补充证据后复核");}
}
async function openDraftReport(item:EvidenceDraft){
  if(!item.id)return;
  try{
    const result=await api.taskReport(props.taskId,item.id);
    if(reportUrl.value)URL.revokeObjectURL(reportUrl.value.split('#')[0]!);
    reportUrl.value=URL.createObjectURL(result.data as unknown as Blob)+`#page=${item.report_page||1}`;
    reportTitle.value=`${taskContext.value?.reports.find(r=>r.attachment_id===item.id)?.file_name||'检测报告'} · 第 ${item.report_page||1} 页`;
    reportOpen.value=true;
  }catch(cause){error.value=extractApiErrorMessage(cause,'报告原件无法取得，请先核对来源关联');}
}
onBeforeUnmount(()=>{++contextEpoch;++loadEpoch;if(reportUrl.value)URL.revokeObjectURL(reportUrl.value.split('#')[0]!);});

type EvidenceDraft = {
  kind: "measurement_record" | "report_attachment";
  id: string;
  measurement_key: string;
  sample_id: string;
  value: number | null;
  unit: string;
  method: string;
  conditions: Record<string,any>;
  uncertainty: number | null;
  report_page: number | null;
  report_item: string;
  requirement_ref:string;
};

function emptyEvidence(): EvidenceDraft {
  return {
    kind: "measurement_record",
    id: "",
    measurement_key: "",
    sample_id: "",
    value: null,
    unit: "",
    method: "",
    conditions: {},
    uncertainty: null,
    report_page: null,
    report_item: "",
    requirement_ref:'',
  };
}

const sampleIds = computed(() => form.samples);
const usableRequirements=computed(()=>requirements.value.filter(item=>['inspection_requirement','method_condition'].includes(item.candidate_type)&&
  (!form.product_category||item.product_category===form.product_category)));
const selectedRequirements=computed(()=>usableRequirements.value.filter(item=>selected.value.includes(`${item.revision_id}:${item.id}`)));
const selectedPolicy=computed(()=>taskContext.value?.policies.find(item=>item.id===form.policy_id));
const sessionMeasurements=computed(()=>taskContext.value?.measurements.filter(item=>item.session_id===form.session_id)||[]);
const sampleLabel=(id:string)=>taskContext.value?.samples.find(item=>item.id===id)?.label||current.value?.snapshot.task_context?.selected_samples?.find(item=>item.id===id)?.label||id;
const requirementType=(value:string)=>({inspection_requirement:'产品检测要求',method_condition:'试验方法 / 条件',body_clause:'参考正文',unclassified:'用途待核对'} as Record<string,string>)[value]||'用途待核对';
function applyContext(value:ExecutionTaskContext,reset=false){
  taskContext.value=value;
  if(reset){
    form.product_category=value.task_scope.product_category;form.production_date=value.task_scope.production_date;
    const requested=typeof route.query.session==='string'?route.query.session:'';
    form.session_id=requested ? (value.sessions.some(item=>item.id===requested)?requested:'') : value.sessions.length===1?value.sessions[0]!.id:'';form.samples=[];
    form.production_date=value.task_scope.production_date||value.sessions.find(item=>item.id===form.session_id)?.production_date||null;
    form.policy_id=value.policies.find(item=>!item.issues.length)?.id||'';
    form.imageViews=Object.fromEntries(value.images.map(item=>[item.image_hash,item.view]));
  }
}
function chooseMeasurement(item:EvidenceDraft){
  const original=taskContext.value?.measurements.find(m=>m.id===item.id);
  if(!original)return;
  Object.assign(item,{sample_id:original.sample_id,measurement_key:original.data.item,value:original.data.value,
    unit:original.data.unit,method:original.data.method,conditions:{...(original.data.conditions||{})},uncertainty:original.data.uncertainty??null});
  if(!form.samples.includes(original.sample_id))form.samples.push(original.sample_id);
}
function resetEvidence(item:EvidenceDraft){const kind=item.kind;Object.assign(item,emptyEvidence(),{kind});}
function measurementLabel(item:any){return `${sampleLabel(item.sample_id)} · ${usableRequirements.value.find(r=>r.measurement_key===item.data.item)?.indicator||item.data.item} · ${item.data.value} ${item.data.unit} · ${item.data.measured_at||'测量时间待补齐'}`;}
function measurementDisabled(item:any){return item.validation_status!=='accepted'||item.data.quality_flag!=='valid'||!item.data.measured_at||!taskContext.value?.samples.some(s=>s.id===item.sample_id);}
function conditionLabel(key:string){return ({mode:'试验模式',temperature_c:'温度（℃）',tolerance_c:'允许温差（℃）',ratio:'比例',depth_mm:'距离或深度（mm）',notes:'其他试验条件'} as Record<string,string>)[key]||key;}
function chooseReport(item:EvidenceDraft){
  const report=taskContext.value?.reports.find(r=>r.attachment_id===item.id);
  item.sample_id=report?.samples.length===1?report.samples[0]!.id:'';
  if(item.sample_id&&!form.samples.includes(item.sample_id))form.samples.push(item.sample_id);
}
function chooseRequirement(item:EvidenceDraft){
  const rule=selectedRequirements.value.find(r=>`${r.revision_id}:${r.id}`===item.requirement_ref);
  if(!rule)return;
  item.measurement_key=rule.measurement_key;item.unit=rule.unit;item.method='';
  item.conditions=Object.fromEntries(Object.keys(rule.expected_conditions||{}).map(key=>[key,null]));
}
function conditionFields(item:EvidenceDraft){
  const rule=selectedRequirements.value.find(r=>`${r.revision_id}:${r.id}`===item.requirement_ref);
  return Object.entries(rule?.expected_conditions||{}).map(([key,value])=>({key,value,type:typeof value}));
}
watch(()=>form.session_id,()=>{for(const item of form.evidence)if(item.kind==='measurement_record')Object.assign(item,emptyEvidence());if(!taskContext.value?.task_scope.production_date)form.production_date=taskContext.value?.sessions.find(item=>item.id===form.session_id)?.production_date||null;});

async function openReportLink(){
  busy.value=true;error.value='';
  try{reportCandidates.value=(await api.reportCandidates(props.taskId)).data.data;Object.assign(reportLink,{selected:'',samples:'',reason:''});reportLinkOpen.value=true;}
  catch(cause){error.value=extractApiErrorMessage(cause,'检测报告资料暂时无法读取');}finally{busy.value=false;}
}
async function saveReportLink(){
  const choice=reportCandidates.value.find(item=>`${item.source_record_id}:${item.attachment_id}`===reportLink.selected);
  if(!choice||!taskContext.value)return;
  busy.value=true;error.value='';
  try{applyContext((await api.linkReport(props.taskId,{request_key:crypto.randomUUID(),expected_context_hash:taskContext.value.context_hash,
    source_record_id:choice.source_record_id,attachment_id:choice.attachment_id,sample_codes:reportLink.samples.split('\n').map(s=>s.trim()).filter(Boolean),reason:reportLink.reason.trim()})).data.data);
    reportLinkOpen.value=false;ElMessage.success('报告及原样品已关联到本任务');}
  catch(cause){error.value=extractApiErrorMessage(cause,'关联失败，请刷新任务并核对报告来源');}finally{busy.value=false;}
}
const canReview = computed(
  () => auth.primaryRole === "expert" && auth.hasPermission("inspection_execution_review") &&
    current.value?.created_by !== auth.userId && current.value?.status === "draft",
);
const canCreate = computed(() => auth.hasPermission("inspection_execution"));
const verdictMeta: Record<string, { label: string; tone: "success" | "danger" | "warning" | "info"; description: string }> = {
  pass: { label: "选定项目符合要求", tone: "success", description: "当前选定项目的证据和条件满足已发布标准限值。" },
  fail: { label: "存在不符合项目", tone: "danger", description: "至少一项实测结果超出已发布标准限值，需要专家确认不符合结论。" },
  uncertain: { label: "条件或结果不确定", tone: "warning", description: "证据存在缺口、条件不匹配或测量区间与限值重叠，暂不能形成确定结论。" },
  incomplete: { label: "检测或依据尚不完整", tone: "warning", description: "标准来源、样品证据或必要条件尚未补齐，不能直接判定合格。" },
  manual_required: { label: "需人工核对", tone: "warning", description: "该要求尚未配置为可自动计算的数值规则，需要专家按原文和证据人工核验。" },
  missing: { label: "缺少测量依据", tone: "warning", description: "当前样品没有与该检测项目匹配的有效观测或报告转录值。" },
};
const statusLabel = (value: string) => ({
  pass: "选定项目符合要求",
  fail: "存在不符合项目",
  incomplete: "检测或依据尚不完整",
  manual_required: "需人工核对",
  uncertain: "条件或结果不确定",
  missing: "缺少测量依据",
  draft: "待独立复核",
  accepted: "专家已确认",
  rejected: "已驳回",
  awaiting_evidence: "等待补充证据",
  needs_reassessment: "需重新评估",
} as Record<string, string>)[value] || value || "未标记";
const verdictInfo = (value?: string | null) => verdictMeta[value || ""] || {
  label: statusLabel(value || ""), tone: "info" as const, description: "当前状态暂无更多说明。",
};
const effectiveStatus = (row: ExecutionRun) => row.current_source_issues?.length ? "needs_reassessment" : row.status;
function runVerdict(run:ExecutionRun|null){
  const original=verdictInfo(run?.evaluation?.item_verdict);
  if(run?.evaluation?.checks.length&&run.evaluation.checks.every(item=>item.candidate_type==='method_condition')){
    return {...original,label:run.evaluation.item_verdict==='pass'?'试验条件符合要求':run.evaluation.item_verdict==='fail'?'试验条件不符合要求':original.label,
      description:'本次只核对试验方法或条件，产品性能项目尚未评定。'};
  }
  return original;
}
const currentVerdict = computed(() => runVerdict(current.value));
const currentMissingInputs = computed(() => Array.from(new Set([
  ...(current.value?.current_source_issues || []),
  ...(current.value?.evaluation?.missing_inputs || []),
])));
const currentReviewReasons = computed(() => current.value?.evaluation?.review_reasons || []);
const checkCount = computed(() => {
  const checks = current.value?.evaluation?.checks || [];
  return {
    total: checks.length,
    pass: checks.filter((item: any) => item.status === "pass").length,
    fail: checks.filter((item: any) => item.status === "fail").length,
    attention: checks.filter((item: any) => !["pass", "fail"].includes(item.status)).length,
  };
});
const reviewAcceptAllowed = computed(() => ["pass", "fail"].includes(current.value?.evaluation?.item_verdict || "") && !currentMissingInputs.value.length);

async function load() {
  const key=++loadEpoch,target=props.taskId;
  rows.value=[];
  loading.value = true;
  error.value = "";
  try {
    const result=(await api.page(target,runPage.value,runKeyword.value)).data.data;
    if(key===loadEpoch && target===props.taskId){rows.value=result.items;runTotal.value=result.total;}
  } catch (cause) {
    if(key===loadEpoch){current.value=null;drawer.value=false;runTotal.value=0;error.value = extractApiErrorMessage(cause, "执行记录暂时无法加载，请确认后端已更新到检测执行版本");}
  } finally {
    if(key===loadEpoch)loading.value = false;
  }
}

defineExpose({openCreate});
async function openCreate() {
  if(busy.value||loading.value)return;
  const target=props.taskId,key=++contextEpoch;
  busy.value = true;
  error.value = "";
  try {
    const linkedSession=typeof route.query.session==='string'?route.query.session:null;
    const [requirementResponse,contextResponse]=await Promise.all([api.requirements(props.taskId,{suppressErrorToast:true}),linkedSession?api.selectedContext(props.taskId,{session_id:linkedSession,sample_ids:[],policy_id:null}):api.context(props.taskId,{suppressErrorToast:true})]);
    if(key!==contextEpoch||target!==props.taskId)return;
    if(linkedSession&&!contextResponse.data.data.sessions.some(item=>item.id===linkedSession))throw new Error('链接的检测批次不属于当前任务或已不可用');
    requirements.value=requirementResponse.data.data;
    selected.value = [];
    applyContext(contextResponse.data.data,true);
    form.evidence = [{...emptyEvidence(),kind:contextResponse.data.data.sessions.length?'measurement_record':'report_attachment'}];
    dialog.value = true;
  } catch (cause) {
    if(key===contextEpoch&&target===props.taskId)error.value = extractApiErrorMessage(cause, "无法读取已发布检测要求，请先确认标准要求已发布");
  } finally {
    if(key===contextEpoch&&target===props.taskId)busy.value = false;
  }
}

function addEvidence() {
  form.evidence.push(emptyEvidence());
}

function applyCaseDraft(){
  const plan=taskContext.value?.case_preparation;
  if(!plan)return;
  if(form.evidence.some(item=>item.id||item.measurement_key)){
    ElMessage.warning('当前已有填写内容，请先核对或移除，避免覆盖。');return;
  }
  const report=taskContext.value?.reports.find(r=>r.attachment_id===plan.report_attachment_id&&!r.issues.length);
  const sample=report?.samples[0];
  const refs=plan.standard_refs.filter(r=>plan.initial_execution_keys.includes(r.measurement_key));
  if(!sample||!refs.length||refs.some(r=>!usableRequirements.value.some(item=>item.revision_id===r.revision_id&&item.id===r.candidate_id))){
    ElMessage.warning('首轮条款尚未确认发布，或报告来源不可用；请先完成标准核对并刷新。');return;
  }
  const drafts:EvidenceDraft[]=[];
  for(const ref of refs){
    const source=plan.planned_items.find(p=>p.measurement_key===ref.measurement_key);
    if(!source){ElMessage.warning('案例转录资料不完整，请重新核对。');return;}
    drafts.push({...emptyEvidence(),kind:'report_attachment',id:plan.report_attachment_id,sample_id:sample.id,
      measurement_key:source.measurement_key,value:source.value,unit:source.unit,method:source.method,
      conditions:{...source.conditions_values},report_page:source.report_page,report_item:source.report_item,
      requirement_ref:`${ref.revision_id}:${ref.candidate_id}`});
  }
  selected.value=refs.map(r=>`${r.revision_id}:${r.candidate_id}`);form.samples=[sample.id];form.evidence=drafts;
  ElMessage.info('已带入首轮报告转录；原文、方法及数值仍须逐项核对，不会复制成多次观测。');
}

function removeEvidence(index: number) {
  form.evidence.splice(index, 1);
  if (!form.evidence.length) addEvidence();
}

function parseEvidence() {
  return form.evidence.filter((item) => item.id.trim() || item.measurement_key.trim()).map((item) => {
    const conditions: Record<string, unknown> = {};
    for(const [key,value] of Object.entries(item.conditions))if(value!==null&&value!==undefined&&value!=='')conditions[key]=value;
    return {
      kind: item.kind,
      id: item.id.trim(),
      measurement_key: item.measurement_key.trim(),
      sample_id: item.sample_id.trim(),
      value: item.value,
      unit: item.unit.trim(),
      method: item.method.trim(),
      conditions,
      uncertainty: item.uncertainty,
      report_page: item.kind === "report_attachment" ? item.report_page : null,
      report_item: item.kind === "report_attachment" ? item.report_item.trim() : "",
    };
  });
}

async function create() {
  if(busy.value||!taskContext.value)return;
  const target=props.taskId,key=contextEpoch;
  if (!selected.value.length || !form.product_category.trim() || !form.production_date || sampleIds.value.length === 0) {
    error.value = "请补齐产品类别、生产日期、样品编号和至少一项标准检测要求";
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    const refs = requirements.value
      .filter((item) => selected.value.includes(`${item.revision_id}:${item.id}`))
      .map((item) => ({ revision_id: item.revision_id, candidate_id: item.id }));
    const created = (await api.create({
      request_key: crypto.randomUUID(),
      task_id: props.taskId,
      session_id: form.session_id.trim() || null,
      product_category: form.product_category.trim(),
      production_date: form.production_date,
      requirements: refs,
      sample_ids: sampleIds.value,
      observations: parseEvidence(),
      policy_id: form.policy_id||null,
      context_hash:taskContext.value?.context_hash,
      image_view_assignments:Object.entries(form.imageViews).filter(([,view])=>!!view).map(([image_hash,view])=>({image_hash,view})),
    })).data.data;
    if(target!==props.taskId||key!==contextEpoch)return;
    current.value=created;
    dialog.value = false;
    drawer.value = true;
    await load();
  } catch (cause: any) {
    if(target===props.taskId&&key===contextEpoch)error.value = extractApiErrorMessage(cause, cause?.message || "执行未完成，请核对标准要求和证据来源");
  } finally {
    if(target===props.taskId&&key===contextEpoch)busy.value = false;
  }
}

async function show(row: ExecutionRun) {
  busy.value = true;
  error.value = "";
  try {
    current.value = (await api.detail(row.id, { suppressErrorToast: true })).data.data;
    drawer.value = true;
  } catch (cause) {
    error.value = extractApiErrorMessage(cause, "执行结果暂时无法打开");
  } finally {
    busy.value = false;
  }
}

function openReview() {
  reviewForm.decision = reviewAcceptAllowed.value ? "accept" : "request_evidence";
  reviewForm.reason = "";
  reviewForm.evidence = "";
  reviewForm.reportVerified = false;
  reviewForm.verifiedIds=[];
  reviewOpen.value = true;
}

async function review() {
  if (!current.value) return;
  if (reviewForm.decision === "accept" && !reviewAcceptAllowed.value) {
    error.value = "当前证据或标准来源不完整，只能选择“需补充证据”或“驳回本次执行”";
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    current.value = (await api.review(current.value.id, {
      expected_version: current.value.row_version,
      request_key: crypto.randomUUID(),
      decision: reviewForm.decision,
      reason: reviewForm.reason.trim(),
      report_values_verified: reviewForm.reportVerified,
      verified_evidence_ids: reviewForm.verifiedIds,
      evidence_refs: reviewForm.evidence.split("\n").map((item) => item.trim()).filter(Boolean),
    })).data.data;
    reviewOpen.value = false;
    await load();
    ElMessage.success("独立复核已记录");
  } catch (cause) {
    error.value = extractApiErrorMessage(cause, "复核未完成，请检查缺少的证据或复核说明");
  } finally {
    busy.value = false;
  }
}

watch(()=>props.taskId,()=>{++contextEpoch;runPage.value=1;runKeyword.value='';dialog.value=false;drawer.value=false;taskContext.value=null;current.value=null;busy.value=false;void load();},{immediate:true});
</script>

<template>
  <section class="execution-panel">
    <header class="execution-heading">
      <div>
        <p class="eyebrow">标准执行 / 证据留痕</p>
        <h3>标准要求执行与独立复核</h3>
        <p class="muted">图片只用于外观观察；尺寸、温度、质量和试验条件必须引用实测记录或检测报告。</p>
      </div>
      <div class="heading-actions">
        <el-button v-if="rows.length&&auth.hasPermission('result')" @click="router.push(`/app/results/${taskId}`)">查看统一结果与报告</el-button>
        <el-button @click="load">刷新</el-button>
        <el-button v-if="canCreate" type="primary" :disabled="busy||loading" @click="openCreate">新建执行记录</el-button>
      </div>
    </header>

    <el-alert v-if="error" :title="error" type="warning" show-icon :closable="false" />
    <el-form @submit.prevent="runPage=1;load()"><el-input v-model="runKeyword" aria-label="执行记录编号搜索" placeholder="输入执行记录编号搜索" :maxlength="200" clearable /><el-button native-type="submit">搜索执行记录</el-button></el-form>
    <el-table v-loading="loading" :data="rows" empty-text="本任务还没有标准执行记录">
      <el-table-column label="项目判定" min-width="190"><template #default="{ row }"><el-tag :type="runVerdict(row).tone">{{ runVerdict(row).label }}</el-tag></template></el-table-column>
      <el-table-column label="复核状态" width="140"><template #default="{ row }"><el-tag :type="effectiveStatus(row) === 'accepted' ? 'success' : effectiveStatus(row) === 'rejected' ? 'danger' : effectiveStatus(row) === 'needs_reassessment' ? 'danger' : 'warning'">{{ statusLabel(effectiveStatus(row)) }}</el-tag></template></el-table-column>
      <el-table-column label="依据状态" min-width="200"><template #default="{ row }"><span :class="['source-state', row.current_source_issues?.length ? 'is-invalid' : 'is-valid']"><i />{{ row.current_source_issues?.length ? "标准或证据已变化，需重新评估" : "来源可追溯" }}</span></template></el-table-column>
      <el-table-column label="创建时间" prop="created_at" width="180" />
      <el-table-column label="操作" width="160"><template #default="{ row }"><el-button link type="primary" @click="show(row)">查看执行详情</el-button></template></el-table-column>
    </el-table>
    <el-pagination layout="prev,pager,next,total" :page-size="20" :total="runTotal" :current-page="runPage" :disabled="loading||busy" @current-change="runPage=$event;load()" />

    <el-dialog v-model="dialog" class="execution-create-dialog" title="新建标准执行记录" width="min(980px, 94vw)" top="5vh" append-to-body :close-on-click-modal="false">
      <el-alert title="标准限值来自已确认、已发布的标准要求。提交后，本任务的独立复核专家可核对引用原件；私有资料仍只在本次复核范围内使用。" type="info" :closable="false" />
      <el-form label-position="top" class="execution-form">
        <el-alert v-if="error" :title="error" type="warning" :closable="false" />
        <el-alert v-if="taskContext&&(taskContext.truncated.samples||taskContext.truncated.sessions)" title="会话、样品和策略支持分页搜索；选中后会重新核对本任务的资料范围。" type="info" :closable="false"/>
        <el-alert v-if="taskContext?.truncated.measurements" title="当前会话测量记录较多，显示的读数可能不完整；缺少目标记录时请核对原始来源。" type="warning" :closable="false"/>
        <el-alert v-if="taskContext?.task_scope.issues.length" :title="taskContext.task_scope.issues.join('；')" type="warning" :closable="false"/>
        <el-button v-if="taskContext?.case_preparation" plain type="primary" @click="applyCaseDraft">带入本案首轮报告转录</el-button>
        <div v-if="taskContext" class="task-scope-strip"><div><span>本次任务对象</span><strong>{{ taskContext.task_scope.product_name }}</strong></div><div><span>生产批次</span><strong>{{ taskContext.task_scope.production_batch_ref||'尚未关联' }}</strong></div><div><span>输入类型</span><strong>{{ ({image:'图片辅助',measurement:'设备测量',mixed:'混合资料',report:'检测报告'} as Record<string,string>)[taskContext.task_scope.input_mode] }}</strong></div></div>
        <div class="form-section">
          <div class="section-title"><span>01</span><div><h4>任务范围</h4><p>先确定本次实际检测对应的产品和样品。</p></div></div>
          <div class="form-grid two">
            <el-form-item label="产品类别" required><el-input v-model="form.product_category" :disabled="!!taskContext?.task_scope.product_category" placeholder="补齐本任务实际产品类别" /></el-form-item>
            <el-form-item label="实际生产日期" required><el-date-picker v-model="form.production_date" :disabled="!!taskContext?.task_scope.production_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
            <el-form-item label="本次样品" required><PagedReferenceSelect v-model="form.samples" multiple :selection-limit="500" label="本次样品" :loader="sampleOptions" :context-key="taskId" :disabled="busy" @update:model-value="refreshSelectedContext" /><p v-if="!taskContext?.samples.length" class="field-hint">暂无关联样品。实测样品请先在实验检测登记；报告样品可通过下方关联入口加入。</p></el-form-item>
            <el-form-item label="检测会话（引用实测记录时必选）"><PagedReferenceSelect v-model="form.session_id" label="检测会话" :loader="sessionOptions" :context-key="taskId" :disabled="busy" @update:model-value="refreshSelectedContext" /></el-form-item>
          </div>
        </div>

        <div class="form-section">
          <div class="section-title"><span>02</span><div><h4>标准检测要求</h4><p>只选择本次确实有证据支持的条款。</p></div></div>
          <el-checkbox-group v-model="selected" class="requirement-list">
            <label v-for="item in requirements" :key="`${item.revision_id}:${item.id}`" class="requirement-option">
              <el-checkbox :value="`${item.revision_id}:${item.id}`" :disabled="!usableRequirements.some(rule=>rule.id===item.id&&rule.revision_id===item.revision_id)" />
              <span><strong>{{ item.indicator || "未命名项目" }}</strong><small>{{ item.standard_no }} · {{ item.clause_no }} · {{ item.unit || "无单位" }}</small><el-tag size="small" effect="plain">{{ requirementType(item.candidate_type) }}</el-tag></span>
            </label>
          </el-checkbox-group>
          <el-empty v-if="!usableRequirements.length" description="暂无用途已核对的可执行要求，请由专家核对分类并发布新稿" :image-size="60" />
        </div>

        <div class="form-section"><div class="section-title"><span>03</span><div><h4>执行与复核策略</h4><p>产品限值来自标准；策略检查本任务的材料完整性。</p></div></div><el-form-item label="已发布适用策略"><PagedReferenceSelect v-model="form.policy_id" label="已发布适用策略" :clearable="!taskContext?.policies.some(p=>!p.issues.length)" :loader="policyOptions" :context-key="taskId" :disabled="busy" @update:model-value="refreshSelectedContext" /></el-form-item><div v-if="selectedPolicy" class="policy-summary"><span>独立专业复核</span><span>图片 {{ selectedPolicy.snapshot.required_image_count||0 }} 张</span><span>视角 {{ selectedPolicy.snapshot.required_views?.join('、')||'无特定要求' }}</span><p class="muted">图片要求适用于图片及混合输入；报告和纯测量任务按对应材料检查。</p></div><div v-if="selectedPolicy?.snapshot.required_views?.length&&['image','mixed'].includes(taskContext?.task_scope.input_mode||'')" class="form-grid two"><el-form-item v-for="image in taskContext?.images||[]" :key="image.image_hash" :label="`任务图片 ${image.index+1} 的实际视角`"><el-select v-model="form.imageViews[image.image_hash]" clearable placeholder="对照任务图片标注"><el-option v-for="view in selectedPolicy.snapshot.required_views" :key="view" :label="view" :value="view"/></el-select></el-form-item></div></div>
        <div class="form-section">
          <div class="section-title"><span>04</span><div><h4>证据来源</h4><p>实测值引用原始记录；报告值需逐项登记并独立复核。</p></div><el-button size="small" plain @click="openReportLink">关联已有检测报告</el-button><el-button size="small" plain @click="addEvidence">添加证据</el-button></div>
          <div v-for="(item, index) in form.evidence" :key="index" class="evidence-card">
            <div class="evidence-card-head"><strong>证据 {{ index + 1 }}</strong><el-button v-if="item.kind==='report_attachment'&&item.id" link type="primary" @click="openDraftReport(item)">查看报告原件</el-button><el-button link type="danger" @click="removeEvidence(index)">移除</el-button></div>
            <div class="form-grid two">
              <el-form-item label="来源类型"><el-radio-group v-model="item.kind" @change="resetEvidence(item)"><el-radio-button label="measurement_record">实测记录</el-radio-button><el-radio-button label="report_attachment">检测报告</el-radio-button></el-radio-group></el-form-item>
              <el-form-item v-if="item.kind==='measurement_record'" label="任务原始测量记录" required><el-select v-model="item.id" filterable style="width:100%" :disabled="!form.session_id" placeholder="先选择会话，再选择原始读数" @change="chooseMeasurement(item)"><el-option v-for="measurement in sessionMeasurements" :key="measurement.id" :value="measurement.id" :label="measurementLabel(measurement)" :disabled="measurementDisabled(measurement)"/></el-select></el-form-item>
              <el-form-item v-else label="已关联检测报告" required><el-select v-model="item.id" filterable style="width:100%" placeholder="从本任务已关联报告选择" @change="chooseReport(item)"><el-option v-for="report in taskContext?.reports||[]" :key="report.attachment_id" :value="report.attachment_id" :disabled="!!report.issues.length" :label="report.file_name||'报告来源需重新核对'"/></el-select></el-form-item>
              <el-form-item v-if="item.kind==='report_attachment'" label="对应标准项目" required><el-select v-model="item.requirement_ref" style="width:100%" placeholder="先选择本次标准检测要求" @change="chooseRequirement(item)"><el-option v-for="rule in selectedRequirements" :key="`${rule.revision_id}:${rule.id}`" :value="`${rule.revision_id}:${rule.id}`" :label="`${rule.indicator} · ${rule.clause_no}`"/></el-select></el-form-item>
              <el-form-item v-else label="测量项目"><el-input :model-value="usableRequirements.find(r=>r.measurement_key===item.measurement_key)?.indicator||item.measurement_key" disabled /></el-form-item>
              <el-form-item label="证据对应样品" required><el-select v-model="item.sample_id" style="width:100%" :disabled="item.kind==='measurement_record'"><el-option v-for="sample in item.kind==='report_attachment'?(taskContext?.reports.find(r=>r.attachment_id===item.id)?.samples||[]):(taskContext?.samples||[])" :key="sample.id" :label="sample.label" :value="sample.id"/></el-select></el-form-item>
              <el-form-item :label="item.kind==='measurement_record'?'原始实测值（只读）':'报告原文数值'"><el-input-number v-model="item.value" :disabled="item.kind==='measurement_record'" :controls="false" style="width:100%" /></el-form-item>
              <el-form-item label="单位"><el-input v-model="item.unit" :disabled="item.kind==='measurement_record'" /></el-form-item>
              <el-form-item label="报告 / 实测方法"><el-input v-model="item.method" :disabled="item.kind==='measurement_record'" placeholder="按原报告方法填写，须与标准已确认方法对应" /></el-form-item>
              <el-form-item label="不确定度（可选）"><el-input-number v-model="item.uncertainty" :disabled="item.kind==='measurement_record'" :min="0" :controls="false" style="width:100%" /></el-form-item>
              <template v-if="item.kind === 'report_attachment'">
                <el-form-item label="报告页码" required><el-input-number v-model="item.report_page" :min="1" :max="taskContext?.reports.find(r=>r.attachment_id===item.id)?.page_count" :controls="false" style="width:100%" /></el-form-item>
                <el-form-item label="报告原文项目" required><el-input v-model="item.report_item" placeholder="与 PDF 中的项目名称一致" /></el-form-item>
              </template>
              <div class="conditions-block wide-field"><div class="conditions-heading"><strong>实际试验条件</strong><span>从测量记录读取，或对照报告逐项填写。</span></div><div v-if="item.kind==='measurement_record'" class="condition-readings"><p v-for="(value,key) in item.conditions" :key="key">{{ conditionLabel(String(key)) }}：{{ value }}</p><p v-if="!Object.keys(item.conditions).length" class="muted">原测量记录没有附加条件。</p></div><div v-else class="form-grid two"><el-form-item v-for="field in conditionFields(item)" :key="field.key" :label="conditionLabel(field.key)"><el-input-number v-if="field.type==='number'" v-model="item.conditions[field.key]" :controls="false" style="width:100%"/><el-select v-else-if="field.type==='boolean'" v-model="item.conditions[field.key]" placeholder="尚未核对"><el-option label="是" :value="true"/><el-option label="否" :value="false"/></el-select><el-input v-else v-model="item.conditions[field.key]" placeholder="从原报告核对实际条件"/><small class="muted">标准要求：{{ field.value }}</small></el-form-item></div></div>
            </div>
          </div>
        </div>
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" :loading="busy" @click="create">保存证据并执行</el-button></template>
    </el-dialog>

    <el-dialog v-model="reportLinkOpen" title="关联已有检测报告" width="min(720px, 94vw)" append-to-body :close-on-click-modal="false"><el-alert title="从已接入的真实检测报告选择，核对产品对象及原样品编号。关联只供本任务使用，不发布为公共知识。" type="info" :closable="false"/><el-alert v-if="error" :title="error" type="warning" :closable="false"/><el-form label-position="top" class="review-form"><el-form-item label="检测报告资料" required><el-select v-model="reportLink.selected" filterable style="width:100%" placeholder="从已接入检测报告中选择"><el-option v-for="report in reportCandidates" :key="`${report.source_record_id}:${report.attachment_id}`" :value="`${report.source_record_id}:${report.attachment_id}`" :label="report.label" :disabled="!!report.issues.length"/></el-select><p v-if="!reportCandidates.length" class="field-hint">暂无授权的检测报告。请在资料接入上传 PDF，并明确资料类型为“检测报告”。</p></el-form-item><el-form-item label="报告原样品编号（每行一条）" required><el-input v-model="reportLink.samples" type="textarea" :rows="3" placeholder="对照原报告样品编号，保留原始命名"/></el-form-item><el-form-item label="报告与本任务对象的核对说明" required><el-input v-model="reportLink.reason" type="textarea" :rows="3" placeholder="说明产品、批次或单件与报告样品的对应关系；缺少的信息须明确记录"/></el-form-item></el-form><template #footer><el-button @click="reportLinkOpen=false">取消</el-button><el-button type="primary" :loading="busy" :disabled="!reportLink.selected||!reportLink.samples.trim()||reportLink.reason.trim().length<4" @click="saveReportLink">核对并关联到任务</el-button></template></el-dialog>
    <el-drawer v-model="drawer" class="execution-result-drawer" title="标准执行结果与证据" size="min(1120px, 96vw)" append-to-body>
      <template v-if="current">
        <div class="result-hero"><div><p class="eyebrow">冻结快照 / {{ current.id }}</p><div class="hero-title"><h2>{{ currentVerdict.label }}</h2><el-tag :type="currentVerdict.tone" effect="light">{{ currentVerdict.label }}</el-tag></div><p class="muted">复核状态：{{ statusLabel(current.status) }} · 风险等级：{{ current.evaluation?.risk_level === "unknown" ? "尚未专业评定" : current.evaluation?.risk_level }}</p></div><el-tag :type="current.effective_status === 'needs_reassessment' ? 'danger' : current.status === 'accepted' ? 'success' : current.status === 'rejected' ? 'danger' : 'warning'" effect="dark">{{ statusLabel(current.effective_status || current.status) }}</el-tag></div>
        <div class="verdict-explainer"><span class="verdict-mark" :class="`tone-${currentVerdict.tone}`" /><div><strong>{{ currentVerdict.label }}</strong><p>{{ currentVerdict.description }}</p></div></div>
        <div class="result-summary-grid"><div><span>已选检测项目</span><strong>{{ checkCount.total }}</strong></div><div><span>符合</span><strong class="text-success">{{ checkCount.pass }}</strong></div><div><span>不符合</span><strong class="text-danger">{{ checkCount.fail }}</strong></div><div><span>待处理</span><strong class="text-warning">{{ checkCount.attention }}</strong></div></div>
        <el-alert :title="current.evaluation?.boundary || '本记录只判定选定的标准项目，不代表整份标准或产品整体合格。'" type="info" :closable="false" />
        <div v-if="currentMissingInputs.length || currentReviewReasons.length" class="result-guidance-grid">
          <section v-if="currentMissingInputs.length" class="guidance-block attention-block"><div class="guidance-heading"><strong>需要处理</strong><span>{{ currentMissingInputs.length }} 项</span></div><ul><li v-for="issue in currentMissingInputs" :key="issue">{{ issue }}</li></ul></section>
          <section v-if="currentReviewReasons.length" class="guidance-block review-block"><div class="guidance-heading"><strong>复核要求</strong><span>{{ currentReviewReasons.length }} 项</span></div><ul><li v-for="reason in currentReviewReasons" :key="reason">{{ reason }}</li></ul></section>
        </div>
        <el-table :data="current.evaluation?.checks || []" class="result-table">
          <el-table-column label="样品" width="140"><template #default="{row}">{{ sampleLabel(row.sample_id) }}</template></el-table-column>
          <el-table-column prop="standard_no" label="标准" width="150" />
          <el-table-column prop="clause_no" label="条款" width="90" />
          <el-table-column prop="indicator" label="项目" min-width="180" />
          <el-table-column label="条款用途" width="145"><template #default="{row}">{{ requirementType(row.candidate_type) }}</template></el-table-column>
          <el-table-column label="判定" width="150"><template #default="{ row }"><div class="check-verdict"><el-tag :type="verdictInfo(row.status).tone">{{ verdictInfo(row.status).label }}</el-tag><small v-if="row.missing_inputs?.length">{{ row.missing_inputs.length }} 项待处理</small></div></template></el-table-column>
          <el-table-column label="证据与原因" min-width="300"><template #default="{ row }"><div v-for="finding in row.findings || []" :key="finding.evidence_id" class="finding-line"><strong>{{ finding.value ?? "—" }} {{ row.unit || "" }}</strong><small>{{ finding.evidence_id }}</small></div><span v-if="!row.findings?.length" class="muted">尚无有效证据</span><ul v-if="row.missing_inputs?.length" class="check-issues"><li v-for="issue in row.missing_inputs" :key="issue">{{ issue }}</li></ul></template></el-table-column>
        </el-table>
        <div v-if="canReview" class="review-callout"><div><strong>{{ reviewAcceptAllowed ? "结果已具备专家确认条件" : "当前结果不能直接确认" }}</strong><p>{{ reviewAcceptAllowed ? "请核对标准来源、测量方法和证据页码后记录独立复核。" : "先补充缺失证据或选择驳回；系统不会把不完整结果标记为合格。" }}</p></div><el-button type="primary" @click="openReview">{{ reviewAcceptAllowed ? "独立专业复核" : "处理复核意见" }}</el-button></div>
        <section v-if="current.review_history?.length" class="guidance-block"><strong>独立复核记录</strong><div v-for="action in current.review_history" :key="action.id"><p>{{ action.reason }}</p><ul><li v-for="reference in action.evidence_refs || []" :key="reference">{{ reference }}</li></ul><small>核验时间：{{ action.verification_snapshot?.checked_at || '历史记录未保存核验凭据' }} · 已核对报告项目：{{ action.verification_snapshot?.verified_evidence_ids?.length || 0 }}</small></div></section>
        <div class="drawer-actions"><el-button v-if="effectiveStatus(current) === 'accepted' && auth.hasPermission('knowledge_candidate_submit')" @click="knowledgeOpen = true">提出知识候选</el-button></div>
        <el-collapse class="snapshot-collapse"><el-collapse-item title="查看本次输入、标准来源和策略快照"><pre>{{ JSON.stringify(current.snapshot, null, 2) }}</pre></el-collapse-item></el-collapse>
      </template>
    </el-drawer>

    <el-dialog v-model="reviewOpen" class="execution-review-dialog" title="独立专业复核" width="min(680px, 92vw)" append-to-body>
      <el-alert title="专家复核只确认本次证据是否足以支持选定项目结论；风险等级仍在风险研判流程中单独确认。" type="info" :closable="false" />
      <el-form label-position="top" class="review-form"><el-form-item label="复核决定"><el-select v-model="reviewForm.decision" style="width: 100%"><el-option label="确认选定项目结论" value="accept" :disabled="!reviewAcceptAllowed" /><el-option label="需补充证据" value="request_evidence" /><el-option label="驳回本次执行" value="reject" /></el-select><p v-if="!reviewAcceptAllowed" class="field-hint">当前存在缺失证据、来源问题或未确定项目，只能先补证或驳回。</p></el-form-item><el-form-item label="复核说明" required><el-input v-model="reviewForm.reason" type="textarea" :rows="4" placeholder="说明你核对了哪些项目、条件和来源" /></el-form-item><el-form-item label="复核依据（每行一条）"><el-input v-model="reviewForm.evidence" type="textarea" :rows="3" placeholder="原报告页码、测量记录、设备校准记录等" /></el-form-item><el-checkbox v-model="reviewForm.reportVerified">涉及报告转录时，已逐项核对原 PDF 的项目、数值、方法、条件和页码</el-checkbox></el-form>
      <section v-if="reportObservations.length" class="report-review-list"><strong>逐项核对报告原件</strong><p class="muted">同一报告的重复引用不增加独立观测次数。</p><div v-for="item in reportObservations" :key="item.evidence_id" class="report-review-item"><el-checkbox-group v-model="reviewForm.verifiedIds"><el-checkbox :value="item.evidence_id">已核对 {{ item.report_item }} · {{ item.sample_label||sampleLabel(item.sample_id) }} · {{ item.value }} {{ item.unit }}</el-checkbox></el-checkbox-group><el-button link type="primary" @click="openReport(item)">查看原件第 {{ item.report_page }} 页</el-button><small>{{ item.method }}</small></div></section>
      <template #footer><el-button @click="reviewOpen = false">取消</el-button><el-button type="primary" :loading="busy" :disabled="!reviewReady" @click="review">确认并记录</el-button></template>
    </el-dialog>
    <el-dialog v-model="reportOpen" :title="reportTitle" width="min(1100px, 96vw)" append-to-body><a :href="reportUrl" target="_blank" rel="noopener">在新窗口查看原件</a><iframe v-if="reportOpen" :src="reportUrl" title="检测报告原件" style="width:100%;height:70vh;border:0" /></el-dialog>
    <KnowledgeSubmitDialog v-if="current" v-model="knowledgeOpen" source-kind="inspection_execution" :source-id="current.id" />
  </section>
</template>

<style scoped>
.execution-panel { display: grid; gap: 18px; margin: 18px 0; padding: 22px; border: 1px solid var(--piap-line, #dbe5f2); border-radius: 14px; background: #fff; box-shadow: 0 12px 28px rgba(35, 71, 122, .06); }
.execution-heading { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; padding-bottom: 16px; border-bottom: 1px solid var(--piap-line, #dbe5f2); }
.execution-heading h3, .result-hero h2 { margin: 3px 0 6px; color: var(--piap-ink, #16283f); }
.hero-title { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.hero-title h2 { margin-bottom: 0; }
.eyebrow { margin: 0; color: var(--piap-blue, #2563eb); font-size: 11px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }
.muted { margin: 0; color: var(--piap-muted, #64748b); font-size: 13px; line-height: 1.65; }
.source-state { display: inline-flex; align-items: center; gap: 7px; font-size: 13px; }
.source-state i { width: 7px; height: 7px; border-radius: 50%; background: #22a06b; box-shadow: 0 0 0 4px rgba(34, 160, 107, .12); }
.source-state.is-invalid { color: #b42318; }
.source-state.is-invalid i { background: #d92d20; box-shadow: 0 0 0 4px rgba(217, 45, 32, .12); }
.heading-actions, .drawer-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.form-section { display: grid; gap: 16px; padding: 18px; border: 1px solid #e4ebf4; border-radius: 12px; background: #fbfdff; }
.section-title { display: flex; align-items: center; gap: 12px; }
.section-title > span { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 8px; background: #e8f1ff; color: #2563eb; font-size: 12px; font-weight: 800; }
.section-title h4 { margin: 0; color: #1e293b; font-size: 15px; }
.section-title p { margin: 3px 0 0; color: #64748b; font-size: 12px; }
.section-title > .el-button { margin-left: auto; }
.form-grid { display: grid; gap: 0 16px; }
.form-grid.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.form-grid.four { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.wide-field { grid-column: 1 / -1; }
.requirement-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.requirement-option { display: flex; align-items: flex-start; gap: 8px; min-height: 68px; padding: 11px 12px; border: 1px solid #e3eaf4; border-radius: 10px; background: #fff; cursor: pointer; }
.requirement-option:hover { border-color: #9bbcf4; background: #f6faff; }
.requirement-option span { display: grid; gap: 5px; }
.requirement-option strong { color: #1e293b; font-size: 13px; }
.requirement-option small { color: #64748b; font-size: 11px; }
.evidence-card { display: grid; gap: 12px; padding: 14px; border: 1px solid #dae5f3; border-radius: 10px; background: #fff; }
.evidence-card-head { display: flex; align-items: center; justify-content: space-between; }
.conditions-block { display: grid; gap: 2px; margin-top: 2px; padding: 14px; border: 1px dashed #cbd9ec; border-radius: 10px; background: #f8fbff; }
.conditions-heading { display: flex; align-items: baseline; gap: 10px; margin-bottom: 4px; }
.conditions-heading strong { color: #334155; font-size: 13px; }
.conditions-heading span { color: #64748b; font-size: 12px; }
.result-hero { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; padding: 16px 0 18px; border-bottom: 1px solid #e5eaf2; }
.verdict-explainer { display: flex; align-items: flex-start; gap: 12px; margin-top: 18px; padding: 14px 16px; border: 1px solid #e2e8f0; border-radius: 12px; background: #f8fafc; }
.verdict-explainer strong { color: #1e293b; font-size: 14px; }
.verdict-explainer p { margin: 4px 0 0; color: #64748b; font-size: 13px; line-height: 1.6; }
.verdict-mark { flex: 0 0 auto; width: 9px; height: 9px; margin-top: 5px; border-radius: 50%; background: #64748b; box-shadow: 0 0 0 5px rgba(100, 116, 139, .13); }
.verdict-mark.tone-success { background: #16a36b; box-shadow: 0 0 0 5px rgba(22, 163, 107, .13); }
.verdict-mark.tone-danger { background: #d92d20; box-shadow: 0 0 0 5px rgba(217, 45, 32, .13); }
.verdict-mark.tone-warning { background: #d98b09; box-shadow: 0 0 0 5px rgba(217, 139, 9, .13); }
.verdict-mark.tone-info { background: #2563eb; box-shadow: 0 0 0 5px rgba(37, 99, 235, .13); }
.result-summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 14px 0; }
.result-summary-grid > div { display: grid; gap: 4px; padding: 12px 14px; border: 1px solid #e4eaf2; border-radius: 10px; background: #fff; }
.result-summary-grid span { color: #64748b; font-size: 12px; }
.result-summary-grid strong { color: #1e293b; font-size: 20px; line-height: 1; }
.text-success { color: #087443 !important; }
.text-danger { color: #b42318 !important; }
.text-warning { color: #a15c00 !important; }
.result-guidance-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 14px 0; }
.guidance-block { padding: 14px 16px; border: 1px solid #e4eaf2; border-radius: 12px; background: #fff; }
.attention-block { border-color: #f2cf91; background: #fffaf0; }
.review-block { border-color: #bcd3f8; background: #f6f9ff; }
.guidance-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.guidance-heading strong { color: #334155; font-size: 13px; }
.guidance-heading span { color: #64748b; font-size: 12px; }
.guidance-block ul, .check-issues { display: grid; gap: 5px; margin: 9px 0 0; padding-left: 18px; color: #475569; font-size: 12px; line-height: 1.55; }
.result-table { margin-top: 16px; }
.finding-line { display: flex; gap: 6px; align-items: baseline; line-height: 1.6; }
.finding-line small { color: #94a3b8; overflow-wrap: anywhere; }
.check-verdict { display: grid; gap: 4px; justify-items: start; }
.check-verdict small { color: #a15c00; font-size: 11px; }
.review-callout { display: flex; align-items: center; justify-content: space-between; gap: 18px; margin-top: 18px; padding: 15px 16px; border: 1px solid #bcd3f8; border-radius: 12px; background: #f6f9ff; }
.review-callout strong { color: #1e3a66; font-size: 13px; }
.review-callout p { margin: 4px 0 0; color: #5b6f8b; font-size: 12px; line-height: 1.5; }
.field-hint { margin: 7px 0 0; color: #a15c00; font-size: 12px; line-height: 1.5; }
.snapshot-collapse { margin-top: 18px; }
.snapshot-collapse pre { max-height: 420px; margin: 0; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font: 12px/1.7 ui-monospace, SFMono-Regular, Consolas, monospace; }
.review-form { margin-top: 16px; }
.task-scope-strip{display:grid;grid-template-columns:2fr 1fr 1fr;gap:16px;padding:18px 20px;background:#eef5ff;border-left:4px solid #2563eb;border-radius:8px}.task-scope-strip>div{display:grid;gap:5px}.task-scope-strip span{color:#64748b;font-size:12px}.task-scope-strip strong{color:#1e3a66;font-size:14px}.policy-summary{display:flex;gap:10px;flex-wrap:wrap}.policy-summary>span{padding:6px 10px;background:#edf4fc;border-radius:6px;color:#334155;font-size:12px}.policy-summary p{width:100%}.condition-readings p{margin:6px 0;color:#334155;font-size:13px}.execution-form{display:grid;gap:18px;margin-top:18px}
.report-review-list{display:grid;gap:12px;margin-top:18px}.report-review-item{display:grid;gap:6px;padding:12px;border:1px solid #dbe5f2;border-radius:10px}.report-review-item small{color:#64748b;overflow-wrap:anywhere}.report-review-item :deep(.el-checkbox){height:auto;white-space:normal}.report-review-item :deep(.el-checkbox__label){white-space:normal;line-height:1.6}
@media (max-width: 960px) { .form-grid.four { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 760px) { .execution-heading, .result-hero, .review-callout { flex-direction: column; align-items: stretch; } .form-grid.two, .form-grid.four, .requirement-list, .result-summary-grid, .result-guidance-grid,.task-scope-strip { grid-template-columns:1fr; } .section-title{flex-wrap:wrap}.section-title>div{flex:1;min-width:170px}.section-title>.el-button{margin-left:0}.execution-panel { padding:16px; } }
</style>
