<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useAuthStore } from "@/stores/auth.store";
import { standardAdmissionApi as api } from "@/api/standard-admission.api";
import { admissionLabel as label, metadataDifferences } from "@/utils/standard-admission";
import type { StandardCandidate, StandardRevision } from "@/types/standard-admission.types";

const props = withDefaults(defineProps<{documentId: string; initialRevisionId?: string; initialTab?:string; reviewMode?:boolean}>(), { initialRevisionId: "", initialTab:"metadata", reviewMode:false });
const emit = defineEmits<{changed: []}>();
const auth = useAuthStore();
const versions = ref<StandardRevision[]>([]);
const selected = ref("");
const revision = ref<StandardRevision | null>(null);
const tab = ref(props.initialTab);
const busy = ref(false);
const error = ref("");
const fileUrl = ref("");
const canSubmit = computed(() => auth.hasPermission("standard_admission_submit"));
const canReview = computed(() => auth.primaryRole === "expert" && auth.hasPermission("standard_admission_review") && revision.value?.created_by !== auth.userId &&
  (!revision.value?.review_assignment?.reviewer_id || revision.value.review_assignment.reviewer_id===auth.userId));
const canPublish = computed(() => auth.hasPermission("standard_admission_publish"));
const canEditCandidates = computed(() => canSubmit.value && (auth.primaryRole==="admin" || !revision.value?.review_assignment?.reviewer_id ||
  revision.value.review_assignment.reviewer_id===auth.userId || revision.value.created_by===auth.userId));
const metadata = reactive<Record<string, any>>({});
const formKeys = ["standard_no","standard_name","domain","product_category","standard_level","standard_status","resource_type","source_url","publisher","effective_from","effective_to","production_from","production_to","scope_notes"];
const metaLabels: Record<string,string> = {standard_no:"标准编号",standard_name:"标准名称",domain:"领域",product_category:"适用产品类别",standard_level:"标准类型",standard_status:"标准效力",resource_type:"资料类型",source_url:"来源地址",publisher:"发布机构",effective_from:"实施日期",effective_to:"效力截止",production_from:"适用生产日期开始",production_to:"适用生产日期截止",scope_notes:"适用对象、范围与过渡说明"};
function useHeaderClues() { for (const [key,item] of Object.entries(revision.value?.metadata_candidates || {})) if (formKeys.includes(key)) metadata[key]=item.value; }
const diff = computed(() => {
  const index = versions.value.findIndex(v => v.id === selected.value);
  if (index < 0 || !versions.value[index + 1] || !revision.value) return [];
  return metadataDifferences(versions.value[index+1].snapshot,revision.value.snapshot);
});
const actionOpen = ref(false);
const action = ref("review");
const decision = ref("approve");
const reason = ref("");
const evidence = ref("");
const conflictResolution = ref("");
const candidateOpen = ref(false);
const candidateReviewOpen = ref(false);
const reviewingCandidate = ref<StandardCandidate|null>(null);
const candidateDecision = ref<"confirm"|"needs_information"|"reject">("confirm");
const originalPage = ref(1);
const originalSource = computed(() => fileUrl.value ? `${fileUrl.value}#page=${originalPage.value}` : "");
const canReviewCandidate = (item:StandardCandidate) => canReview.value && item.prepared_by!==auth.userId;
const contextForm = reactive({product_category:"",production_date:null as string|null,conditions:""});
const applicabilityResult = ref<Awaited<ReturnType<typeof api.applicability>>['data']['data']|null>(null);
async function checkApplicability() { await run(async () => { applicabilityResult.value=(await api.applicability(props.documentId,selected.value,contextForm)).data.data; }); }
const editing = ref<StandardCandidate|null>(null);
const candidateType=ref('unclassified');
const candidateForm = reactive<Record<string,string>>({});
const executionFields=reactive({execution_mode:'manual',numeric_lower:null as number|null,numeric_upper:null as number|null,numeric_target:null as number|null,
  decision_mode:'direct',numeric_aggregation:'all',minimum_observations:1});
