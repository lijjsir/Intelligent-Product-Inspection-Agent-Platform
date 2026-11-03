<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import AlgoWorkspaceHero from "@/components/business/algo/AlgoWorkspaceHero.vue";
import { useModelConfigStore } from "@/stores/model_config.store";
import { useAuthStore } from "@/stores/auth.store";
import { modelConfigApi } from "@/api/model_config.api";
import type { ModelConfigPayload, ModelType } from "@/types/governance.types";
import type { ModelCapability, ModelCapabilityResult, ModelConfig } from "@/types/governance.types";

const store = useModelConfigStore();
const auth = useAuthStore();
const canManage = computed(() => auth.effectivePermissions === null || auth.hasPermission("model_config"));
const drawerOpen = ref(false);
const editingId = ref("");
const checkingAll = ref(false);
const editingHasApiKey = ref(false);
const isLocalProvider = computed(() => form.provider.trim().toLowerCase() === "local_openai");
const verificationOpen = ref(false);
const verificationModel = ref<ModelConfig | null>(null);
const verifying = ref(false);
const verificationResults = ref<ModelCapabilityResult[]>([]);
const selectedCapabilities = ref<ModelCapability[]>([]);
const capabilityOptions: { value: ModelCapability; label: string }[] = [
  { value: "text", label: "文字生成" }, { value: "json", label: "JSON 输出" },
  { value: "vision", label: "图片理解" }, { value: "tools", label: "工具调用" },
  { value: "embedding", label: "向量生成" },
];
const availableCapabilities = computed(() => capabilityOptions.filter(item =>
  verificationModel.value?.model_type === 'embedding' ? item.value === 'embedding'
    : item.value !== 'embedding' && (verificationModel.value?.model_type === 'multimodal' || item.value !== 'vision'),
));
const providerOptions = [
  { value: "local_openai", label: "本地 OpenAI 兼容服务（Ollama / vLLM）" },
  { value: "volcengine", label: "火山引擎" }, { value: "deepseek", label: "DeepSeek" },
];
const form = reactive({
  provider: "volcengine",
  model_key: "",
  display_name: "",
  source_type: "external",
  source_uri: "",
  endpoint: "",
  api_key: "",
  model_type: "chat",
  fine_tune_command_template: "",
  offline_eval_command_template: "",
  deployment_command_template: "",
  runtime_env_json: "{\"workdir\":\"/tmp/piap-gpu-jobs\",\"artifact_root\":\"/tmp/piap-gpu-jobs/artifacts\",\"env\":{}}",
  default_gpu_request: 1,
  default_cpu_request: 8,
  default_memory_gb: 32,
  priority: 100,
  rpm_limit: 60,
  input_price_per_million: 0,
  output_price_per_million: 0,
  is_active: true,
});

const modelTypeOptions = [
  { label: "文字对话", value: "chat" },
  { label: "向量生成", value: "embedding" },
  { label: "多模态（文字与图片）", value: "multimodal" },
];

const sourceTypeOptions = [
  { label: "external", value: "external" },
  { label: "local", value: "local" },
];

function resetForm() {
  editingId.value = "";
  editingHasApiKey.value = false;
  Object.assign(form, {
    provider: "volcengine",
    model_key: "",
    display_name: "",
    source_type: "external",
    source_uri: "",
    endpoint: "",
    api_key: "",
    model_type: "chat",
    fine_tune_command_template: "",
    offline_eval_command_template: "",
    deployment_command_template: "",
    runtime_env_json: "{\"workdir\":\"/tmp/piap-gpu-jobs\",\"artifact_root\":\"/tmp/piap-gpu-jobs/artifacts\",\"env\":{}}",
    default_gpu_request: 1,
    default_cpu_request: 8,
    default_memory_gb: 32,
    priority: 100,
    rpm_limit: 60,
    input_price_per_million: 0,
    output_price_per_million: 0,
    is_active: true,
  });
}

function openCreate() {
  resetForm();
  drawerOpen.value = true;
}

