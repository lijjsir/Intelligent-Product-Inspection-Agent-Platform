<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { extractApiErrorMessage } from "@/api/http";
import { useAuthStore } from "@/stores/auth.store";
import { formatServerDateTime } from "@/utils/date-time";
import type {
  DemoRiskContent,
  DemoRiskContext,
  QualitySourceRecord,
  RiskAssessmentV4,
} from "@/types/quality-risk.types";

const props = defineProps<{
  caseId: string;
  assessment: RiskAssessmentV4 | null;
  isLatest: boolean;
  context: DemoRiskContext;
  records: QualitySourceRecord[];
}>();
const emit = defineEmits<{ changed: []; reload: [] }>();
const auth = useAuthStore(),
  router = useRouter();
const busy = ref(false),
  error = ref(""),
  comment = ref("");
const blank: DemoRiskContent = {
  summary: "",
  reasoning: "",
  limitations: "",
  risk_type: null,
  risk_level: "unknown",
  cited_record_ids: [],
  missing_inputs: [],
  recommendations: [],
};
const form = reactive<DemoRiskContent>({ ...blank });
const missingLines = ref(""),
  recommendationLines = ref("");
const baseline = ref("");
let requestKey = crypto.randomUUID();
const workflow = computed(() => props.assessment?.demo_workflow);
const latest = computed(() => !props.assessment || props.isLatest);
const isExpert = computed(() => auth.role === "expert" && props.context.can_author);
const own = computed(() => props.assessment?.submitted_by === auth.userId);
const fresh = computed(() => !!props.assessment?.demo_validation?.is_current);
const editable = computed(
  () =>
    isExpert.value &&
    own.value &&
    latest.value &&
    props.assessment?.status === "demo_draft" &&
    fresh.value,
);
const canCreate = computed(
  () =>
    isExpert.value &&
    latest.value &&
    !props.context.blockers.length &&
    (!workflow.value ||
      ["demo_reviewed", "demo_revise", "demo_request_evidence"].includes(
        props.assessment?.status || "",
      ) ||
      (own.value && !fresh.value)),
);
const showReview = computed(
  () => latest.value && isExpert.value && props.assessment?.status === "demo_submitted",
);
const reviewAllowed = computed(() => showReview.value && !own.value);
const statusLabels: Record<string, string> = {
  demo_draft: "演示草稿",
  demo_submitted: "演示待独立复核",
  demo_reviewed: "演示复核通过",
  demo_revise: "演示退回修改",
  demo_request_evidence: "演示退回补证",
  needs_reassessment: "依据变化，待重评",
};
const actionLabels: Record<string, string> = {
  created: "创建草稿",
  saved: "保存草稿",
  submitted: "提交指定版本",
  reviewed: "独立复核",
};
const decisionLabels: Record<string, string> = {
  approve: "演示通过",
  revise: "退回修改",
  request_evidence: "退回补证",
};
const levelLabels: Record<string, string> = {
  unknown: "未知",
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
};
const lines = (value: string) => [
  ...new Set(
    value
      .split(/\r?\n/)
      .map((x) => x.trim())
      .filter(Boolean),
  ),
];
const currentContent = computed<DemoRiskContent>(() => ({
  ...form,
  risk_type: form.risk_type?.trim() || null,
  missing_inputs: lines(missingLines.value),
  recommendations: lines(recommendationLines.value),
}));
const dirty = computed(() => JSON.stringify(currentContent.value) !== baseline.value);
watch(
  () => [props.assessment?.id, workflow.value?.revision],
  () => {
    const content = workflow.value?.content || blank;
    Object.assign(form, JSON.parse(JSON.stringify(content)));
    missingLines.value = content.missing_inputs.join("\n");
    recommendationLines.value = content.recommendations.join("\n");
    baseline.value = JSON.stringify(currentContent.value);
    error.value = "";
    comment.value = "";
    requestKey = crypto.randomUUID();
  },
  { immediate: true },
);
async function act(operation: () => Promise<unknown>, success: string) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await operation();
    ElMessage.success(success);
    emit("changed");
  } catch (e) {
    error.value = extractApiErrorMessage(e);
  } finally {
    busy.value = false;
  }
}
function create() {
  void act(
    () =>
      qualityRiskApi.createDemoDraft(props.caseId, {
        base_assessment_id: props.assessment?.id || null,
        expected_basis_hash: props.context.basis_hash,
        request_key: requestKey,
      }),
    "已创建人工演示草稿",
  );
}
function save() {
  if (!props.assessment || !workflow.value) return;
  void act(
    () =>
      qualityRiskApi.saveDemoDraft(
        props.caseId,
        props.assessment!.id,
        workflow.value!.revision,
        currentContent.value,
      ),
    "草稿已保存，可刷新恢复",
  );
}
function submit() {
  if (!props.assessment || !workflow.value) return;
  if (dirty.value) {
    error.value = "请先保存当前修改，再提交复核";
    return;
  }
  void act(
    () =>
      qualityRiskApi.submitDemoDraft(props.caseId, props.assessment!.id, workflow.value!.revision),
    "已提交此版本，等待另一位专家复核",
  );
}
function review(decision: "approve" | "revise" | "request_evidence") {
  if (!props.assessment || !workflow.value) return;
  if (!comment.value.trim()) {
    error.value = "请填写针对本版本的复核意见";
    return;
  }
  void act(
    () =>
      qualityRiskApi.reviewDemoDraft(
        props.caseId,
        props.assessment!.id,
        workflow.value!.revision,
        decision,
        comment.value.trim(),
      ),
    decision === "approve" ? "已完成独立演示复核" : "已记录退回意见，请编写新版草稿",
  );
}
function raw(id: string) {
  void router.push({ path: "/app/quality-data", query: { record: id } });
}
</script>