const expectedConditions=ref('{}');
const candidateKeys = ["indicator","method","conditions","unit","requirement","measurement_key","applicability"];
const candidateLabels: Record<string,string> = {indicator:"检测指标 / 项目",method:"检测方法及条款",conditions:"试验条件与规格分支",unit:"单位（无单位请写无量纲）",requirement:"限值或明确文字要求",measurement_key:"对应测量字段",applicability:"适用产品 / 场景"};
function executionEvidenceLabel(item: StandardCandidate) {
  if (item.execution_mode === "numeric") return "实测记录 / 检测报告转录";
  if (item.candidate_type === "method_condition") return "方法条件人工核对";
  if (item.execution_mode === "manual") return "人工核对";
  return "待补充执行方式";
}
function executionEvidenceHint(item: StandardCandidate) {
  if (item.execution_mode === "numeric") return "该项目包含明确数值或范围，图片不能替代计量结果；任务执行时必须引用实测记录或报告页码。";
  if (item.candidate_type === "method_condition") return "这是试验方法或条件核对项，不是可直接从图片判断的外观缺陷。";
  return "执行时需要根据条款保留人工核对说明和来源依据。";
}
let interval: ReturnType<typeof setInterval> | undefined;

function resetFile() { if (fileUrl.value) URL.revokeObjectURL(fileUrl.value); fileUrl.value = ""; }
async function loadVersions(keep = false) {
  const result = await api.revisions(props.documentId);
  versions.value = result.data.data;
  if (!keep || !versions.value.some(v => v.id === selected.value)) {
    selected.value = props.initialRevisionId && versions.value.some(v => v.id === props.initialRevisionId)
      ? props.initialRevisionId
      : versions.value[0]?.id || "";
  }
  await loadDetail();
}
async function loadDetail() {
  if (!selected.value) { revision.value = null; return; }
  const result = await api.detail(props.documentId,selected.value);
  revision.value = result.data.data;
  for (const key of formKeys) metadata[key] = revision.value.snapshot[key] ?? (key.endsWith("_from") || key.endsWith("_to") ? null : "");
  metadata.resource_type ||= "unverified";
}
async function run(work: () => Promise<void>) {
  busy.value = true; error.value = "";
  try { await work(); } catch (e: any) { error.value = e?.response?.data?.error?.message || e?.response?.data?.message || "操作未完成，请核对状态后重试"; }
  finally { busy.value = false; }
}
async function amend() {
  if (!revision.value) return;
  await run(async () => {
    const payload = Object.fromEntries(formKeys.map(k => [k,metadata[k]]));
    const result = await api.amend(props.documentId,{...payload,expected_version:revision.value!.row_version,base_revision_id:revision.value!.id});
    selected.value = result.data.data.id;
    await loadVersions(true); resetFile(); emit("changed"); ElMessage.success("已保存新修订，待独立核对");
  });
}
async function viewOriginal() {
  await run(async () => {
    resetFile();
    const result = await api.file(props.documentId,selected.value);
    fileUrl.value = URL.createObjectURL(result.data as unknown as Blob);
  });
}
function openAction(value: string) { action.value=value;reason.value="";evidence.value="";conflictResolution.value="";decision.value="approve";actionOpen.value=true; }
function actionPayload() { return {expected_version:revision.value!.row_version,request_key:crypto.randomUUID(),reason:reason.value.trim(),evidence_refs:evidence.value.split("\n").map(x=>x.trim()).filter(Boolean)}; }
async function submitAction() {
  if (!reason.value.trim() || !revision.value) return;
  await run(async () => {
    if (action.value === "review") await api.review(props.documentId,selected.value,{...actionPayload(),decision:decision.value,conflict_resolution:conflictResolution.value});
    else await api.action(props.documentId,selected.value,action.value as "publish"|"withdraw"|"retry",actionPayload());
    actionOpen.value=false; await loadVersions(true); emit("changed"); ElMessage.success("操作已记录");
  });
}
function editCandidate(item: StandardCandidate, duplicate=false) {
  candidateType.value=item.candidate_type||'unclassified';
  editing.value={...item,id:duplicate?`new:${item.id}`:item.id};
  for (const key of candidateKeys) candidateForm[key]=String((item as any)[key] || (key === "requirement" ? item.source_text : ""));
  candidateForm.operator=item.operator;candidateForm.status="pending";reason.value="";evidence.value="";candidateOpen.value=true;
  Object.assign(executionFields,{execution_mode:item.execution_mode||'manual',numeric_lower:item.numeric_lower??null,numeric_upper:item.numeric_upper??null,
    numeric_target:item.numeric_target??null,decision_mode:item.decision_mode||'direct',numeric_aggregation:item.numeric_aggregation||'all',minimum_observations:item.minimum_observations||1});
  expectedConditions.value=JSON.stringify(item.expected_conditions||{},null,2);
}
async function saveCandidate() {
  if (!editing.value || !revision.value || !reason.value.trim()) return;
  await run(async () => {
    await api.candidate(props.documentId,selected.value,{...actionPayload(),candidate_id:editing.value!.id,...candidateForm,candidate_type:candidateType.value,status:"pending",...executionFields,
      expected_conditions:JSON.parse(expectedConditions.value)} as any);
    candidateOpen.value=false;await loadVersions(true);emit("changed");ElMessage.success("检测要求已记录");
  });
}
async function openCandidateReview(item:StandardCandidate) {
  reviewingCandidate.value=item;candidateDecision.value="confirm";reason.value="";evidence.value="";
  originalPage.value=item.page_number;candidateReviewOpen.value=true;
  if(props.reviewMode&&!fileUrl.value) await viewOriginal();
}
async function reviewCandidate() {
  if(!reviewingCandidate.value||!revision.value||!reason.value.trim())return;
  await run(async()=>{
    await api.candidateReview(props.documentId,selected.value,{...actionPayload(),candidate_id:reviewingCandidate.value!.id,decision:candidateDecision.value});
    candidateReviewOpen.value=false;await loadVersions(true);emit("changed");ElMessage.success("逐项专业核对已记录");
  });
}
async function submitWorkflowAction() {
  if(action.value!=="release"&&action.value!=="draft") {await submitAction();return;}
  await run(async()=>{
    if(action.value==="release") await api.assignment(props.documentId,selected.value,{...actionPayload(),operation:"release"});
    else {const result=await api.requirementsDraft(props.documentId,selected.value,actionPayload());selected.value=result.data.data.id;}
    actionOpen.value=false;await loadVersions(true);emit("changed");
  });
}
watch(() => props.documentId, async () => { selected.value="";revision.value=null;resetFile();await run(() => loadVersions()); },{immediate:true});
watch(selected, () => { resetFile();applicabilityResult.value=null; });
interval=setInterval(() => {
  if (!busy.value && !actionOpen.value && !candidateOpen.value && revision.value &&
    (revision.value.processing_status==="pending" || revision.value.publication_status==="publishing")) void run(() => loadVersions(true));
},10000);
onBeforeUnmount(() => { clearInterval(interval);resetFile(); });
</script>