function openEdit(row: any) {
  editingId.value = row.id;
  editingHasApiKey.value = Boolean(row.has_api_key);
  Object.assign(form, {
    provider: row.provider,
    model_key: row.model_key,
    display_name: row.display_name,
    source_type: row.source_type,
    source_uri: row.source_uri,
    endpoint: row.endpoint,
    api_key: "",
    model_type: row.model_type,
    fine_tune_command_template: row.fine_tune_command_template || "",
    offline_eval_command_template: row.offline_eval_command_template || "",
    deployment_command_template: row.deployment_command_template || "",
    runtime_env_json: JSON.stringify(row.runtime_env_json || { workdir: "/tmp/piap-gpu-jobs", artifact_root: "/tmp/piap-gpu-jobs/artifacts", env: {} }, null, 2),
    default_gpu_request: row.default_gpu_request ?? 1,
    default_cpu_request: row.default_cpu_request ?? 8,
    default_memory_gb: row.default_memory_gb ?? 32,
    priority: row.priority,
    rpm_limit: row.rpm_limit ?? 60,
    input_price_per_million: row.input_price_per_million ?? 0,
    output_price_per_million: row.output_price_per_million ?? 0,
    is_active: row.is_active,
  });
  drawerOpen.value = true;
}

const isEditing = computed(() => Boolean(editingId.value));
const apiKeyHint = computed(() => {
  if (isLocalProvider.value) return "本地服务未启用鉴权时可留空；启用鉴权时填写该服务的 Key。编辑时留空保留已有 Key。";
  if (!isEditing.value) return "创建后不会回显明文 API Key，请妥善保管。";
  return editingHasApiKey.value
    ? "已配置 API Key；留空表示保持不变，输入新值表示覆盖。"
    : "尚未配置 API Key；留空表示不设置。";
});

function openVerification(row: ModelConfig) {
  verificationModel.value = row;
  verificationResults.value = [];
  selectedCapabilities.value = row.model_type === "embedding" ? ["embedding"]
    : row.model_type === "multimodal" ? ["text", "json", "vision", "tools"] : ["text", "json", "tools"];
  verificationOpen.value = true;
}

async function verifyModel() {
  if (!verificationModel.value || !selectedCapabilities.value.length || verifying.value) return;
  verifying.value = true;
  verificationResults.value = [];
  try {
    const { data } = await modelConfigApi.verify(verificationModel.value.id, selectedCapabilities.value);
    verificationResults.value = data.data.results;
    await store.fetchAll();
  } catch (e: any) {
    ElMessage.error(e?.message || "能力验证失败");
  } finally {
    verifying.value = false;
  }
}

function capabilityLabel(value: string) {
  return capabilityOptions.find((item) => item.value === value)?.label || value;
}

function verificationStatus(value: string) {
  return ({ healthy: "通过", unhealthy: "未通过", degraded: "暂不可用", unsupported: "接口未接受" } as Record<string, string>)[value] || value;
}

async function submit() {
  let runtimeEnvJson: Record<string, unknown> | null = null;
  try {
    runtimeEnvJson = form.runtime_env_json ? JSON.parse(form.runtime_env_json) : null;
  } catch {
    ElMessage.error("运行时环境 JSON 解析失败");
    return;
  }
  const provider = form.provider.trim();
  const modelKey = form.model_key.trim();
  const displayName = form.display_name.trim();
  const sourceUri = form.source_uri.trim();
  const endpoint = form.endpoint.trim();
  if (!displayName || !sourceUri || !endpoint) {
    ElMessage.error("请填写完整的展示名称、来源地址和接口地址");
    return;
  }
  if (!editingId.value && (!provider || !modelKey)) {
    ElMessage.error("新增模型时必须填写提供方和模型标识");
    return;
  }
  const payload: Record<string, unknown> = {
    provider,
    display_name: displayName,
    source_type: form.source_type,
    source_uri: sourceUri,
    endpoint,
    model_type: form.model_type,
    fine_tune_command_template: form.fine_tune_command_template || null,
    offline_eval_command_template: form.offline_eval_command_template || null,
    deployment_command_template: form.deployment_command_template || null,
    runtime_env_json: runtimeEnvJson,
    default_gpu_request: form.default_gpu_request || null,
    default_cpu_request: form.default_cpu_request || null,
    default_memory_gb: form.default_memory_gb || null,
    priority: form.priority,
    rpm_limit: form.rpm_limit,
    input_price_per_million: form.input_price_per_million,
    output_price_per_million: form.output_price_per_million,
    is_active: form.is_active,
  };
  if (editingId.value) {
    if (form.api_key) {
      payload.api_key = form.api_key;
    }
    await store.updateOne(editingId.value, payload);
    ElMessage.success("模型配置已更新");
  } else {
    payload.model_key = modelKey;
    payload.api_key = form.api_key || undefined;
    const created = await store.createOne(payload as unknown as ModelConfigPayload);
    ElMessage.success("模型配置已创建");
    try {
      await store.checkHealth(created.id);
    } catch { /* health check is best-effort */ }
  }
  drawerOpen.value = false;
}