<template>
  <section class="demo-risk-workflow" aria-label="演示人工研判与独立复核">
    <div class="demo-flow-heading">
      <div>
        <el-tag type="warning" effect="plain">演示 · 人工编写</el-tag>
        <h3>研判提交与独立复核</h3>
      </div>
      <span>人工流程 · 未调用真实模型</span>
    </div>
    <p class="boundary">{{ context.boundary }}</p>
    <el-button v-if="assessment && !isLatest" @click="emit('reload')">返回最新版本</el-button>
    <el-alert v-if="error" :title="error" type="error" :closable="false" class="workflow-error" />
    <div v-if="error" class="recovery">
      <el-button :disabled="busy" @click="emit('reload')">重新加载（放弃未保存输入）</el-button>
    </div>
    <el-alert
      v-if="context.blockers.length"
      type="warning"
      :closable="false"
      :title="context.blockers.map((b) => b.message).join('；')"
    />
    <template v-if="!workflow"
      ><div class="initial-draft">
        <h4>初始化参考草稿</h4>
        <p v-if="assessment">第 {{ assessment.version }} 版 · 初始化记录，未复核</p>
        <ul v-if="assessment?.missing_inputs.length">
          <li v-for="(item, index) in assessment.missing_inputs" :key="index">{{ item }}</li>
        </ul>
        <p>原有资料、版本继续保留。创建人工演示版本后，可整理判断依据并提交另一位专家复核。</p>
        <el-button v-if="canCreate" type="primary" :loading="busy" @click="create"
          >创建人工演示草稿</el-button
        >
        <p v-else>
          {{
            isLatest
              ? "请由本组织研判专家核对可用资料后创建草稿。"
              : "历史版本仅供查阅，请返回最新版本继续操作。"
          }}
        </p>
      </div></template
    >
    <template v-else>
      <div class="workflow-version">
        <strong>第 {{ assessment!.version }} 版</strong
        ><el-tag :type="assessment!.status === 'demo_reviewed' && fresh ? 'success' : 'info'">{{
          statusLabels[assessment!.effective_status || assessment!.status] || assessment!.status
        }}</el-tag
        ><span v-if="!isLatest">历史版本 · 仅供查阅</span
        ><small>编写人 {{ workflow.author_name }}</small>
      </div>
      <el-alert
        v-if="!fresh"
        title="本版依据已变化或不可用，保留原内容与复核意见，请创建新版重新提交。"
        type="warning"
        :closable="false"
      />
      <p v-if="assessment!.status === 'demo_submitted'" class="submission-note">
        已于 {{ formatServerDateTime(workflow.submitted_at) }} 提交第
        {{ assessment!.version }} 版，提交后内容锁定。
      </p>
      <el-form v-if="editable" label-position="top" class="demo-draft-form" :disabled="busy">
        <el-form-item label="演示结论"
          ><el-input
            v-model="form.summary"
            type="textarea"
            :rows="3"
            maxlength="4000"
            placeholder="说明当前能够判断的线索与结论范围"
        /></el-form-item>
        <el-form-item label="判断依据"
          ><el-input
            v-model="form.reasoning"
            type="textarea"
            :rows="4"
            maxlength="8000"
            placeholder="结合原始资料和市场线索说明判断依据，保留尚未核对的条件"
        /></el-form-item>
        <el-form-item label="引用原始资料"
          ><el-checkbox-group v-model="form.cited_record_ids" class="citation-options"
            ><div v-for="record in records" :key="record.id">
              <el-checkbox :value="record.id"
                ><span
                  >{{ record.external_record_id || record.id }} ·
                  {{ String(record.content.text || "附件资料").slice(0, 65) }}</span
                ></el-checkbox
              ><el-button link type="primary" @click="raw(record.id)">查看原文</el-button>
            </div></el-checkbox-group
          ></el-form-item
        >
        <div class="draft-pair">
          <el-form-item label="关注问题（可留空）"
            ><el-input
              v-model="form.risk_type"
              maxlength="128"
              placeholder="例如：温升异常线索" /></el-form-item
          ><el-form-item label="演示关注等级"
            ><el-select v-model="form.risk_level"
              ><el-option
                v-for="(label, value) in levelLabels"
                :key="value"
                :label="label"
                :value="value" /></el-select
          ></el-form-item>
        </div>
        <el-form-item label="证据缺口（每行一项）"
          ><el-input
            v-model="missingLines"
            type="textarea"
            :rows="3"
            placeholder="保留真实资料、适用标准、测量条件等尚待核对的信息"
        /></el-form-item>
        <el-form-item label="适用范围与限制"
          ><el-input
            v-model="form.limitations"
            type="textarea"
            :rows="3"
            maxlength="4000"
            placeholder="说明模拟资料、未知信息以及结论不能覆盖的范围"
        /></el-form-item>
        <el-form-item label="后续建议（可选，每行一项）"
          ><el-input v-model="recommendationLines" type="textarea" :rows="2"
        /></el-form-item>
        <div class="draft-actions">
          <el-button :loading="busy" @click="save">保存演示草稿</el-button
          ><el-button type="primary" :loading="busy" :disabled="dirty" @click="submit"
            >提交本版演示复核</el-button
          ><span>{{ dirty ? "有未保存修改" : "已保存，可提交指定版本" }}</span>
        </div>
      </el-form>
      <div v-else class="demo-content-snapshot">
        <section>
          <h4>演示结论</h4>
          <p>{{ workflow.content.summary || "尚未填写" }}</p>
        </section>
        <section>
          <h4>判断依据</h4>
          <p>{{ workflow.content.reasoning || "尚未填写" }}</p>
        </section>
        <section>
          <h4>引用原始资料</h4>
          <p v-if="!workflow.content.cited_record_ids.length">尚未引用资料</p>
          <div v-for="id in workflow.content.cited_record_ids" :key="id" class="cited-record">
            <span>{{ records.find((r) => r.id === id)?.external_record_id || id }}</span
            ><el-button link type="primary" @click="raw(id)">查看原文与附件</el-button>
          </div>
        </section>
        <div class="snapshot-meta">
          <span>关注问题：{{ workflow.content.risk_type || "待核对" }}</span
          ><span>演示等级：{{ levelLabels[workflow.content.risk_level] }}</span
          ><span>发生概率：未知</span>
        </div>
        <section>
          <h4>证据缺口</h4>
          <ul>
            <li v-for="item in workflow.content.missing_inputs" :key="item">{{ item }}</li>
          </ul>
        </section>
        <section>
          <h4>适用范围与限制</h4>
          <p>{{ workflow.content.limitations || "尚未填写" }}</p>
        </section>
        <section v-if="workflow.content.recommendations.length">
          <h4>后续建议</h4>
          <ul>
            <li v-for="item in workflow.content.recommendations" :key="item">{{ item }}</li>
          </ul>
        </section>
      </div>
      <section v-if="showReview" class="demo-review-box">
        <h4>独立复核 · 第 {{ assessment!.version }} 版</h4>
        <p v-if="own">本版由你编写并提交，请由另一位专家独立复核。</p>
        <p v-else>核对本版内容、引用资料和限制后，记录复核意见。演示通过仍保留证据缺口。</p>
        <el-form label-position="top"
          ><el-form-item label="本版复核意见"
            ><el-input
              v-model="comment"
              type="textarea"
              :rows="3"
              maxlength="4000"
              :disabled="!reviewAllowed || busy" /></el-form-item
        ></el-form>
        <div class="review-buttons">
          <el-button
            type="primary"
            :disabled="!reviewAllowed || !fresh || busy"
            @click="review('approve')"
            >演示复核通过</el-button
          ><el-button :disabled="!reviewAllowed || busy" @click="review('revise')"
            >退回修改</el-button
          ><el-button :disabled="!reviewAllowed || busy" @click="review('request_evidence')"
            >退回补证</el-button
          >
        </div>
      </section>
      <section v-if="assessment!.review_comment" class="demo-review-note">
        <h4>第 {{ assessment!.version }} 版复核意见</h4>
        <p>{{ assessment!.review_comment }}</p>
        <small
          >{{ workflow.events.filter((e) => e.action === "reviewed").at(-1)?.actor_name }} ·
          {{ formatServerDateTime(assessment!.reviewed_at) }}</small
        >
      </section>
      <div v-if="canCreate" class="new-version-action">
        <el-button type="primary" plain :loading="busy" @click="create">创建新版演示草稿</el-button
        ><span>沿用本版文字，重新冻结当前资料；历史版本和复核意见继续保留。</span>
      </div>
      <details class="demo-audit">
        <summary>本版操作记录（{{ workflow.events.length }}）</summary>
        <ol>
          <li v-for="(event, index) in workflow.events" :key="index">
            <strong
              >{{ actionLabels[event.action] || event.action
              }}{{ event.decision ? " · " + decisionLabels[event.decision] : "" }}</strong
            ><span>{{ event.actor_name }} · {{ formatServerDateTime(event.at) }}</span>
            <p v-if="event.comment">{{ event.comment }}</p>
          </li>
        </ol>
      </details>
    </template>
  </section>