<template>
  <div class="standard-detail" v-loading="busy">
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
    <template v-if="revision">
      <header class="document-heading">
        <div><p class="eyebrow">标准核对工作区</p><h2>{{ revision.snapshot.standard_no }}</h2><p>{{ revision.snapshot.standard_name }}</p></div>
        <el-select v-model="selected" aria-label="选择标准修订" @change="run(loadDetail)">
          <el-option v-for="v in versions" :key="v.id" :value="v.id" :label="`修订 ${v.revision_no} · ${label(v.publication_status)}`" />
        </el-select>
      </header>
      <div class="admission-stages">
        <div><span>01 处理</span><strong>{{ label(revision.processing_status) }}</strong></div>
        <div><span>02 原文准入核验</span><strong>{{ label(revision.review_status) }}</strong></div>
        <div><span>03 发布使用</span><strong>{{ label(revision.publication_status) }}</strong></div>
      </div>
      <el-alert v-if="revision.publication_status !== 'published'" type="warning" :closable="false" :title="revision.review_status==='approved'?'原文准入核验已完成；正式使用仍须发布，并仅启用逐项已确认的要求。':'本修订尚不可作为正式判定依据；解析成功后仍需专业核验与发布。'" />
      <el-alert v-if="revision.created_by===auth.userId" type="info" :closable="false" title="此修订由本人提交，专业核验须交给另一位授权专家。"/>
      <el-alert v-if="revision.snapshot.metadata_review_basis_revision_id" type="info" :closable="false" title="本稿沿用已发布原文的来源核验；新增或修改要求须另行独立确认，原发布版继续有效。"/>
      <el-alert v-if="revision.snapshot.conflicts?.length" type="warning" :closable="false" title="存在相同编号、不同内容的资料，请核对来源及修订差异，避免重复发布。" />
      <div class="action-row">
        <el-button @click="run(() => loadVersions(true))">刷新状态</el-button>
        <el-button v-if="canReview && revision.publication_status === 'unpublished'" type="primary" @click="openAction('review')">专业核验</el-button>
        <el-button v-if="revision.review_assignment?.reviewer_id===auth.userId && revision.publication_status==='unpublished'" @click="openAction('release')">退回重新分派</el-button>
        <el-button v-if="canSubmit && revision.publication_status==='published' && versions[0]?.id===revision.id" @click="openAction('draft')">建立检测要求新稿</el-button>
        <el-button v-if="canPublish && revision.review_status === 'approved' && revision.publication_status === 'unpublished'" type="primary" @click="openAction('publish')">发布标准</el-button>
        <el-button v-if="canPublish && ['published','publishing','suspended'].includes(revision.publication_status)" type="danger" plain @click="openAction('withdraw')">撤回本修订</el-button>
        <el-button v-if="canSubmit && (revision.processing_status !== 'parsed' || revision.jobs?.some(j=>j.status==='failed'))" @click="openAction('retry')">重新处理</el-button>
      </div>
      <div :class="{'review-layout':reviewMode}">
      <aside v-if="reviewMode" class="review-original"><div class="action-row"><strong>原文对照</strong><el-button :loading="busy" @click="viewOriginal">打开原PDF核对</el-button><a v-if="originalSource" :href="originalSource" target="_blank" rel="noopener noreferrer">新窗口查看</a></div><iframe v-if="originalSource" :src="originalSource" title="标准审核原PDF" class="pdf-frame"/><el-empty v-else description="打开原PDF，与右侧提取内容逐项核对"/></aside>
      <el-tabs v-model="tab" class="review-content">
        <el-tab-pane label="基本信息与适用范围" name="metadata">
          <el-collapse v-if="Object.keys(revision.metadata_candidates || {}).length" class="header-clues"><el-collapse-item title="自动识别的正文元信息候选（须对照原PDF核对）"><div v-for="(item,key) in revision.metadata_candidates" :key="key"><strong>{{ metaLabels[key] }}：</strong>{{ item.value }} <span class="muted">· PDF第 {{ item.page_number }} 页</span></div><el-button v-if="canSubmit" class="clue-button" @click="useHeaderClues">填入候选后核对</el-button><p class="muted">编号出现在正文中也可能只是引用其他标准；这些候选不代表来源、类型或现行状态已确认。</p></el-collapse-item></el-collapse>
          <el-form label-position="top" class="metadata-grid" :disabled="!canSubmit">
            <el-form-item v-for="key in formKeys" :key="key" :label="metaLabels[key]" :class="{'wide-field':key==='scope_notes'||key==='source_url'||key==='standard_name'}">
              <el-select v-if="key==='resource_type'" v-model="metadata[key]"><el-option label="待核实类型" value="unverified"/><el-option label="标准正文" value="standard"/><el-option label="参考资料（不作为检测标准）" value="reference"/></el-select>
              <el-select v-else-if="key==='standard_status'" v-model="metadata[key]"><el-option v-for="status in ['待核实','现行','即将实施','被代替','废止']" :key="status" :label="status" :value="status"/></el-select>
              <el-date-picker v-else-if="key.endsWith('_from')||key.endsWith('_to')" v-model="metadata[key]" type="date" value-format="YYYY-MM-DD" />
              <el-input v-else v-model="metadata[key]" :type="key==='scope_notes'?'textarea':'text'" :rows="3"/>
            </el-form-item>
          </el-form>
          <el-button v-if="canSubmit" type="primary" @click="amend">保存为新修订</el-button>
          <p class="muted">正文、来源和适用范围随修订保留。新稿核对期间，已有发布版仍可按原范围使用。</p>
          <el-alert v-for="issue in revision.issues" :key="issue" :title="issue" type="info" :closable="false" class="issue"/>
        </el-tab-pane>
        <el-tab-pane label="原文与条款" name="original">
          <div class="action-row"><el-button @click="viewOriginal">打开原PDF核对</el-button><span class="muted">共 {{ revision.page_count }} 页；数字和表格请以原文核对结果为准。</span></div>
          <iframe v-if="fileUrl && !reviewMode" :src="fileUrl" title="标准原PDF" class="pdf-frame" />
          <el-collapse><el-collapse-item v-for="page in revision.pages" :key="page.page_number" :title="`PDF第 ${page.page_number} 页 · 解析文本`" :name="page.page_number"><pre>{{ page.text }}</pre></el-collapse-item></el-collapse>
          <el-empty v-if="!revision.pages?.length" description="等待解析正文，可先查看原PDF或检查处理状态"/>
        </el-tab-pane>
        <el-tab-pane :label="`候选条款与检测要求（${revision.candidate_count}）`" name="requirements">
          <div class="requirements-summary"><strong>{{ revision.confirmed_count }} 项已确认</strong><span>{{ label(revision.extraction_status) }}</span></div>
          <p class="muted">自动解析结果全部是候选。检测要求、方法条件和正文条款分别保留；只有专家确认并完成发布后，才进入正式检测要求总览。</p>
          <article v-for="item in revision.candidates" :key="item.id" class="requirement-card">
            <header><strong>{{ item.clause_no || '待核对条款号' }} · {{ item.indicator || '待识别检测项目' }}</strong><span><el-tag effect="plain">{{ item.candidate_type === 'method_condition' ? '方法条件' : item.candidate_type === 'body_clause' ? '正文条款' : '检测要求候选' }}</el-tag> <el-tag :type="item.status==='confirmed'?'success':'info'">{{ item.status==='pending'?'待专业核对':label(item.status) }}</el-tag></span></header>
            <p class="source-ref">PDF第 {{ item.page_number }} 页 · 识别置信度 {{ item.extraction_confidence ?? '待评估' }}</p><pre>{{ item.source_text }}</pre>
            <dl class="evidence-compare"><dt>原始 OCR</dt><dd>{{ item.ocr_text || item.source_text }}</dd><dt>规范化文本</dt><dd>{{ item.normalized_text || '未生成；请以原 PDF 为准' }}</dd></dl>
            <el-alert v-if="item.normalization_notes" :title="item.normalization_notes" type="warning" :closable="false" />
             <dl v-if="item.requirement"><dt>核对要求</dt><dd>{{ item.requirement }}</dd><dt>方法 / 条件</dt><dd>{{ item.method }} / {{ item.conditions }}</dd><dt>测量字段 / 单位</dt><dd>{{ item.measurement_key }} / {{ item.unit }}</dd><dt>执行证据</dt><dd><el-tag size="small" effect="plain">{{ executionEvidenceLabel(item) }}</el-tag><span class="evidence-hint">{{ executionEvidenceHint(item) }}</span></dd></dl>
            <p v-if="item.review_reason" class="muted">核对意见：{{item.review_reason}} · {{item.review_evidence_refs?.join('；')}}</p>
            <footer><div><span class="muted">{{ item.warning }}</span><p v-if="item.prepared_by===auth.userId" class="muted">本人整理，须交其他专家确认</p></div><div v-if="revision.publication_status==='unpublished'"><el-button v-if="canEditCandidates" @click="editCandidate(item)">编辑整理稿</el-button><el-button v-if="canEditCandidates" link @click="editCandidate(item,true)">同条款新增项目</el-button><el-button v-if="canReviewCandidate(item)&&item.status!=='confirmed'" type="primary" @click="openCandidateReview(item)">逐项专业核对</el-button></div></footer>
          </article>
          <el-empty v-if="!revision.candidates?.length" description="尚无候选；可查看原文及解析状态，不能据此认定标准没有检测要求"/>
        </el-tab-pane>
        <el-tab-pane label="修订与引用影响" name="history">
          <el-alert title="发布新版后，后续检索使用新修订；已有任务不会被静默重算。任务与规则的完整引用关联将在执行阶段接入。" type="info" :closable="false"/>
          <h3>与上一修订的元信息差异</h3>
          <el-table :data="diff"><el-table-column prop="key" label="字段"/><el-table-column label="之前"><template #default="{row}">{{ row.before ?? '—' }}</template></el-table-column><el-table-column label="本修订"><template #default="{row}">{{ row.after ?? '—' }}</template></el-table-column></el-table>
          <h3>核对与操作记录</h3>
          <el-table :data="revision.reviews"><el-table-column prop="created_at" label="时间" width="190"/><el-table-column prop="action" label="操作" width="100"/><el-table-column prop="reason" label="说明"/><el-table-column label="依据"><template #default="{row}">{{ row.evidence_refs.join('；') }}</template></el-table-column></el-table>
          <h3>处理记录</h3>
          <el-table :data="revision.jobs"><el-table-column prop="action" label="处理项"/><el-table-column label="状态"><template #default="{row}">{{ label(row.status) }}</template></el-table-column><el-table-column prop="attempts" label="尝试次数"/><el-table-column prop="error_message" label="问题"/></el-table>
        </el-tab-pane>
        <el-tab-pane label="适用核对" name="applicability">
          <p class="muted">按当前选择的具体修订核对生产日期和产品范围。历史产品可以核对历史标准；不自动套用最新版本。</p>
          <el-form label-position="top" class="metadata-grid"><el-form-item label="产品类别"><el-input v-model="contextForm.product_category" :placeholder="revision.snapshot.product_category || '填写产品类别'"/></el-form-item><el-form-item label="产品生产日期"><el-date-picker v-model="contextForm.production_date" type="date" value-format="YYYY-MM-DD"/></el-form-item><el-form-item label="型号、场景与试验条件" class="wide-field"><el-input v-model="contextForm.conditions" type="textarea" :rows="3"/></el-form-item></el-form>
          <el-button type="primary" @click="checkApplicability">核对当前修订适用范围</el-button>
          <div v-if="applicabilityResult" class="applicability-result"><el-alert :title="applicabilityResult.status==='scope_match'?'登记的日期与类别范围匹配，仍需核对具体方法和试验条件':applicabilityResult.status==='mismatch'?'与登记适用范围不匹配':'需要补充或核对信息'" :type="applicabilityResult.status==='scope_match'?'success':'warning'" :closable="false"/><p v-for="item in [...applicabilityResult.missing_fields,...applicabilityResult.mismatches]" :key="item">{{ item }}</p><p>{{ applicabilityResult.scope_notes }}</p><p class="muted">{{ applicabilityResult.notice }}</p></div>
        </el-tab-pane>
      </el-tabs>
      </div>
    </template>
    <el-empty v-else-if="!busy && !error" description="尚无可显示修订"/>
    <el-dialog v-model="actionOpen" :title="action==='review'?'专业核验':action==='publish'?'发布标准':action==='withdraw'?'撤回修订':action==='draft'?'建立检测要求新稿':action==='release'?'退回重新分派':'重新处理'" width="620px" append-to-body>
      <el-alert v-if="action==='publish'" type="info" :closable="false" title="发布启用已核验原文及已确认检测要求。尚未确认的候选只保留为待核对内容，不进入任务判定。"/>
      <el-form label-position="top"><el-form-item v-if="action==='review'" label="核验决定"><el-select v-model="decision"><el-option label="来源、类型、版本及适用范围已核对" value="approve"/><el-option label="需补充资料" value="needs_information"/><el-option label="存在冲突 / 分歧" value="dispute"/><el-option label="退回" value="reject"/></el-select></el-form-item>
      <el-form-item label="核对说明 / 操作原因" required><el-input v-model="reason" type="textarea" :rows="3"/></el-form-item><el-form-item label="核对依据（每行一条，批准时必填）"><el-input v-model="evidence" type="textarea" :rows="3" placeholder="来源页面、原PDF页码、发布信息或核验记录"/></el-form-item><el-form-item v-if="action==='review' && revision?.snapshot.conflicts?.length" label="同编号正文冲突的核对与处理依据" required><el-input v-model="conflictResolution" type="textarea" :rows="3"/></el-form-item></el-form>
      <template #footer><el-button @click="actionOpen=false">取消</el-button><el-button type="primary" :disabled="!reason.trim()" :loading="busy" @click="submitWorkflowAction">确认并记录</el-button></template>
    </el-dialog>
    <el-dialog v-model="candidateOpen" title="核对检测项目与要求" width="820px" append-to-body>
      <template v-if="editing"><div class="candidate-original"><strong>{{ editing.clause_no }} · PDF第 {{ editing.page_number }} 页</strong><pre>{{ editing.source_text }}</pre></div>
        <el-form label-position="top" class="metadata-grid"><el-form-item label="条款用途" required class="wide-field"><el-select v-model="candidateType"><el-option label="待专业分类" value="unclassified"/><el-option label="产品检测要求" value="inspection_requirement"/><el-option label="试验方法或条件" value="method_condition"/><el-option label="参考正文（不进入检测执行）" value="body_clause"/></el-select></el-form-item><el-form-item v-for="key in candidateKeys" :key="key" :label="candidateLabels[key]" :class="{'wide-field':['conditions','requirement','method','applicability'].includes(key)}"><el-input v-model="candidateForm[key]" :type="['conditions','requirement','method','applicability'].includes(key)?'textarea':'text'" :rows="2"/></el-form-item>
        <el-form-item label="要求关系"><el-select v-model="candidateForm.operator"><el-option v-for="op in [{v:'unresolved',l:'待核对'},{v:'le',l:'不得高于'},{v:'ge',l:'不得低于'},{v:'range',l:'范围'},{v:'eq',l:'等于'},{v:'text',l:'文字核对要求'}]" :key="op.v" :value="op.v" :label="op.l"/></el-select></el-form-item>
        <el-form-item label="整理状态"><el-tag>保存为待独立核对稿</el-tag><p class="muted">保存人不能确认自己的技术整理；未修改的候选可直接交专业核对。</p></el-form-item>
        <el-form-item label="执行方式"><el-select v-model="executionFields.execution_mode"><el-option label="人工核对要求" value="manual"/><el-option label="明确数值比较" value="numeric"/></el-select></el-form-item>
        <template v-if="executionFields.execution_mode==='numeric'"><el-form-item label="已核对下限"><el-input-number v-model="executionFields.numeric_lower"/></el-form-item><el-form-item label="已核对上限"><el-input-number v-model="executionFields.numeric_upper"/></el-form-item><el-form-item v-if="candidateForm.operator==='eq'" label="目标值"><el-input-number v-model="executionFields.numeric_target"/></el-form-item><el-form-item label="判定方式"><el-select v-model="executionFields.decision_mode"><el-option label="数值直接比较（须与条款一致）" value="direct"/><el-option label="观测区间与限值比较" value="interval"/></el-select></el-form-item><el-form-item label="重复观测处理"><el-select v-model="executionFields.numeric_aggregation"><el-option label="逐次核对，全部符合" value="all"/><el-option label="条款明确要求的均值" value="mean"/></el-select></el-form-item><el-form-item label="最少有效观测次数"><el-input-number v-model="executionFields.minimum_observations" :min="1"/></el-form-item><el-form-item label="试验条件与规格字段（JSON）" class="wide-field"><el-input v-model="expectedConditions" type="textarea" :rows="4" placeholder='例如：{"dry":true,"test_speed_kmh":25}'/></el-form-item></template>
        <el-form-item label="核对说明" required class="wide-field"><el-input v-model="reason" type="textarea"/></el-form-item><el-form-item label="依据（每行一条，确认时必填）" class="wide-field"><el-input v-model="evidence" type="textarea"/></el-form-item></el-form>
      </template>
      <template #footer><el-button @click="candidateOpen=false">取消</el-button><el-button type="primary" :disabled="!reason.trim()" :loading="busy" @click="saveCandidate">保存整理稿</el-button></template>
    </el-dialog>
    <el-dialog v-model="candidateReviewOpen" title="逐项专业核对" width="min(900px, 94vw)" append-to-body :close-on-click-modal="false">
      <el-alert v-if="error" :title="error" type="error" :closable="false"/>
      <template v-if="reviewingCandidate"><div class="candidate-original"><strong>{{reviewingCandidate.clause_no}} · PDF第 {{reviewingCandidate.page_number}} 页</strong><pre>{{reviewingCandidate.source_text}}</pre></div><el-descriptions :column="2" border><el-descriptions-item label="指标">{{reviewingCandidate.indicator||'未整理'}}</el-descriptions-item><el-descriptions-item label="方法">{{reviewingCandidate.method||'未整理'}}</el-descriptions-item><el-descriptions-item label="条件">{{reviewingCandidate.conditions||'未整理'}}</el-descriptions-item><el-descriptions-item label="单位">{{reviewingCandidate.unit||'未整理'}}</el-descriptions-item><el-descriptions-item label="要求">{{reviewingCandidate.requirement||'未整理'}}</el-descriptions-item><el-descriptions-item label="适用对象">{{reviewingCandidate.applicability||'未整理'}}</el-descriptions-item><el-descriptions-item label="测量字段">{{reviewingCandidate.measurement_key||'未整理'}}</el-descriptions-item><el-descriptions-item label="执行方式">{{executionEvidenceLabel(reviewingCandidate)}}</el-descriptions-item><el-descriptions-item v-if="reviewingCandidate.execution_mode==='numeric'" label="数值关系" :span="2">{{reviewingCandidate.operator}} · 下限 {{reviewingCandidate.numeric_lower??'—'}} / 上限 {{reviewingCandidate.numeric_upper??'—'}} / 目标 {{reviewingCandidate.numeric_target??'—'}}</el-descriptions-item></el-descriptions>
      <el-descriptions v-if="reviewingCandidate.execution_mode==='numeric'" :column="2" border class="issue"><el-descriptions-item label="判定方式">{{reviewingCandidate.decision_mode==='interval'?'观测区间比较':'数值直接比较'}}</el-descriptions-item><el-descriptions-item label="次数与聚合">至少 {{reviewingCandidate.minimum_observations||1}} 次 · {{reviewingCandidate.numeric_aggregation==='mean'?'按条款取均值':'逐次全部符合'}}</el-descriptions-item><el-descriptions-item label="必须匹配的试验条件" :span="2"><pre>{{JSON.stringify(reviewingCandidate.expected_conditions||{},null,2)}}</pre></el-descriptions-item></el-descriptions>
      <el-alert class="issue" type="info" :closable="false" title="此处确认已有内容。需要改动指标、限值或条件时先保存整理稿，再交其他专家确认。"/>
      <el-form label-position="top"><el-form-item label="逐项决定"><el-select v-model="candidateDecision"><el-option label="与原文一致，确认要求" value="confirm"/><el-option label="缺少信息，退回补充" value="needs_information"/><el-option label="不作为检测要求，排除并说明" value="reject"/></el-select></el-form-item><el-form-item label="专业核对意见" required><el-input v-model="reason" type="textarea" :rows="3"/></el-form-item><el-form-item label="核对依据（每行一条）" :required="candidateDecision!=='needs_information'"><el-input v-model="evidence" type="textarea" :rows="3" placeholder="原PDF页码、条款号及核对记录"/></el-form-item></el-form></template>
      <template #footer><el-button @click="candidateReviewOpen=false">取消</el-button><el-button type="primary" :loading="busy" :disabled="!reason.trim()||(candidateDecision!=='needs_information'&&!evidence.trim())" @click="reviewCandidate">记录逐项决定</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.review-layout{display:grid;grid-template-columns:minmax(340px,.85fr) minmax(0,1fr);gap:20px;align-items:start}.review-original{position:sticky;top:0;border:1px solid var(--el-border-color);border-radius:6px;padding:12px;min-width:0}.review-original .pdf-frame{width:100%;height:690px}.review-content{min-width:0}.review-layout .metadata-grid{grid-template-columns:1fr}.review-layout .requirement-card{padding:14px}.review-layout .requirement-card footer{flex-direction:column}@media(max-width:1000px){.review-layout{grid-template-columns:1fr}.review-original{position:static}.review-original .pdf-frame{height:460px}}
