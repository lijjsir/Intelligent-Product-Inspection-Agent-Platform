<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {useRoute} from 'vue-router';
import { ElMessage } from "element-plus";
import { useAuthStore } from "@/stores/auth.store";
import { standardAdmissionApi as api } from "@/api/standard-admission.api";
import { extractApiErrorMessage } from "@/api/http";
import { admissionLabel } from "@/utils/standard-admission";
import type { StandardReviewRow, StandardReviewQueue } from "@/types/standard-admission.types";
import StandardDocumentDetail from "./StandardDocumentDetail.vue";

const auth = useAuthStore();
const route=useRoute();
const admin = computed(() => auth.primaryRole === "admin");
const canAssign = computed(() => auth.hasPermission("standard_review_assign"));
const data = ref<StandardReviewQueue>({items:[],total:0,page:1,size:30,domains:[],totals:{pending:0,mine:0,unassigned:0,awaiting_publish:0}});
const scope = ref("pending"), keyword = ref(""), domain = ref("");
const page = ref(1), loading = ref(false), busy = ref(false), error = ref("");
const selected = ref<StandardReviewRow|null>(null), detailOpen = ref(false), assignOpen = ref(false);
const reviewers = ref<{id:string;name:string}[]>([]), reviewer = ref(""), due = ref<Date|null>(null), reason = ref("");
const labels:Record<string,string>={pending:"待核对",mine:"我的待审",unassigned:"待领取",authored:"本人提交",awaiting_publish:"待发布",all:"全部记录"};
const scopes = computed(() => admin.value ? ["pending","awaiting_publish","all"] : ["pending","mine","unassigned","authored","all"]);
const actionLabels:Record<string,string>={pending:"待原文核验",needs_information:"需补资料",disputed:"存在分歧",rejected:"已退回",approved:"原文已核验"};
const overdue = (row:StandardReviewRow) => row.needs_work && !!row.review_assignment.due_at && new Date(row.review_assignment.due_at).getTime()<Date.now();
const deadline = (row:StandardReviewRow) => row.review_assignment.due_at ? new Date(row.review_assignment.due_at).toLocaleDateString("zh-CN") : "未设置";

async function load() {
  loading.value=true;error.value="";
  try { data.value=(await api.reviewQueue({scope:scope.value,keyword:keyword.value.trim(),domain:domain.value,page:page.value,size:30})).data.data; }
  catch(e) { error.value=extractApiErrorMessage(e,"审核清单未能加载，请重试"); }
  finally { loading.value=false; }
}
function filter() { page.value=1;void load(); }
function open(row:StandardReviewRow) { selected.value=row;detailOpen.value=true; }
async function claim(row:StandardReviewRow) {
  busy.value=true;error.value="";
  try {
    await api.assignment(row.document_id,row.revision_id,{expected_version:row.row_version,request_key:crypto.randomUUID(),
      operation:"claim",reason:"领取组织开放的标准专业核验任务",evidence_refs:[]});
    await load();open(data.value.items.find(x=>x.revision_id===row.revision_id)||row);
  } catch(e) { error.value=extractApiErrorMessage(e,"领取未完成，请刷新确认审核责任"); }
  finally { busy.value=false; }
}
async function assign(row:StandardReviewRow) {
  busy.value=true;error.value="";
  try { reviewers.value=(await api.reviewers()).data.data;selected.value=row;reviewer.value=row.review_assignment.reviewer_id||"";due.value=row.review_assignment.due_at?new Date(row.review_assignment.due_at):null;reason.value="";assignOpen.value=true; }
  catch(e) { error.value=extractApiErrorMessage(e,"审核人员未能加载"); }
  finally { busy.value=false; }
}
async function saveAssignment() {
  if(!selected.value||!reviewer.value||!reason.value.trim())return;
  busy.value=true;error.value="";
  try {
    await api.assignment(selected.value.document_id,selected.value.revision_id,{expected_version:selected.value.row_version,
      request_key:crypto.randomUUID(),operation:"assign",reviewer_id:reviewer.value,due_at:due.value?.toISOString()||null,
      reason:reason.value.trim(),evidence_refs:[]});
    assignOpen.value=false;await load();ElMessage.success("审核责任和期限已记录");
  } catch(e) { error.value=extractApiErrorMessage(e,"分派未完成，请刷新后重试"); }
  finally { busy.value=false; }
}
watch(()=>route.query,async()=>{
  if(route.query.document_id){scope.value='all';keyword.value=String(route.query.keyword||'');page.value=1;}
  await load();
  if(route.query.document_id){
    const row=data.value.items.find(item=>item.document_id===String(route.query.document_id)&&
      (!route.query.revision_id||item.revision_id===String(route.query.revision_id)));
    if(row)open(row);else error.value='本页未找到指定修订，请核对当前版本或清除筛选后查找。';
  }
},{immediate:true});
</script>

