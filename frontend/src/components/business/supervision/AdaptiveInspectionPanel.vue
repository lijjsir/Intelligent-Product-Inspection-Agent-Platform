<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { supervisionApi } from "@/api/supervision.api";
import { useAuthStore } from "@/stores/auth.store";
import type {
  InspectionDecision,
  InspectionEvidenceState,
  InspectionGoal,
  InspectionTestItem,
  SupervisionRecord,
} from "@/types/supervision.types";

const props = defineProps<{ session: SupervisionRecord }>();
const auth = useAuthStore();
const loading = ref(false);
const goal = ref<InspectionGoal | null>(null);
const evidence = ref<InspectionEvidenceState | null>(null);
const latestDecision = ref<InspectionDecision | null>(null);
const dialog = ref(false);
const hypothesesInput = ref("");
const threshold = ref(0.8);
const maxRounds = ref(20);

const canOperate = computed(
  () => ["user", "expert"].includes(auth.role) && props.session.status !== "signed",
);
const canReviewStop = computed(
  () =>
    auth.role === "expert" &&
    latestDecision.value?.kind === "goal_reached" &&
    latestDecision.value.status === "awaiting_approval" &&
    latestDecision.value.proposed_by !== auth.userId,
);
const requiredItems = computed<InspectionTestItem[]>(() => {
  const configured = props.session.data.required_items || [];
  if (configured.length) return configured;
  return props.session.data.test_items || [];
});
const candidateItems = computed<InspectionTestItem[]>(
  () => props.session.data.candidate_items || [],
);
const sufficiencyPercent = computed(() =>
  Math.round(Number(evidence.value?.evidence_sufficiency || 0) * 100),
);
const deviceStatus = computed(() => {
  const value = evidence.value?.device_trust_state.status || "unknown";
  return { trusted: "可信", suspect: "待核验", invalid: "无效", unknown: "未知" }[value];
});
const productStatus = computed(() => {
  const value = evidence.value?.product_quality_state.status || "uncertain";
  return { normal: "未见异常", abnormal: "发现异常", uncertain: "证据不足" }[value];
});

async function load() {
  loading.value = true;
  try {
    goal.value = (await supervisionApi.inspectionGoal(props.session.id)).data.data;
    evidence.value = (await supervisionApi.inspectionEvidenceState(props.session.id)).data.data;
  } catch {
    goal.value = null;
    evidence.value = null;
  } finally {
    loading.value = false;
  }
}

function openGoalDialog() {
  hypothesesInput.value = String(props.session.data.risk_hypotheses?.join("，") || "");
  dialog.value = true;
}

async function createGoal() {
  if (!requiredItems.value.length && !candidateItems.value.length) {
    ElMessage.warning("请先配置必检项目或动态候选项目");
    return;
  }
  loading.value = true;
  try {
    goal.value = (
      await supervisionApi.createInspectionGoal(props.session.id, {
        session_version: props.session.version,
        request_key: `goal:${props.session.id}:${props.session.version}`,
        plan_id: props.session.data.plan_id || undefined,
        risk_hypotheses: hypothesesInput.value
          .split(/[,，]/)
          .map((item) => item.trim())
          .filter(Boolean),
        required_items: requiredItems.value,
        candidate_items: candidateItems.value,
        success_criteria: { resolve_all_hypotheses: true },
        stop_policy: {
          rule_version: "adaptive-stop-v1",
          evidence_sufficiency_threshold: threshold.value,
          max_rounds: maxRounds.value,
          allow_early_stop: true,
          require_expert_approval: true,
        },
      })
    ).data.data;
    dialog.value = false;
    ElMessage.success("设备闭环目标已建立");
    await load();
  } finally {
    loading.value = false;
  }
}