</template>

<style scoped>
.demo-risk-workflow {
  margin-top: 16px;
  min-width: 0;
}
.demo-flow-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.demo-flow-heading > div {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.demo-flow-heading h3 {
  margin: 0;
  font-size: 18px;
}
.demo-flow-heading > span,
.boundary,
.submission-note {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.8;
}
.boundary {
  margin: 16px 0;
  padding: 12px 16px;
  background: var(--el-fill-color-light);
  border-left: 3px solid var(--el-color-warning);
}
.initial-draft {
  padding: 20px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}
.initial-draft p {
  font-size: 14px;
  line-height: 1.8;
  color: var(--el-text-color-regular);
}
.initial-draft h4 {
  margin: 0;
}
.workflow-error {
  margin: 16px 0 8px;
}
.recovery {
  margin-bottom: 16px;
}
.workflow-version {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 20px 0 16px;
}
.workflow-version small {
  color: var(--el-text-color-secondary);
}
.demo-draft-form {
  margin-top: 20px;
}
.draft-pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.draft-pair .el-select {
  width: 100%;
}
.citation-options {
  width: 100%;
  max-height: 310px;
  overflow: auto;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 8px 12px;
}
.citation-options > div {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.citation-options .el-checkbox {
  margin: 0;
  height: auto;
  align-items: flex-start;
  min-width: 0;
}
.citation-options :deep(.el-checkbox__label) {
  white-space: normal;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
.citation-options :deep(.el-checkbox__input) {
  margin-top: 4px;
}
.citation-options .el-button {
  flex-shrink: 0;
}
.draft-actions,
.review-buttons,
.new-version-action {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin: 20px 0;
}
.draft-actions > span,
.new-version-action > span {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}
.draft-actions .el-button + .el-button,
.review-buttons .el-button + .el-button {
  margin: 0;
}
.demo-content-snapshot > section {
  border-top: 1px solid var(--el-border-color-light);
  padding: 16px 0;
}
.demo-content-snapshot h4,
.demo-review-box h4,
.demo-review-note h4 {
  margin: 0 0 10px;
  font-size: 15px;
}
.demo-content-snapshot p,
.demo-review-note p {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.8;
  overflow-wrap: anywhere;
  font-size: 14px;
}
.demo-content-snapshot ul {
  margin: 0;
  padding-left: 20px;
  line-height: 1.9;
  font-size: 14px;
}
.snapshot-meta {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  padding: 12px;
  background: var(--el-fill-color-light);
  font-size: 13px;
}
.cited-record {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 5px 0;
  font-size: 13px;
  overflow-wrap: anywhere;
}
.cited-record > span {
  min-width: 0;
}
.demo-review-box {
  padding: 20px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  margin-top: 16px;
}
.demo-review-box > p {
  font-size: 13px;
  line-height: 1.8;
}
.demo-review-note {
  padding: 18px 0;
  border-top: 1px solid var(--el-border-color-light);
}
.demo-review-note small {
  color: var(--el-text-color-secondary);
  display: block;
  margin-top: 8px;
}
.demo-audit {
  border-top: 1px solid var(--el-border-color-light);
  margin-top: 20px;
}
.demo-audit summary {
  padding: 14px 0;
  cursor: pointer;
  font-size: 13px;
}
.demo-audit li {
  font-size: 13px;
  line-height: 1.8;
  padding: 8px 0;
}
.demo-audit li > span {
  display: block;
  color: var(--el-text-color-secondary);
}
.demo-audit li p {
  margin: 4px 0;
}
.demo-audit summary:focus-visible {
  outline: 2px solid var(--el-color-primary);
}
@media (max-width: 650px) {
  .draft-pair {
    grid-template-columns: 1fr;
    gap: 0;
  }
  .demo-flow-heading h3 {
    font-size: 17px;
  }
  .demo-review-box {
    padding: 14px;
  }
  .citation-options {
    max-height: 250px;
    padding: 6px 8px;
  }
  .citation-options > div {
    flex-wrap: wrap;
  }
  .citation-options .el-checkbox {
    width: 100%;
  }
  .cited-record {
    flex-wrap: wrap;
  }
  .draft-actions > span,
  .new-version-action > span {
    width: 100%;
  }
  :deep(.el-button) {
    min-height: 44px;
  }
  :deep(textarea) {
    font-size: 16px;
  }
  .snapshot-meta {
    gap: 8px;
    flex-direction: column;
  }
}
</style>