<template>
  <section class="review-workspace">
    <header class="review-header"><div><p class="eyebrow">标准管理 / 专业核验</p><h2>{{admin?'标准审核分派':'标准审核工作台'}}</h2><p class="muted">{{admin?'核对审核进度，按标准领域分派人员；专业确认后发布启用。':'领取或处理待审项，对照原文核对指标、方法、条件和适用范围。'}}</p></div><div class="header-actions"><router-link to="/governance/admin/inspection-standards"><el-button>浏览标准库</el-button></router-link><el-button @click="load">刷新</el-button></div></header>
    <div class="review-totals"><div><span>待核对文档</span><strong>{{data.totals.pending}}</strong></div><div><span>我的待审</span><strong>{{data.totals.mine}}</strong></div><div><span>待领取</span><strong>{{data.totals.unassigned}}</strong></div><div><span>原文核验后待发布</span><strong>{{data.totals.awaiting_publish}}</strong></div></div>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false"/>
    <div class="review-filters"><el-radio-group v-model="scope" @change="filter"><el-radio-button v-for="item in scopes" :key="item" :label="item">{{labels[item]}}</el-radio-button></el-radio-group><div><el-input v-model="keyword" placeholder="标准编号、名称或专题库" clearable @keyup.enter="filter" @clear="filter"/><el-select v-model="domain" placeholder="标准领域" clearable @change="filter"><el-option v-for="item in data.domains" :key="item" :label="item" :value="item"/></el-select><el-button @click="filter">查询</el-button></div></div>
    <el-table :data="data.items" v-loading="loading" row-key="revision_id" empty-text="当前范围没有待审记录，可切换到待领取或全部记录" class="review-table">
      <el-table-column label="标准与修订" min-width="250"><template #default="{row}"><strong>{{row.standard_no}}</strong><p class="table-sub">{{row.standard_name}}</p><span class="muted">{{row.library_name}} · 修订 {{row.revision_no}}</span></template></el-table-column>
      <el-table-column prop="domain" label="领域" min-width="120"/>
      <el-table-column label="原文核验" width="135"><template #default="{row}"><el-tag :type="row.review_status==='approved'?'success':'warning'">{{actionLabels[row.review_status]||admissionLabel(row.review_status)}}</el-tag><p class="table-sub muted">{{admissionLabel(row.processing_status)}}</p></template></el-table-column>
      <el-table-column label="逐项核对进度" min-width="180"><template #default="{row}"><strong>{{row.confirmed_count}}</strong> 已确认 / {{row.candidate_count}} 候选<p class="table-sub muted">待核对 {{row.pending_count}} · 已排除 {{row.excluded_count}}</p></template></el-table-column>
      <el-table-column label="审核责任与期限" min-width="175"><template #default="{row}"><span>{{row.review_assignment.reviewer_name||'待分派或领取'}}</span><p class="table-sub" :class="{'overdue':overdue(row),'muted':!overdue(row)}">{{overdue(row)?'已逾期 · ':''}}{{deadline(row)}}</p></template></el-table-column>
      <el-table-column label="操作" min-width="210" fixed="right"><template #default="{row}"><el-button v-if="row.can_claim" link type="primary" :loading="busy" @click="claim(row)">领取并审核</el-button><el-button link :type="row.can_review?'primary':'info'" @click="open(row)">{{row.can_review?'进入审核':admin&&row.review_status==='approved'&&row.publication_status==='unpublished'?'核对并发布':'查看详情'}}</el-button><el-button v-if="canAssign&&row.publication_status==='unpublished'" link type="primary" @click="assign(row)">分派</el-button><p v-if="row.is_author&&row.publication_status==='unpublished'" class="table-sub muted">本人提交，须交其他专家核验</p></template></el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" :page-size="30" :total="data.total" layout="total, prev, pager, next" @current-change="load"/>
    <el-dialog v-model="detailOpen" title="标准原文与逐项核对" width="min(1480px, 96vw)" top="3vh" :close-on-click-modal="false" destroy-on-close><StandardDocumentDetail v-if="selected&&detailOpen" :document-id="selected.document_id" :initial-revision-id="selected.revision_id" initial-tab="requirements" review-mode @changed="load"/></el-dialog>
    <el-dialog v-model="assignOpen" title="分派标准审核" width="560px" :close-on-click-modal="false"><el-alert v-if="error" :title="error" type="error" :closable="false"/><el-form label-position="top"><el-form-item label="标准领域">{{selected?.domain}}</el-form-item><el-form-item label="审核专家" required><el-select v-model="reviewer" placeholder="选择具有本领域核验能力的授权专家"><el-option v-for="item in reviewers" :key="item.id" :label="item.name" :value="item.id" :disabled="item.id===selected?.created_by"/></el-select></el-form-item><el-form-item label="审核期限（可选）"><el-date-picker v-model="due" type="datetime"/></el-form-item><el-form-item label="分派依据与说明" required><el-input v-model="reason" type="textarea" :rows="3" placeholder="说明专家与本标准领域的匹配及本次审核范围"/></el-form-item></el-form><template #footer><el-button @click="assignOpen=false">取消</el-button><el-button type="primary" :loading="busy" :disabled="!reviewer||!reason.trim()" @click="saveAssignment">记录并分派</el-button></template></el-dialog>
  </section>