async function proposeNextTest() {
  if (!evidence.value) return;
  latestDecision.value = (
    await supervisionApi.proposeNextTest(props.session.id, {
      evidence_state_id: evidence.value.id,
      request_key: `next:${props.session.id}:${evidence.value.round}`,
      rule_version: "next-test-v1",
    })
  ).data.data;
  ElMessage.success(
    latestDecision.value.kind === "goal_reached"
      ? "当前没有待执行检测项目"
      : "已生成下一项检测建议",
  );
}

async function proposeStop() {
  if (!evidence.value) return;
  latestDecision.value = (
    await supervisionApi.proposeStop(props.session.id, {
      evidence_state_id: evidence.value.id,
      request_key: `stop:${props.session.id}:${evidence.value.round}`,
      rule_version: "adaptive-stop-v1",
    })
  ).data.data;
  ElMessage.info(
    latestDecision.value.kind === "goal_reached"
      ? "已形成待审批的停止建议"
      : "当前尚不满足停止条件",
  );
}

async function reviewStop(decision: "approve" | "reject") {
  if (!latestDecision.value) return;
  const result = await ElMessageBox.prompt(
    decision === "approve" ? "说明允许提前停止的复核依据。" : "说明继续检测的原因。",
    decision === "approve" ? "批准停止建议" : "退回停止建议",
    {
      inputType: "textarea",
      inputValidator: (value: string) => Boolean(value?.trim()) || "请填写复核意见",
    },
  );
  latestDecision.value = (
    await supervisionApi.reviewStopDecision(props.session.id, latestDecision.value.id, {
      decision,
      comment: result.value,
    })
  ).data.data;
  ElMessage.success(decision === "approve" ? "停止建议已批准" : "停止建议已退回");
}

watch(() => props.session.id, load, { immediate: true });
</script>

<template>
  <section class="adaptive-panel" v-loading="loading" aria-labelledby="adaptive-title">
    <header>
      <div>
        <p>MODEL–DEVICE CLOSED LOOP</p>
        <h3 id="adaptive-title">设备闭环与证据状态</h3>
        <span>设备是否可信与产品是否异常分别判断，必检项未完成时禁止提前停止。</span>
      </div>
      <el-button
        v-if="canOperate && !goal"
        type="primary"
        :loading="loading"
        @click="openGoalDialog"
      >
        启用设备闭环
      </el-button>
    </header>

    <el-alert
      v-if="!goal"
      :closable="false"
      type="info"
      title="当前会话尚未建立自适应检测目标"
      description="建立目标后，系统才会根据设备回复持续更新证据并建议下一项检测。"
    />

    <template v-else>
      <div class="state-grid">
        <article>
          <span>设备可信状态</span>
          <strong>{{ deviceStatus }}</strong>
          <small>校准、能力、数据质量独立校验</small>
        </article>
        <article>
          <span>产品质量状态</span>
          <strong>{{ productStatus }}</strong>
          <small>不使用设备故障推高产品异常判断</small>
        </article>
        <article>
          <span>证据充分度</span>
          <strong>{{ sufficiencyPercent }}%</strong>
          <el-progress :percentage="sufficiencyPercent" :stroke-width="6" :show-text="false" />
        </article>
        <article>
          <span>当前检测轮次</span>
          <strong>{{ evidence?.round ?? 0 }}</strong>
          <small
            >必检 {{ goal.required_items.length }} · 候选 {{ goal.candidate_items.length }}</small
          >
        </article>
      </div>

      <div v-if="evidence?.unresolved_conflicts.length" class="conflict-list">
        <strong>未解决冲突</strong>
        <span>{{ evidence.unresolved_conflicts.join("；") }}</span>
      </div>

      <div v-if="latestDecision" class="decision-card">
        <span>最新决策</span>
        <strong>{{ latestDecision.kind }}</strong>
        <p v-if="latestDecision.payload.selected">
          建议项目：{{ (latestDecision.payload.selected as any).item?.item || "-" }} ·
          {{ (latestDecision.payload.selected as any).reason || "" }}
        </p>
        <div v-if="canReviewStop" class="decision-actions">
          <el-button size="small" type="primary" @click="reviewStop('approve')">批准停止</el-button>
          <el-button size="small" @click="reviewStop('reject')">继续检测</el-button>
        </div>
      </div>

      <div v-if="canOperate" class="panel-actions">
        <el-button type="primary" :loading="loading" @click="proposeNextTest"
          >建议下一项检测</el-button
        >
        <el-button :loading="loading" @click="proposeStop">评估停止条件</el-button>
      </div>
    </template>

    <el-dialog v-model="dialog" title="建立设备闭环目标" width="min(620px, 94vw)">
      <el-form label-position="top">
        <el-form-item label="待确认或排除的风险假设">
          <el-input
            v-model="hypothesesInput"
            type="textarea"
            :rows="3"
            placeholder="多个假设使用逗号分隔"
          />
        </el-form-item>
        <div class="goal-form-grid">
          <el-form-item label="证据充分度阈值">
            <el-input-number v-model="threshold" :min="0" :max="1" :step="0.05" />
          </el-form-item>
          <el-form-item label="最大检测轮次">
            <el-input-number v-model="maxRounds" :min="1" :max="1000" />
          </el-form-item>
        </div>
        <el-alert
          type="warning"
          :closable="false"
          :title="`必检 ${requiredItems.length} 项必须完成；候选 ${candidateItems.length} 项可按证据动态选择`"
        />
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="createGoal">确认建立</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.adaptive-panel {
  margin: 18px 0;
  overflow: hidden;
  border: 1px solid #e0d9f3;
  border-radius: 15px;
  background: linear-gradient(115deg, #f8f5ff, #fff 46%, #f2fbff);
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 20px 22px;
  border-bottom: 1px solid #e8e2f5;
}

header p {
  margin: 0 0 6px;
  color: #6d4bc3;
  font:
    700 10px/1 ui-monospace,
    SFMono-Regular,
    Menlo,
    monospace;
  letter-spacing: 0.12em;
}

header h3 {
  margin: 0;
  color: #24364b;
  font-size: 19px;
}

header span {
  display: block;
  margin-top: 7px;
  color: #71849a;
  font-size: 12px;
}

.adaptive-panel > :deep(.el-alert) {
  margin: 18px 22px 22px;
}

.state-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  padding: 18px 20px;
}

