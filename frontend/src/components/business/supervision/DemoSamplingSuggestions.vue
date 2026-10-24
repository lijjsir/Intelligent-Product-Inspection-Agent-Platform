<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { extractApiErrorMessage } from "@/api/http";
import {
  demoSamplingApi,
  type DemoSamplingCandidate,
  type DemoSamplingContent,
  type DemoSamplingSuggestion,
} from "@/api/demo-sampling.api";
import { useRuntimeContext } from "@/composables/useRuntimeContext";
import { useAuthStore } from "@/stores/auth.store";
import SupervisionModuleHeader from "./SupervisionModuleHeader.vue";
import { formatServerDateTime } from "@/utils/date-time";

const route = useRoute(),
  router = useRouter(),
  auth = useAuthStore();
const runtime = useRuntimeContext();
const isDemo = computed(() => runtime.context.value?.execution_mode === "demo");
const caseId = computed(() =>
  typeof route.query.case_id === "string" ? route.query.case_id : undefined,
);
const loading = ref(false),
  saving = ref(false),
  error = ref("");
const candidates = ref<DemoSamplingCandidate[]>([]),
  blockers = ref<string[]>([]),
  rows = ref<DemoSamplingSuggestion[]>([]);
const selected = ref<DemoSamplingSuggestion | null>(null),
  form = ref<DemoSamplingContent | null>(null);
function paging(){return reactive({page:1,cursors:[undefined] as Array<string|undefined>,next:null as string|null});}
const listPaging=paging(),candidatePaging=paging(),keyword=ref(''),appliedKeyword=ref('');
function resetPages(){for(const state of [listPaging,candidatePaging]){state.page=1;state.cursors=[undefined];state.next=null;}}
function movePage(kind:'list'|'candidates',direction:number){if(loading.value||saving.value)return;const state=kind==='list'?listPaging:candidatePaging;if(direction>0){if(!state.next)return;state.cursors[state.page]=state.next;}else if(state.page<=1)return;state.page+=direction;void load(true);}
let epoch = 0;
let alive = true;
function apply(row: DemoSamplingSuggestion | null) {
  selected.value = row;
  form.value = row ? { ...row.content } : null;
}
async function load(listOnly=false) {
  if (auth.role !== "expert") return;
  const key = ++epoch;
  loading.value = true;
  error.value = "";
  if(!listOnly)apply(null);
  rows.value = [];
  candidates.value = [];
  blockers.value = [];
  try {
    await runtime.load();
    const [list, options] = await Promise.all([
      demoSamplingApi.page<DemoSamplingSuggestion>('suggestions',{case_id:caseId.value,cursor:listPaging.cursors[listPaging.page-1],keyword:appliedKeyword.value}),
      demoSamplingApi.page<DemoSamplingCandidate>('candidates',{case_id:caseId.value,cursor:candidatePaging.cursors[candidatePaging.page-1],keyword:appliedKeyword.value}),
    ]);
    const id = typeof route.query.suggestion === "string" ? route.query.suggestion : null;
    const detail=listOnly?selected.value:id?(await demoSamplingApi.get(id)).data.data:null;
    if(detail&&caseId.value&&detail.snapshot.case_id!==caseId.value)throw new Error('建议不属于当前事项');
    if (key !== epoch) return;
    rows.value = list.data.data.items;
    listPaging.next=list.data.data.next_cursor;candidatePaging.next=options.data.data.next_cursor;
    candidates.value = options.data.data.items;
    blockers.value = options.data.data.blockers;
    if(!listOnly)apply(detail);
  } catch (e) {
    if (key === epoch) {
      error.value = extractApiErrorMessage(e, "加载抽查建议失败");
      apply(null);
      rows.value = [];
      candidates.value = [];
    }
  } finally {
    if (key === epoch) loading.value = false;
  }
}
function open(row: DemoSamplingSuggestion) {
  void router.replace({ query: { ...route.query, suggestion: row.id } });
}
async function create(candidate: DemoSamplingCandidate) {
  const requestedCase = caseId.value;
  saving.value = true;
  error.value = "";
  try {
    const row = (await demoSamplingApi.create(candidate)).data.data;
    if (!alive || caseId.value !== requestedCase) return;
    await router.replace({ query: { ...route.query, suggestion: row.id } });
    await load();
  } catch (e) {
    if (alive && caseId.value === requestedCase)
      error.value = extractApiErrorMessage(e, "创建失败，请刷新核对依据");
  } finally {
    saving.value = false;
  }
}
async function save(confirm = false) {
  if (!selected.value || !form.value) return;
  const target = selected.value;
  saving.value = true;
  error.value = "";
  try {
    const row = (
      confirm
        ? await demoSamplingApi.confirm(target.id, target.revision)
        : await demoSamplingApi.save(target.id, target.revision, form.value)
    ).data.data;
    if (!alive || selected.value?.id !== target.id) return;
    apply(row);
    rows.value = rows.value.map((r) => (r.id === row.id ? row : r));
    ElMessage.success(confirm ? "建议已固定，未创建执行任务" : "建议已保存");
  } catch (e) {
    if (alive && selected.value?.id === target.id)
      error.value = extractApiErrorMessage(e, "操作失败，请刷新核对当前版本");
  } finally {
    saving.value = false;
  }
}
const dirty = computed(
  () => !!selected.value && JSON.stringify(form.value) !== JSON.stringify(selected.value.content),
);
watch(() => [route.query.case_id, route.query.suggestion],(now,old)=>{if(now[0]!==old?.[0])resetPages();void load();});
onMounted(()=>load());
onBeforeUnmount(() => {
  alive = false;
  ++epoch;
});
</script>