.standard-detail{display:flex;flex-direction:column;gap:16px;color:var(--el-text-color-primary)}
.document-heading{display:flex;justify-content:space-between;align-items:start;gap:24px;padding:0 0 18px;border-bottom:2px solid var(--el-color-primary)}
.document-heading h2{margin:4px 0;font-size:25px;font-variant-numeric:tabular-nums}.document-heading p{margin:6px 0}.document-heading .el-select{width:210px;flex-shrink:0}
.eyebrow{font-size:12px;letter-spacing:2px;color:var(--el-color-primary)}
.admission-stages{display:grid;grid-template-columns:repeat(3,1fr);border:1px solid var(--el-border-color);border-radius:6px}
.admission-stages>div{padding:14px 18px;border-right:1px solid var(--el-border-color);display:flex;flex-direction:column;gap:8px}.admission-stages>div:last-child{border:0}.admission-stages span{color:var(--el-text-color-secondary);font-size:12px}
.action-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.metadata-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 20px}.wide-field{grid-column:1/-1}.metadata-grid .el-select,.metadata-grid :deep(.el-date-editor){width:100%}
.muted{color:var(--el-text-color-secondary);font-size:13px;line-height:1.7}.issue{margin-top:8px}.pdf-frame{width:100%;height:580px;border:1px solid var(--el-border-color);margin:16px 0}
.applicability-result{margin-top:18px}
pre{font:13px/1.8 'Microsoft YaHei',sans-serif;white-space:pre-wrap;overflow-wrap:anywhere;margin:12px 0;max-height:300px;overflow:auto}
.requirements-summary{display:flex;gap:20px;align-items:center;margin:6px 0}.requirements-summary strong{color:var(--el-color-primary)}
.requirement-card{margin:16px 0;padding:20px;border:1px solid var(--el-border-color);border-left:3px solid var(--el-color-primary);border-radius:6px}
.evidence-compare{display:grid;grid-template-columns:120px 1fr;gap:7px 12px;padding:12px;background:var(--el-fill-color-light);border-radius:5px;font-size:13px}.evidence-compare dt{color:var(--el-text-color-secondary)}.evidence-compare dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}
.requirement-card header,.requirement-card footer{display:flex;justify-content:space-between;gap:16px;align-items:start}.source-ref{font-size:12px;color:var(--el-text-color-secondary)}.requirement-card dl{display:grid;grid-template-columns:130px 1fr;gap:8px;font-size:13px}.requirement-card dd{margin:0}.requirement-card footer{padding-top:12px;border-top:1px solid var(--el-border-color-lighter)}.candidate-original{padding:12px 16px;background:var(--el-fill-color-light);border-radius:6px;margin-bottom:18px}
@media(max-width:700px){.metadata-grid{grid-template-columns:1fr}.document-heading{flex-direction:column}.requirement-card footer{flex-direction:column}.admission-stages>div{padding:10px}}
</style>