</template>

<style scoped>
.review-workspace{display:flex;flex-direction:column;gap:18px}.review-header{display:flex;align-items:center;justify-content:space-between;gap:20px;border-bottom:1px solid var(--el-border-color);padding-bottom:18px}.review-header h2{margin:4px 0;font-size:24px}.review-header p{margin:6px 0}.eyebrow{font-size:12px;color:var(--el-color-primary);letter-spacing:1px}.muted{color:var(--el-text-color-secondary);font-size:13px}.header-actions{display:flex;gap:8px;flex-shrink:0}.review-totals{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--el-border-color);border-radius:8px;background:var(--el-bg-color)}.review-totals>div{display:flex;justify-content:space-between;align-items:center;padding:18px 20px;border-right:1px solid var(--el-border-color)}.review-totals>div:last-child{border-right:0}.review-totals span{font-size:13px;color:var(--el-text-color-secondary)}.review-totals strong{font-size:25px;font-variant-numeric:tabular-nums}.review-filters{display:flex;flex-direction:column;gap:12px}.review-filters>div{display:flex;gap:10px}.review-filters .el-input{max-width:380px}.review-filters .el-select{width:200px}.table-sub{margin:5px 0;font-size:13px}.overdue{color:var(--el-color-danger)}.review-table{border:1px solid var(--el-border-color);border-radius:8px}.el-pagination{align-self:flex-end}@media(max-width:760px){.review-header{flex-direction:column;align-items:flex-start}.review-totals{grid-template-columns:repeat(2,1fr)}.review-totals>div{padding:12px}.review-filters>div{flex-wrap:wrap}.review-filters .el-radio-group{display:flex;flex-wrap:wrap}}
</style>