<template>
  <main class="demo-sampling-page" v-loading="loading">
    <SupervisionModuleHeader :title="isDemo ? '演示抽查建议' : '抽查建议'" tone="amber" description="依据已独立复核的风险事项和证据编写抽查建议，明确抽查对象、关注内容和资源条件。" principle="建议保留来源版本；正式抽查计划须独立批准，检测按验证需求组织。">
      <template #actions><el-button @click="router.push('/app/sampling-plans?records=1')">查看抽查计划记录</el-button><el-button :disabled="saving" @click="load()">刷新依据与列表</el-button></template>
    </SupervisionModuleHeader>
    <el-alert
      type="warning"
      :closable="false"
      :title="isDemo ? '全部为模拟资料，仅用于流程验收。建议不进入正式候选，不启动抽查或实验室检测；本页未调用真实模型。' : '建议依据已独立复核的最新研判及证据；正式抽查计划仍须独立审批，不自动启动检测。'"
    />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert
      v-if="auth.role !== 'expert'"
      type="info"
      :closable="false"
      title="请使用有权读取来源资料的研判专家账号查看建议。"
    />
    <template v-else>
      <el-form class="panel-actions" @submit.prevent="appliedKeyword=keyword.trim();resetPages();load(true)"><el-input v-model="keyword" aria-label="抽查建议搜索" placeholder="按编号或标题搜索" :maxlength="200" :disabled="loading||saving" clearable /><el-button native-type="submit" :disabled="loading||saving">搜索建议</el-button><el-button :disabled="loading||saving" @click="resetPages();load(true)">回到建议首页</el-button></el-form>
      <el-button
        v-if="caseId"
        class="return-case"
        @click="
          router.push({
            path: '/app/risk-assessments',
            query: { case_id: caseId, tab: 'assessment' },
          })
        "
        >返回来源事项</el-button
      >
      <el-button v-if="!isDemo" @click="router.push('/app/sampling-plans')">查看正式抽查计划</el-button>
      <section class="sampling-candidates">
        <h2>建议候选</h2>
        <p>最新研判须由另一位专家独立复核通过；无需协同工作项或会议。</p>
        <el-alert
          v-for="item in blockers"
          :key="item"
          :title="item"
          type="info"
          :closable="false"
        />
        <el-empty
          v-if="!candidates.length && !loading"
          :description="candidatePaging.next ? '本页暂无可用候选，可继续查看下一页' : '暂无符合条件的建议候选，请先完成研判及独立复核'"
          :image-size="56"
        />
        <article
          v-for="candidate in candidates"
          :key="candidate.context_hash"
          class="candidate-card"
        >
          <div>
            <strong
              >{{ candidate.snapshot.case_code }} · {{ candidate.snapshot.case_title }}</strong
            >
            <p>
              固定研判第 {{ candidate.snapshot.assessment_version }} 版 ·
              {{ candidate.snapshot.source_record_ids.length }} 条来源 ·
              {{ candidate.snapshot.evidence_ids.length }} 条证据
            </p>
          </div>
          <el-button type="primary" :disabled="saving" @click="create(candidate)">{{
            rows.some((r) => r.context_hash === candidate.context_hash)
              ? "查看已有建议"
              : "编写建议"
          }}</el-button>
        </article>
        <div class="panel-actions"><el-button :disabled="loading||saving||candidatePaging.page<=1" @click="movePage('candidates',-1)">上一页候选</el-button><span>第 {{ candidatePaging.page }} 页 · 本页 {{ candidates.length }} 项</span><el-button :disabled="loading||saving||!candidatePaging.next" @click="movePage('candidates',1)">下一页候选</el-button></div>
      </section>
      <section>
        <h2>建议记录</h2>
        <el-empty
          v-if="!rows.length && !loading"
          :description="listPaging.next ? '本页暂无可访问建议，可继续查看下一页' : '尚未编写抽查建议'"
          :image-size="56"
        />
        <button
          v-for="row in rows"
          :key="row.id"
          class="suggestion-row"
          :class="{ active: selected?.id === row.id }"
          :disabled="saving"
          @click="open(row)"
        >
          <strong>{{ row.title }}</strong
          ><span
            >{{
              !row.is_current
                ? "待重评"
                : row.status.endsWith("confirmed")
                  ? (isDemo ? "演示建议已固定" : "建议已固定")
                  : (isDemo ? "演示草稿" : "草稿")
            }}
            · 修订 {{ row.revision }}</span
          >
        </button>
        <div class="panel-actions"><el-button :disabled="loading||saving||listPaging.page<=1" @click="movePage('list',-1)">上一页建议</el-button><span>第 {{ listPaging.page }} 页 · 本页 {{ rows.length }} 条</span><el-button :disabled="loading||saving||!listPaging.next" @click="movePage('list',1)">下一页建议</el-button></div>
      </section>
      <section v-if="selected && form" class="suggestion-detail">
        <header>
          <h2>{{ selected.title }}</h2>
          <el-tag :type="selected.is_current ? 'info' : 'warning'">{{
            selected.effective_status === "needs_reassessment"
              ? "待重评"
              : selected.status.endsWith("confirmed")
                ? (isDemo ? "演示建议已固定" : "建议已固定")
                : (isDemo ? "演示草稿" : "草稿")
          }}</el-tag>
        </header>
        <el-alert
          v-if="!selected.is_current"
          type="warning"
          :closable="false"
          :title="selected.stale_reason"
        />
        <el-button v-if="!isDemo && selected.status === 'confirmed' && selected.is_current" type="primary"
          @click="router.push({path:'/app/sampling-plans', query:{case_id:selected.snapshot.case_id, source_suggestion_id:selected.id}})">带入正式计划草稿</el-button>
        <p class="boundary">{{ selected.boundary }}</p>
        <h3>固定的来源与复核</h3>
        <p>
          {{ selected.snapshot.case_code }} · 研判第
          {{ selected.snapshot.assessment_version }} 版；{{
            selected.snapshot.source_record_ids.length
          }}
          条原始资料、{{ selected.snapshot.evidence_ids.length }} 条证据。
        </p>
        <el-button @click="router.push({path:'/app/risk-assessments',query:{case_id:selected.snapshot.case_id,assessment_id:selected.snapshot.assessment_id}})"
          >查看本版研判</el-button
        >
        <p class="preserve">{{ selected.snapshot.conclusion.summary }}</p>
        <p class="preserve">研判限制：{{ selected.snapshot.conclusion.limitations }}</p>
        <p>证据缺口：{{ selected.snapshot.conclusion.missing_inputs.join("；") || "未填写" }}</p>
        <p class="preserve">独立复核意见：{{ selected.snapshot.review.comment }}</p>
        <p v-for="object in selected.snapshot.objects" :key="object.kind">
          {{ object.label }}：{{ object.name }}
        </p>
        <details>
          <summary>查看固定的原始资料链接与对象引用</summary>
          <p v-for="object in selected.snapshot.objects" :key="object.id">
            {{ object.label }}档案编号：{{ object.id }}
          </p>
          <el-button
            v-for="(id, index) in selected.snapshot.source_record_ids"
            :key="id"
            link
            @click="router.push({ path: '/app/quality-data', query: { record: id } })"
            >原始资料 {{ index + 1 }}</el-button
          >
        </details>
        <h3 v-if="selected.snapshot.collaboration_id">历史协作意见快照</h3>
        <p v-if="selected.snapshot.collaboration_id" class="preserve">{{ selected.snapshot.decision_note || "未填写处理说明" }}</p>
        <article v-for="opinion in selected.snapshot.opinions" :key="opinion.id" class="opinion">
          <small
            >{{ opinion.author }} ·
            {{ opinion.origin === "meeting" ? "会议公开消息" : "协作评论" }}</small
          >
          <p class="preserve">{{ opinion.content }}</p>
        </article>
        <div v-if="!selected.can_edit||selected.snapshot.collaboration_id" class="fixed-suggestion">
          <h3>抽查理由</h3>
          <p class="preserve">{{ selected.content.rationale || "未填写" }}</p>
          <h3>关注内容</h3>
          <p class="preserve">{{ selected.content.focus || "未填写" }}</p>
          <h3>资源假设、限制与待核实事项</h3>
          <p class="preserve">{{ selected.content.limitations || "未填写" }}</p>
          <div class="optional-fields">
            <p>建议样本数量：{{ selected.content.sample_quantity ?? "未知" }}</p>
            <p>批次：{{ selected.content.batch ?? "未知" }}</p>
            <p>地点：{{ selected.content.location ?? "未知" }}</p>
            <p>建议时间：{{ selected.content.proposed_time ?? "未知" }}</p>
          </div>
        </div>
        <el-form v-else label-position="top" :disabled="saving" @submit.prevent>
          <el-form-item label="抽查理由"
            ><el-input v-model="form.rationale" type="textarea" :rows="3" :maxlength="4000"
          /></el-form-item>
          <el-form-item label="关注内容"
            ><el-input v-model="form.focus" type="textarea" :rows="3" :maxlength="4000"
          /></el-form-item>
          <el-form-item label="资源假设、限制与待核实事项"
            ><el-input v-model="form.limitations" type="textarea" :rows="3" :maxlength="4000"
          /></el-form-item>
          <p>以下信息未知时留空。数量与安排均为建议，不代表已下达任务；适用标准须另行核实。</p>
          <div class="optional-fields">
            <el-form-item label="建议样本数量（未知可清空）"
              ><el-input-number
                :model-value="form.sample_quantity ?? undefined"
                :min="1"
                :max="100000"
                @update:model-value="form.sample_quantity = $event ?? null"
            /></el-form-item>
            <el-form-item label="批次（未知留空）"
              ><el-input
                :model-value="form.batch ?? ''"
                @update:model-value="form.batch = $event.trim() || null"
            /></el-form-item>
            <el-form-item label="地点（未知留空）"
              ><el-input
                :model-value="form.location ?? ''"
                @update:model-value="form.location = $event.trim() || null"
            /></el-form-item>
            <el-form-item label="建议时间（未知留空）"
              ><el-input
                :model-value="form.proposed_time ?? ''"
                @update:model-value="form.proposed_time = $event.trim() || null"
            /></el-form-item>
          </div>
        </el-form>
        <div v-if="selected.can_edit&&!selected.snapshot.collaboration_id" class="actions">
          <el-button :loading="saving" @click="save(false)">{{ isDemo ? "保存演示草稿" : "保存草稿" }}</el-button
          ><el-button type="primary" :disabled="saving || dirty" @click="save(true)"
            >{{ isDemo ? "确认并固定演示建议" : "确认并固定建议" }}</el-button
          ><span v-if="dirty">请先保存，再确认固定。</span>
        </div>
        <p v-if="selected.confirmed_at">
          固定于
          {{
            formatServerDateTime(selected.confirmed_at)
          }}。原建议保留；新证据或新意见需重新形成建议。
        </p>
        <details>
          <summary>操作记录</summary>
          <p v-for="(event, i) in selected.events" :key="i">
            {{ event.actor_name }} ·
            {{
              { created: "创建", saved: "保存", confirmed: "固定" }[event.action] || event.action
            }}
            · {{ formatServerDateTime(event.at) }}
          </p>
        </details>
      </section>
    </template>
  </main>