.state-grid article {
  min-height: 104px;
  padding: 12px 16px;
}

.state-grid article + article {
  border-left: 1px solid #e5e0f2;
}

.state-grid span,
.state-grid strong,
.state-grid small {
  display: block;
}

.state-grid span {
  color: #71849a;
  font-size: 11px;
}

.state-grid strong {
  margin: 10px 0 8px;
  color: #20354a;
  font-size: 22px;
}

.state-grid small {
  color: #8798aa;
  font-size: 11px;
  line-height: 1.5;
}

.conflict-list,
.decision-card {
  margin: 0 20px 14px;
  padding: 13px 15px;
  border: 1px solid #e4def2;
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.82);
  color: #52677d;
  font-size: 12px;
}

.conflict-list strong,
.decision-card > span {
  margin-right: 10px;
  color: #6d4bc3;
}

.decision-card p {
  margin: 7px 0 0;
}

.decision-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.panel-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 0 20px 20px;
}

.goal-form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

@media (max-width: 820px) {
  .state-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .state-grid article:nth-child(3) {
    border-top: 1px solid #e5e0f2;
    border-left: 0;
  }
  .state-grid article:nth-child(4) {
    border-top: 1px solid #e5e0f2;
  }
}

@media (max-width: 560px) {
  header {
    align-items: flex-start;
    flex-direction: column;
  }
  .state-grid,
  .goal-form-grid {
    grid-template-columns: 1fr;
  }
  .state-grid article + article,
  .state-grid article:nth-child(4) {
    border-top: 1px solid #e5e0f2;
    border-left: 0;
  }
  .panel-actions {
    flex-direction: column;
  }
  .panel-actions :deep(.el-button) {
    min-height: 44px;
    margin-left: 0;
  }
}
</style>
