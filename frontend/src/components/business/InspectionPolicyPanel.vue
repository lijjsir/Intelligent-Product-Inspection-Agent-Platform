<script setup lang="ts">
import { computed, onMounted, ref,watch } from "vue";
import { extractApiErrorMessage } from "@/api/http";
import { inspectionSpecApi } from "@/api/inspection_spec.api";
import { inspectionExecutionApi } from "@/api/inspection-execution.api";
import { useAuthStore } from "@/stores/auth.store";
import {ElMessageBox} from 'element-plus';

const auth = useAuthStore();
const specs = ref<any[]>([]);
const published = ref<any[]>([]);
const selected = ref<any>(null);
const dialog = ref(false);
const preview = ref(false);
const requiredFields = ref<string[]>([]);
const inputModes=ref<string[]>(['image','measurement','mixed','report']);
const imageCount=ref(0);
const requiredViews=ref('');
const fieldChoices=[{value:'product_category',label:'产品类别'},{value:'production_date',label:'实际生产日期'},{value:'sample_ids',label:'本次样品'},
  {value:'session_id',label:'检测会话'},{value:'quality_product_id',label:'具体产品'},{value:'production_batch_ref',label:'生产批次'},{value:'unit_serial_ref',label:'单件标识'}];
const modeLabel=(mode:string)=>({image:'图片辅助',measurement:'设备测量',mixed:'混合输入',report:'检测报告'} as Record<string,string>)[mode]||mode;
const reason = ref("");
const error = ref("");
const loading = ref(false);
const busy = ref(false);

const selectedSnapshot = computed(() => selected.value ? {
  name: selected.value.name,
  spec_code: selected.value.spec_code,
  version: selected.value.version,
  required_image_count: imageCount.value,
  required_views: requiredViews.value.split('\n').map(item=>item.trim()).filter(Boolean),
  input_modes:inputModes.value,
  required_fields: requiredFields.value,
  review_on_fail: true,
  review_on_report_transcription: true,
  require_independent_review: true,
  product_limits: "from_confirmed_standard_requirements",
} : null);

async function load() {
  loading.value = true;
  error.value = "";
  try {
    specs.value = (await inspectionSpecApi.list({ suppressErrorToast: true })).data.data;
    published.value = (await inspectionExecutionApi.policies({ suppressErrorToast: true })).data.data;
  } catch (cause) {
    specs.value = [];
    published.value = [];
    error.value = extractApiErrorMessage(cause, "检测执行策略接口不可用。请重启后端并确认已加载 0113_inspection_execution 迁移。");
  } finally {
    loading.value = false;
  }
}

function open(row: any) {
  selected.value = row;
  const latest=published.value.find(item=>item.spec_id===row.id&&item.status==='published')?.snapshot;
  requiredFields.value = latest?.required_fields?.filter((field:string)=>fieldChoices.some(item=>item.value===field))||[];
  inputModes.value=latest?.input_modes||['image','measurement','mixed','report'];
  imageCount.value=latest?.required_image_count??row.required_image_count??0;
  requiredViews.value=(latest?.required_views||row.required_views||[]).join('\n');
  reason.value = "";
  preview.value = false;
  error.value = "";
  dialog.value = true;
}

async function publish() {
  if (!selected.value) return;
  busy.value = true;
  error.value = "";
  try {
    await inspectionExecutionApi.publishPolicy(selected.value.id, {
      request_key: crypto.randomUUID(),
      expected_updated_at: selected.value.updated_at,
      required_fields: requiredFields.value,
      input_modes:inputModes.value,
      required_image_count:imageCount.value,
      required_views:requiredViews.value.split('\n').map(item=>item.trim()).filter(Boolean),
      review_on_fail: true,
      review_on_report_transcription: true,
      reason: reason.value.trim(),
    });
    dialog.value = false;
    await load();
  } catch (cause) {
    error.value = extractApiErrorMessage(cause, "发布未完成，请刷新后核对策略版本");
  } finally {
    busy.value = false;
  }
}