</template>

<style scoped>
.demo-sampling-page {
  display: grid;
  gap: 20px;
  padding: 20px;
  max-width: 1440px;
  margin: auto;
  color: var(--el-text-color-primary);
}
header,
.candidate-card,
.actions {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}
h1 {
  font-size: 26px;
  margin: 8px 0;
}
h2 {
  font-size: 19px;
  margin: 0 0 12px;
}
h3 {
  font-size: 16px;
  margin: 24px 0 12px;
}
p {
  line-height: 1.7;
  margin: 8px 0;
  color: var(--el-text-color-regular);
}
section {
  border: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color);
  border-radius: 8px;
  padding: 22px;
  min-width: 0;
}
.candidate-card {
  padding-top: 12px;
}
.suggestion-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  width: 100%;
  text-align: left;
  padding: 16px;
  margin-top: 8px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: var(--el-bg-color);
  color: inherit;
  cursor: pointer;
  min-height: 48px;
}
.suggestion-row.active {
  border-color: var(--el-color-primary);
}
.suggestion-row:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}
.optional-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 20px;
}
.preserve {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.opinion {
  border-left: 3px solid var(--el-border-color);
  padding: 8px 16px;
  margin: 12px 0;
}
.boundary {
  background: var(--el-fill-color-light);
  padding: 12px;
}
.actions {
  justify-content: flex-start;
}
summary {
  cursor: pointer;
  min-height: 44px;
  line-height: 44px;
}
details {
  overflow-wrap: anywhere;
}
.return-case {
  justify-self: start;
}
section :deep(.el-button) {
  min-height: 44px;
}
details :deep(.el-button) {
  white-space: normal;
  height: auto;
  text-align: left;
  overflow-wrap: anywhere;
}
@media (max-width: 700px) {
  .demo-sampling-page {
    padding: 16px;
    gap: 16px;
  }
  section {
    padding: 16px;
  }
  .optional-fields {
    grid-template-columns: 1fr;
  }
  .actions {
    align-items: stretch;
    flex-direction: column;
  }
  .actions :deep(.el-button) {
    margin-left: 0;
  }
  .candidate-card {
    align-items: stretch;
    flex-direction: column;
  }
  h1 {
    font-size: 23px;
  }
  .suggestion-row {
    font-size: 14px;
  }
}
</style>