async function remove(id: string) {
  try {
    await ElMessageBox.confirm("确定要删除此模型配置吗？", "确认删除", {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      type: "warning",
    });
    await store.removeOne(id);
    ElMessage.success("模型配置已删除");
  } catch {
    // user cancelled
  }
}

async function checkAll() {
  checkingAll.value = true;
  try {
    const result = await store.checkHealthAll();
    const message = `检测完成: ${result.checked} 个模型, ${result.healthy} 健康, ${result.degraded} 降级, ${result.unhealthy} 异常`;
    if (result.unhealthy > 0) {
      ElMessage.warning(message);
    } else {
      ElMessage.success(message);
    }
  } catch (e: any) {
    ElMessage.error(e?.message || "批量健康检查失败");
  } finally {
    checkingAll.value = false;
  }
}

function healthTagType(status: string) {
  if (status === "healthy") return "success";
  if (status === "degraded") return "warning";
  if (status === "unhealthy") return "danger";
  return "info";
}

onMounted(() => {
  store.fetchAll();
});
</script>

<template>
  <div class="flex flex-col gap-5">
    <AlgoWorkspaceHero title="Base Model 注册" description="管理本地或外部模型接口、验证调用能力，并配置训练与部署模板。">
      <template #actions>
        <div class="flex gap-3">
          <el-button v-if="canManage" @click="checkAll" :loading="checkingAll">全部验证</el-button>
          <el-button v-if="canManage" type="primary" @click="openCreate">新增 Base Model</el-button>
        </div>
      </template>
    </AlgoWorkspaceHero>

    <el-card shadow="never">
      <el-table :data="store.items" v-loading="store.loading">
        <el-table-column prop="display_name" label="名称" min-width="150" />
        <el-table-column prop="model_key" label="模型标识" min-width="150" />
        <el-table-column label="来源" min-width="220">
          <template #default="{ row }">{{ row.source_type }} / {{ row.source_uri }}</template>
        </el-table-column>
        <el-table-column prop="provider" label="提供方" width="110" />
        <el-table-column label="GPU 模板" width="110">
          <template #default="{ row }">
            <el-tag :type="row.fine_tune_command_template || row.offline_eval_command_template || row.deployment_command_template ? 'success' : 'info'">
              {{ row.fine_tune_command_template || row.offline_eval_command_template || row.deployment_command_template ? "已配置" : "未配置" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="80" />
        <el-table-column label="输入单价" width="110">
          <template #default="{ row }">￥{{ Number(row.input_price_per_million || 0).toFixed(2) }}/1M</template>
        </el-table-column>
        <el-table-column label="输出单价" width="110">
          <template #default="{ row }">￥{{ Number(row.output_price_per_million || 0).toFixed(2) }}/1M</template>
        </el-table-column>
        <el-table-column label="健康状态" width="150">
          <template #default="{ row }">
            <el-tooltip :content="row.health_message || '暂无详情'" :disabled="!row.health_message">
              <el-tag :type="healthTagType(row.health_status)">
                {{ row.health_status }}
              </el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="70">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? "是" : "否" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="290" fixed="right">
          <template #default="{ row }">
            <el-button v-if="canManage" link type="primary" @click="openVerification(row)" :disabled="verifying">能力验证</el-button>
            <el-button v-if="canManage" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canManage" link type="danger" @click="remove(row.id)">删除</el-button>
            <span v-if="!canManage" class="text-xs text-zinc-400">仅可查看</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-drawer v-model="drawerOpen" :title="editingId ? '编辑 Base Model' : '新增 Base Model'" size="500px">
      <el-form label-position="top">
        <el-form-item label="提供方">
          <el-select v-model="form.provider" filterable allow-create default-first-option placeholder="选择或输入提供方">
            <el-option v-for="item in providerOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型标识">
          <el-input v-model="form.model_key" :disabled="isEditing" />
          <div v-if="isEditing" class="field-hint">模型标识不可修改；提供方可以修正。如需变更模型标识，请新建配置。</div>
        </el-form-item>
        <el-form-item label="展示名称"><el-input v-model="form.display_name" /></el-form-item>
        <el-form-item label="来源类型">
          <el-select v-model="form.source_type" placeholder="选择来源类型">
            <el-option v-for="item in sourceTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源地址">
          <el-input v-model="form.source_uri" placeholder="HuggingFace/ModelScope ID 或本地路径" />
        </el-form-item>
        <el-form-item label="接口地址">
          <el-input v-model="form.endpoint" :placeholder="isLocalProvider ? 'http://host.docker.internal:11434/v1' : 'https://服务地址/v1'" />
          <div v-if="isLocalProvider" class="field-hint">填写 OpenAI 兼容接口的基础地址，以 /v1 结尾。服务在同一宿主机时可使用上面的地址；服务在其他机器时填写其 IP。模型标识需与服务实际提供的名称一致。</div>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.api_key" type="password" show-password />
          <div class="field-hint">{{ apiKeyHint }}</div>
        </el-form-item>
        <el-form-item label="模型类型">
          <el-select v-model="form.model_type" placeholder="选择模型类型">
            <el-option v-for="item in modelTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-divider content-position="left">GPU 作业模板</el-divider>
        <el-form-item label="微调命令模板">
          <el-input v-model="form.fine_tune_command_template" type="textarea" :rows="4" placeholder="python finetune.py --dataset {dataset_id} --eval-set {eval_set_id} --output {artifact_output_dir} --gpus {gpu_indices}" />
        </el-form-item>
        <el-form-item label="离线评测命令模板">
          <el-input v-model="form.offline_eval_command_template" type="textarea" :rows="4" placeholder="python evaluate.py --eval-set {eval_set_id} --output {artifact_output_dir} --gpus {gpu_indices}" />
        </el-form-item>
        <el-form-item label="部署命令模板">
          <el-input v-model="form.deployment_command_template" type="textarea" :rows="4" placeholder="python serve.py --model {model_config_id} --output {artifact_output_dir} --port 8000 --gpus {gpu_indices}" />
        </el-form-item>
        <el-form-item label="运行时环境 JSON">
          <el-input v-model="form.runtime_env_json" type="textarea" :rows="6" />
        </el-form-item>
        <el-form-item label="默认 GPU 数"><el-input-number v-model="form.default_gpu_request" :min="1" :max="64" /></el-form-item>
        <el-form-item label="默认 CPU 数"><el-input-number v-model="form.default_cpu_request" :min="1" :max="1024" /></el-form-item>
        <el-form-item label="默认内存 GB"><el-input-number v-model="form.default_memory_gb" :min="1" :max="8192" /></el-form-item>
        <el-form-item label="优先级"><el-input-number v-model="form.priority" :min="1" :max="9999" /></el-form-item>
        <el-form-item label="RPM 限制"><el-input-number v-model="form.rpm_limit" :min="1" :max="100000" /></el-form-item>
        <el-form-item label="输入单价（元 / 1M tokens）">
          <el-input-number v-model="form.input_price_per_million" :min="0" :step="0.1" :precision="4" />
        </el-form-item>
        <el-form-item label="输出单价（元 / 1M tokens）">
          <el-input-number v-model="form.output_price_per_million" :min="0" :step="0.1" :precision="4" />
        </el-form-item>
        <el-form-item><el-switch v-model="form.is_active" active-text="启用" inactive-text="停用" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="drawerOpen = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-drawer>

    <el-dialog v-model="verificationOpen" title="模型能力验证" width="min(760px, 95vw)" :close-on-click-modal="!verifying" :close-on-press-escape="!verifying" :show-close="!verifying">
      <p class="mb-3">{{ verificationModel?.display_name }} · {{ verificationModel?.model_key }}</p>
      <p class="field-hint mb-3">发送少量测试文字和内置测试图片，检查接口及返回格式；不会执行业务工具或修改向量索引。验证结果不代表业务准确率。首次加载模型可能需要较长时间。</p>
      <el-checkbox-group v-model="selectedCapabilities" :disabled="verifying">
        <el-checkbox v-for="item in availableCapabilities" :key="item.value" :value="item.value">{{ item.label }}</el-checkbox>
      </el-checkbox-group>
      <el-table :data="verificationResults" class="mt-4" v-loading="verifying" element-loading-text="正在调用模型，请等待验证完成">
        <el-table-column label="能力" width="100"><template #default="{ row }">{{ capabilityLabel(row.capability) }}</template></el-table-column>
        <el-table-column label="结果" width="110"><template #default="{ row }"><el-tag :type="row.status === 'healthy' ? 'success' : row.status === 'unhealthy' ? 'danger' : 'warning'">{{ verificationStatus(row.status) }}</el-tag></template></el-table-column>
        <el-table-column prop="message" label="详情" min-width="240" />
        <el-table-column label="耗时" width="90"><template #default="{ row }">{{ row.latency_ms }} ms</template></el-table-column>
      </el-table>
      <template #footer>
        <el-button :disabled="verifying" @click="verificationOpen = false">关闭</el-button>
        <el-button type="primary" :loading="verifying" :disabled="!selectedCapabilities.length" @click="verifyModel">开始验证</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
:deep(.el-drawer__body) {
  overflow-y: auto;
}

.field-hint {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
}
</style>