async function withdraw(row:any){
  try{
    const answer=await ElMessageBox.prompt(`撤回 ${row.snapshot.name} 的第 ${row.snapshot.publication_no||1} 发布版后，引用它的执行结果将提示重新核验。请填写原因。`,'撤回执行策略',
      {inputType:'textarea',inputValidator:(value:string)=>value.trim().length>=4||'请填写至少四个有效字符'});
    busy.value=true;
    await inspectionExecutionApi.withdrawPolicy(row.id,{expected_version:1,request_key:crypto.randomUUID(),reason:answer.value.trim(),evidence_refs:[]});
    await load();
  }catch(cause){if(cause!=='cancel'&&cause!=='close')error.value=extractApiErrorMessage(cause,'撤回未完成，请刷新后核对版本');}
  finally{busy.value=false;}
}

onMounted(load);
watch([requiredFields,inputModes,imageCount,requiredViews],()=>{preview.value=false;},{deep:true});
</script>

<template>
  <section class="policy-panel">
    <header>
      <div>
        <p class="eyebrow">规则与复核 / 版本化策略</p>
        <h3>策略草稿与发布版本</h3>
        <p>标准要求总览负责项目、单位和限值；本页只负责输入完整性、失败复核和报告转录核验。</p>
      </div>
      <el-button @click="load">刷新</el-button>
    </header>
    <el-alert title="策略不会生成缺失的产品标准，也不会凭 AI 置信度签发产品结论。发布前必须查看完整快照。" type="info" :closable="false" />
    <el-alert v-if="error" :title="error" type="warning" show-icon :closable="false" />
    <el-table v-loading="loading" :data="specs" empty-text="暂无可配置的检测场景">
      <el-table-column prop="name" label="检测场景" />
      <el-table-column prop="spec_code" label="策略编码" />
      <el-table-column label="图片输入"><template #default="{ row }">{{ row.required_image_count || 0 }} 张 · {{ row.required_views?.join("、") || "按任务材料判断" }}</template></el-table-column>
      <el-table-column label="状态"><template #default="{ row }"><el-tag :type="row.is_active&&row.org_id===auth.orgId ? 'success' : 'info'">{{ !row.org_id?'平台默认（只读）':row.is_active?'可编辑草稿':'已停用' }}</el-tag></template></el-table-column>
      <el-table-column label="操作"><template #default="{ row }"><el-button v-if="auth.hasPermission('inspection_spec') && row.is_active&&row.org_id===auth.orgId" link type="primary" @click="open(row)">查看并发布</el-button><span v-else class="muted">只读</span></template></el-table-column>
    </el-table>
    <div class="published-heading"><h3>已发布版本</h3><span>版本不可覆盖，撤回后保留审计记录</span></div>
    <el-table :data="published" empty-text="尚无已发布策略">
      <el-table-column label="名称"><template #default="{ row }">{{ row.snapshot?.name || "未知策略" }}</template></el-table-column>
      <el-table-column label="版本"><template #default="{ row }">{{ row.snapshot?.version || "—" }} · 第 {{ row.snapshot?.publication_no||1 }} 发布版</template></el-table-column>
      <el-table-column label="状态"><template #default="{row}"><el-tag :type="row.status==='published'?'success':'info'">{{ row.status==='published'?'已发布':'已撤回' }}</el-tag></template></el-table-column>
      <el-table-column prop="created_at" label="发布时间" />
      <el-table-column label="策略内容">输入完整性 · 失败复核 · 报告转录核验 · 独立专业复核</el-table-column>
      <el-table-column label="操作" width="110"><template #default="{row}"><el-button v-if="auth.hasPermission('inspection_spec')&&row.status==='published'" link type="danger" :disabled="busy" @click="withdraw(row)">撤回版本</el-button></template></el-table-column>
    </el-table>

    <el-dialog v-model="dialog" class="policy-publish-dialog" title="发布检测执行策略" width="min(760px, 92vw)" top="8vh" append-to-body :close-on-click-modal="false">
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <el-form label-position="top">
        <el-form-item label="适用输入类型" required><el-checkbox-group v-model="inputModes"><el-checkbox v-for="mode in ['image','measurement','mixed','report']" :key="mode" :value="mode">{{ modeLabel(mode) }}</el-checkbox></el-checkbox-group></el-form-item>
        <el-form-item label="任务必填资料"><el-select v-model="requiredFields" multiple style="width:100%" placeholder="选择本场景必须有的资料"><el-option v-for="field in fieldChoices" :key="field.value" :value="field.value" :label="field.label"/></el-select></el-form-item>
        <el-form-item label="图片最少数量（仅图片 / 混合输入）"><el-input-number v-model="imageCount" :min="0" :max="500"/></el-form-item>
        <el-form-item label="所需图片视角（每行一条，仅图片 / 混合输入）"><el-input v-model="requiredViews" type="textarea" :rows="3" placeholder="例如：正面&#10;背面&#10;铭牌"/></el-form-item>
        <el-form-item label="发布说明" required><el-input v-model="reason" type="textarea" :rows="3" placeholder="说明这次策略版本解决了什么问题" /></el-form-item>
      </el-form>
      <section v-if="preview&&selectedSnapshot" class="snapshot"><h3>发布内容核对</h3><el-descriptions :column="1" border><el-descriptions-item label="场景">{{ selectedSnapshot.name }} · {{ selectedSnapshot.version }}</el-descriptions-item><el-descriptions-item label="适用输入">{{ inputModes.map(modeLabel).join('、') }}</el-descriptions-item><el-descriptions-item label="必填资料">{{ fieldChoices.filter(field=>requiredFields.includes(field.value)).map(field=>field.label).join('、')||'无额外要求' }}</el-descriptions-item><el-descriptions-item label="图片要求">{{ imageCount }} 张 · {{ requiredViews.split('\n').filter(Boolean).join('、')||'无特定视角' }}</el-descriptions-item><el-descriptions-item label="复核">独立专家复核；报告逐项核对；失败项目复核</el-descriptions-item><el-descriptions-item label="产品要求">只引用已确认、已发布的标准项目</el-descriptions-item></el-descriptions></section>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button @click="preview = true">预览完整策略</el-button><el-button type="primary" :loading="busy" :disabled="!preview || !inputModes.length || reason.trim().length < 4" @click="publish">确认发布并保留版本</el-button></template>
    </el-dialog>
  </section>
</template>

<style scoped>
.policy-panel { display: flex; flex-direction: column; gap: 18px; }
.policy-panel header { display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; border-bottom: 1px solid var(--piap-line, #dbe5f2); padding-bottom: 16px; }
.policy-panel h3 { margin: 2px 0 6px; font-size: 20px; }
.policy-panel header p:not(.eyebrow) { margin: 0; color: var(--el-text-color-secondary); font-size: 14px; line-height: 1.8; }
.eyebrow { margin: 0; color: #2563eb; font-size: 11px; font-weight: 700; letter-spacing: .14em; }
.published-heading { display: flex; align-items: baseline; gap: 12px; margin-top: 4px; }
.published-heading h3 { margin: 0; color: #1e293b; }
.published-heading span, .muted { color: var(--el-text-color-secondary); font-size: 12px; }
.snapshot { padding: 16px; border: 1px solid var(--el-border-color); border-radius: 10px; background: var(--el-fill-color-light); }
.snapshot h3 { margin: 0 0 10px; font-size: 14px; }
.snapshot pre { max-height: 360px; margin: 0; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; line-height: 1.6; }
@media (max-width: 680px) { .policy-panel header { flex-direction: column; } }
</style>
