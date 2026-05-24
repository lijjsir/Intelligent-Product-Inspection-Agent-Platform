<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import type { EChartsCoreOption } from "echarts/core";

import AlgoWorkspaceHero from "@/components/business/algo/AlgoWorkspaceHero.vue";
import { datasetApi } from "@/api/dataset.api";
import { useECharts } from "@/composables/useECharts";
import { useDatasetStore } from "@/stores/dataset.store";
import { useDatasetProcessingStore } from "@/stores/datasetProcessing.store";
import { ORG_ID_KEY, TOKEN_KEY, readStoredValue } from "@/utils/auth-session";
import type {
  AlignmentPair,
  DatasetExportFormat,
  DatasetProcessingStatus,
  DatasetProcessingSubgraph,
  DatasetProcessingSubgraphEdge,
  DatasetProcessingSubgraphNode,
  DatasetProcessingType,
  KnowledgeGraphEntity,
} from "@/types/algo-workspace.types";
import type { AsyncJob, DatasetSample, DatasetSampleType } from "@/types/dataset.types";
import { datasetModalityLabel, datasetSupportsSampleType } from "@/utils/dataset-modality";

const route = useRoute();
const router = useRouter();
const datasetStore = useDatasetStore();
const processingStore = useDatasetProcessingStore();
const { chartRef, setOption, resize } = useECharts();

const activeTab = ref("overview");
const datasetId = computed(() => String(route.params.id || ""));
const sampleFilters = reactive({ sample_type: "" as DatasetSampleType | "", keyword: "" });
const samplePage = ref(1);
const sampleSize = ref(12);
const sampleTotal = ref(0);
const zipFile = ref<File | null>(null);
const imageFiles = ref<File[]>([]);
const videoFiles = ref<File[]>([]);
const textSampleForm = reactive({
  sample_name: "",
  text_content: "",
});
const importLoading = ref(false);
const importPolling = ref(false);
const imageUploadLoading = ref(false);
const videoUploadLoading = ref(false);
const textUploadLoading = ref(false);
const latestImportJob = ref<AsyncJob | null>(null);
const previewVisible = ref(false);
const previewPayload = ref<DatasetSample | null>(null);
const kgSubgraph = ref<DatasetProcessingSubgraph>({ nodes: [], edges: [], stats: {} });
const graphLoading = ref(false);
const graphKeyword = ref("");
const graphEntityType = ref("");
const alignmentMinScore = ref<number | null>(null);
const alignmentOnlyConfirmed = ref(false);
const augmentationHistory = ref<any[]>([]);
const exportFormatOptions: Array<{ label: string; value: DatasetExportFormat }> = [
  { label: "VLM-JSON", value: "vlm-json" },
  { label: "COCO", value: "coco" },
  { label: "YOLO", value: "yolo" },
];

const kgForm = reactive({ name: "", entity_type: "Defect", description: "" });
const kgRelationForm = reactive({ source_entity_id: "", target_entity_id: "", relation_type: "RELATED_TO" });
const alignmentForm = reactive({ source_sample_id: "", target_sample_id: "", relation_type: "describes", similarity_score: 0.72 });
const exportConfig = reactive<{
  format: DatasetExportFormat;
  train_ratio: number;
  val_ratio: number;
  test_ratio: number;
  include_augmented: boolean;
  only_confirmed_alignment: boolean;
}>({
  format: "vlm-json",
  train_ratio: 0.7,
  val_ratio: 0.15,
  test_ratio: 0.15,
  include_augmented: true,
  only_confirmed_alignment: false,
});
const kgConfig = reactive({ entity_lexicon: "", relation_rules: "" });
const augmentationSelected = ref<string[]>([]);
const alignmentCandidateSource = ref("");
const alignmentCandidateTarget = ref("");
const alignmentSourceOptions = computed(() => sampleItems.value.filter((item) => item.sample_type === "image"));
const alignmentTargetOptions = computed(() => sampleItems.value.filter((item) => item.sample_type === "text"));

const sampleItems = computed(() => datasetStore.samples);
const dataset = computed(() => datasetStore.current);
const recentJobs = computed(() => dataset.value?.recent_jobs || []);
const processingCards = computed(() => [
  buildProcessingCard("知识图谱", processingStore.statusMap.kg),
  buildProcessingCard("跨媒体对齐", processingStore.statusMap.alignment),
  buildProcessingCard("数据增强", processingStore.statusMap.augmentation),
  buildProcessingCard("导出", processingStore.statusMap.export),
]);

const activeStatus = computed(() => processingStore.statusMap[tabToType(activeTab.value)]);
const activeResults = computed(() => processingStore.resultsMap[tabToType(activeTab.value)]);
const kgEntities = computed(() => processingStore.resultsMap.kg?.entities || []);
const kgRelations = computed(() => processingStore.resultsMap.kg?.relations || []);
const alignmentPairs = computed(() => {
  const rows = processingStore.resultsMap.alignment?.pairs || [];
  return rows.filter((row) => {
    if (alignmentOnlyConfirmed.value && row.confirmation_status !== "confirmed") return false;
    if (alignmentMinScore.value !== null && Number(row.similarity_score || 0) < alignmentMinScore.value) return false;
    return true;
  });
});
const augmentationProposals = computed(() => processingStore.resultsMap.augmentation?.proposals || []);
const exportArtifact = computed<Record<string, unknown>>(() => {
  const summary = processingStore.resultsMap.export?.summary || {};
  const summaryArtifact = ((summary as Record<string, unknown>).artifact as Record<string, unknown> | undefined) || {};
  const resultArtifact = processingStore.resultsMap.export?.artifact || {};
  return {
    ...summaryArtifact,
    ...resultArtifact,
  };
});
const supportedExportFormats = computed(() => {
  const allowed = new Set((dataset.value?.supported_export_formats || ["vlm-json", "coco", "yolo"]).map((item) => String(item).toLowerCase()));
  return exportFormatOptions.map((item) => ({ ...item, disabled: !allowed.has(item.value) }));
});
const exportArtifactFormat = computed(() => {
  const format = String(exportArtifact.value.format || "").trim().toLowerCase();
  if (format === "vlm-json" || format === "coco" || format === "yolo") return format;
  return exportConfig.format;
});
const exportDownloadLabel = computed(() => {
  if (exportArtifactFormat.value === "coco") return "下载 COCO 导出";
  if (exportArtifactFormat.value === "yolo") return "下载 YOLO 导出";
  return "下载 VLM-JSON 导出";
});
const degradedWarnings = computed(() => {
  return processingCards.value
    .filter((card) => card.degradedReason)
    .map((card) => `${card.label}：${card.degradedReason}`);
});

function buildProcessingCard(label: string, status: DatasetProcessingStatus | null) {
  const summary = (status?.summary || {}) as Record<string, unknown>;
  const summaryNode = (summary.summary || {}) as Record<string, unknown>;
  return {
    label,
    status: status?.resource?.status || "idle",
    progress: Number(status?.progress || summary.progress || 0),
    stats: (summary.current_stats || summaryNode.current_stats || {}) as Record<string, unknown>,
    warnings: (status?.warnings || summary.warnings || []) as string[],
    degradedReason: (summaryNode.degraded_reason as string | null) || null,
  };
}

function tabToType(tab: string): DatasetProcessingType {
  if (tab === "alignment" || tab === "augmentation" || tab === "export") return tab;
  return "kg";
}

function syncTabFromRoute() {
  activeTab.value = String(route.query.tab || "overview");
}

function formatBytes(value: number | null | undefined) {
  const size = Number(value || 0);
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function statusTagType(status?: string | null) {
  if (status === "completed") return "success";
  if (status === "running") return "warning";
  if (status === "failed") return "danger";
  if (status === "cancelled") return "info";
  if (status === "queued") return "primary";
  return "";
}

function parseOptionalJson(text: string) {
  const trimmed = text.trim();
  return trimmed ? JSON.parse(trimmed) : undefined;
}

function sampleTypeLabel(type?: DatasetSampleType | null) {
  if (type === "image") return "图片";
  if (type === "video") return "视频";
  return "文本";
}

function formatImportJobSummary(resultSummary: unknown) {
  if (!resultSummary || typeof resultSummary !== "object") return "-";
  const record = resultSummary as Record<string, unknown>;
  const createdSamples = record.created_samples;
  const imageSamples = record.image_samples;
  const videoSamples = record.video_samples;
  const textSidecars = record.text_sidecar_attached;
  const annotationSidecars = record.annotation_sidecar_attached;
  const skippedCount = record.skipped_files;
  const parts = [
    createdSamples !== undefined ? `已导入: ${createdSamples}` : null,
    imageSamples !== undefined ? `图片: ${imageSamples}` : null,
    videoSamples !== undefined ? `视频: ${videoSamples}` : null,
    textSidecars !== undefined ? `文本侧车: ${textSidecars}` : null,
    annotationSidecars !== undefined ? `标注侧车: ${annotationSidecars}` : null,
    skippedCount !== undefined ? `已跳过: ${skippedCount}` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" / ") : JSON.stringify(record);
}

function handleZipChange(event: Event) {
  const target = event.target as HTMLInputElement | null;
  zipFile.value = target?.files?.[0] || null;
}

function handleImageChange(event: Event) {
  const target = event.target as HTMLInputElement | null;
  imageFiles.value = Array.from(target?.files || []);
}

function handleVideoChange(event: Event) {
  const target = event.target as HTMLInputElement | null;
  videoFiles.value = Array.from(target?.files || []);
}

const canUploadImage = computed(() => datasetSupportsSampleType(dataset.value?.modality, "image"));
const canUploadVideo = computed(() => datasetSupportsSampleType(dataset.value?.modality, "video"));
const canUploadText = computed(() => datasetSupportsSampleType(dataset.value?.modality, "text"));

async function fetchDataset() {
  if (!datasetId.value) return;
  await datasetStore.fetchDataset(datasetId.value);
  const supported = new Set((datasetStore.current?.supported_export_formats || []).map((item) => String(item).toLowerCase()));
  if (supported.size && !supported.has(exportConfig.format)) {
    const fallback = exportFormatOptions.find((item) => supported.has(item.value));
    if (fallback) exportConfig.format = fallback.value;
  }
}

async function fetchSamples() {
  if (!datasetId.value) return;
  const result = await datasetStore.fetchSamples(datasetId.value, {
    page: samplePage.value,
    size: sampleSize.value,
    sample_type: sampleFilters.sample_type || undefined,
  });
  sampleTotal.value = result.total;
}

async function refreshProcessing(type: DatasetProcessingType) {
  if (!datasetId.value) return;
  await processingStore.refreshActive(datasetId.value, type);
}

async function refreshAll() {
  await Promise.all([
    fetchDataset(),
    fetchSamples(),
    refreshProcessing("kg"),
    refreshProcessing("alignment"),
    refreshProcessing("augmentation"),
    refreshProcessing("export"),
  ]);
}

function resolveDownloadFilename() {
  const objectKey = String(exportArtifact.value.object_key || "").trim();
  if (objectKey) {
    const parts = objectKey.split("/");
    const last = parts[parts.length - 1];
    if (last) return last;
  }
  if (exportArtifactFormat.value === "coco") return "annotations.coco.json";
  if (exportArtifactFormat.value === "yolo") return "labels.yolo.json";
  return "vlm.json";
}

async function downloadExportArtifact() {
  if (!datasetId.value) return;
  try {
    const apiBase = String(import.meta.env.VITE_API_BASE ?? "/api").trim().replace(/\/$/, "");
    const token = readStoredValue(TOKEN_KEY);
    const orgId = readStoredValue(ORG_ID_KEY);
    const response = await fetch(`${apiBase}/v1/datasets/${datasetId.value}/exports/download`, {
      method: "GET",
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(orgId ? { "X-Org-Id": orgId } : {}),
      },
    });
    if (!response.ok) {
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const payload = await response.json() as { message?: string };
        throw new Error(payload.message || "导出文件下载失败");
      }
      throw new Error((await response.text()) || "导出文件下载失败");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    const header = response.headers.get("content-disposition") || "";
    const matched = header.match(/filename="?([^";]+)"?/i);
    link.download = matched?.[1] || resolveDownloadFilename();
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    const message = error instanceof Error ? error.message : "导出文件下载失败";
    ElMessage.error(message);
  }
}

function pushTab(tab: string) {
  router.replace({ path: `/ops/data/import/${datasetId.value}`, query: { tab } });
}

async function startProcessing(type: DatasetProcessingType) {
  if (!datasetId.value) return;
  const payload = type === "export"
    ? {
        name: type,
        description: `${type} run`,
        ...exportConfig,
      }
    : {
        name: type,
        description: `${type} run`,
        config_json: type === "kg"
          ? {
              entity_lexicon: parseOptionalJson(kgConfig.entity_lexicon || "") || {},
              relation_rules: parseOptionalJson(kgConfig.relation_rules || "") || [],
            }
          : type === "alignment"
            ? {
                threshold: alignmentForm.similarity_score,
                top_k: 3,
                mutual_check: true,
              }
            : {},
      };
  await processingStore.startProcessing(datasetId.value, type, payload);
  await processingStore.pollUntilSettled(datasetId.value, type, 12);
  await refreshAll();
  if (type === "kg") {
    await loadKgSubgraph();
  }
  if (type === "augmentation") {
    await loadAugmentationHistory();
  }
}

async function submitZipUpload() {
  if (!datasetId.value || !zipFile.value) return;
  importLoading.value = true;
  latestImportJob.value = null;
  try {
    const chunkSize = 5 * 1024 * 1024;
    const totalChunks = Math.max(1, Math.ceil(zipFile.value.size / chunkSize));
    const init = await datasetApi.initUploadSession(datasetId.value, {
      file_name: zipFile.value.name,
      content_type: zipFile.value.type || "application/zip",
      file_size: zipFile.value.size,
      chunk_size: chunkSize,
      total_chunks: totalChunks,
    });
    const sessionId = init.data.data.session_id;
    for (let index = 0; index < totalChunks; index += 1) {
      const start = index * chunkSize;
      const end = Math.min(zipFile.value.size, start + chunkSize);
      await datasetApi.uploadPart(datasetId.value, sessionId, index + 1, zipFile.value.slice(start, end));
    }
    const complete = await datasetApi.completeUploadSession(datasetId.value, {
      session_id: sessionId,
      uploaded_parts: Array.from({ length: totalChunks }, (_, index) => index + 1),
    });
    latestImportJob.value = complete.data.data.job;
    ElMessage.success("导入任务已创建");
    await pollImportJob(complete.data.data.job.id);
    await refreshAll();
  } finally {
    importLoading.value = false;
  }
}

async function submitImageUpload() {
  if (!datasetId.value || !imageFiles.value.length) return;
  imageUploadLoading.value = true;
  try {
    await datasetStore.uploadImageSamples(datasetId.value, imageFiles.value);
    imageFiles.value = [];
    ElMessage.success("图片样本已上传");
    await refreshAll();
  } finally {
    imageUploadLoading.value = false;
  }
}

async function submitVideoUpload() {
  if (!datasetId.value || !videoFiles.value.length) return;
  videoUploadLoading.value = true;
  try {
    await datasetStore.uploadVideoSamples(datasetId.value, videoFiles.value);
    videoFiles.value = [];
    ElMessage.success("视频样本已上传");
    await refreshAll();
  } finally {
    videoUploadLoading.value = false;
  }
}

async function submitTextSample() {
  if (!datasetId.value) return;
  if (!textSampleForm.text_content.trim()) {
    ElMessage.warning("请填写文本内容");
    return;
  }
  textUploadLoading.value = true;
  try {
    await datasetStore.createTextSample(datasetId.value, {
      sample_name: textSampleForm.sample_name.trim() || undefined,
      text_content: textSampleForm.text_content.trim(),
    });
    textSampleForm.sample_name = "";
    textSampleForm.text_content = "";
    ElMessage.success("文本样本已添加");
    await refreshAll();
  } finally {
    textUploadLoading.value = false;
  }
}

async function pollImportJob(jobId: string) {
  if (!datasetId.value) return;
  importPolling.value = true;
  try {
    for (let index = 0; index < 20; index += 1) {
      const { data } = await datasetApi.getJob(datasetId.value, jobId);
      latestImportJob.value = data.data;
      if (["completed", "failed", "cancelled"].includes(data.data.status)) break;
      await new Promise((resolve) => window.setTimeout(resolve, 500));
    }
  } finally {
    importPolling.value = false;
  }
}

async function addKgEntity() {
  if (!datasetId.value || !kgForm.name.trim()) return;
  await processingStore.createKgEntity(datasetId.value, { ...kgForm, name: kgForm.name.trim(), description: kgForm.description.trim() || undefined });
  kgForm.name = "";
  kgForm.description = "";
  await loadKgSubgraph();
}

async function addKgRelation() {
  if (!datasetId.value || !kgRelationForm.source_entity_id || !kgRelationForm.target_entity_id) return;
  await processingStore.createKgRelation(datasetId.value, { ...kgRelationForm });
  await loadKgSubgraph();
}

async function addAlignmentPair() {
  if (!datasetId.value || !alignmentCandidateSource.value || !alignmentCandidateTarget.value) return;
  alignmentForm.source_sample_id = alignmentCandidateSource.value;
  alignmentForm.target_sample_id = alignmentCandidateTarget.value;
  await processingStore.createAlignmentPair(datasetId.value, { ...alignmentForm });
}

async function confirmAlignmentPair(pairId: string) {
  if (!datasetId.value) return;
  await processingStore.confirmAlignmentPair(datasetId.value, pairId);
}

async function deleteAlignmentPair(pairId: string) {
  if (!datasetId.value) return;
  await processingStore.removeAlignmentPair(datasetId.value, pairId);
}

async function applyAugmentation() {
  if (!datasetId.value || !augmentationSelected.value.length) return;
  await processingStore.applyAugmentation(datasetId.value, augmentationSelected.value);
  augmentationSelected.value = [];
  await fetchSamples();
  await loadAugmentationHistory();
  ElMessage.success("增强样本已生成");
}

function handleAugmentationSelection(rows: Array<{ id: string }>) {
  augmentationSelected.value = rows.map((row) => row.id);
}

async function loadAugmentationHistory() {
  if (!datasetId.value) return;
  const history = await processingStore.getAugmentationHistory(datasetId.value);
  augmentationHistory.value = history.history || [];
}

function buildGraphOption(subgraph: DatasetProcessingSubgraph): EChartsCoreOption {
  const typeColorMap: Record<string, string> = {
    Sample: "#2563eb",
    Defect: "#dc2626",
    Part: "#0f766e",
    Process: "#b45309",
    Attribute: "#7c3aed",
  };
  return {
    tooltip: {
      trigger: "item",
      formatter: (params: { data?: Record<string, unknown> }) => {
        const data = params.data || {};
        const title = String(data.name || "");
        const entityType = String(data.entity_type || data.relation_type || "");
        return `<div><strong>${title}</strong><br/>${entityType}</div>`;
      },
    },
    series: [
      {
        type: "graph",
        layout: "force",
        roam: true,
        draggable: true,
        force: { repulsion: 280, edgeLength: 120, gravity: 0.06 },
        label: { show: true, color: "#18181b", fontSize: 12 },
        lineStyle: { color: "#94a3b8", opacity: 0.8, width: 1.2 },
        edgeLabel: { show: true, formatter: "{c}", fontSize: 11, color: "#52525b" },
        data: subgraph.nodes.map((node) => ({
          ...node,
          symbolSize: Math.max(36, Math.min(72, node.value * 56)),
          itemStyle: { color: typeColorMap[node.entity_type] || "#475569" },
        })),
        links: subgraph.edges.map((edge) => ({
          source: edge.source,
          target: edge.target,
          value: edge.relation_type,
          lineStyle: { width: Math.max(1, edge.value * 2) },
        })),
      },
    ],
  };
}

async function loadKgSubgraph() {
  if (!datasetId.value) return;
  graphLoading.value = true;
  try {
    kgSubgraph.value = await processingStore.getKgSubgraph(datasetId.value, {
      entity_type: graphEntityType.value || undefined,
      keyword: graphKeyword.value.trim() || undefined,
    });
    await nextTick();
    setOption(buildGraphOption(kgSubgraph.value));
    resize();
  } finally {
    graphLoading.value = false;
  }
}

async function removeSample(row: DatasetSample) {
  if (!datasetId.value) return;
  await ElMessageBox.confirm(`删除样本「${row.sample_name || row.id}」？`, "删除样本", { type: "warning" });
  await datasetStore.removeSample(datasetId.value, row.id);
  await refreshAll();
}

function openPreview(row: DatasetSample) {
  previewPayload.value = row;
  previewVisible.value = true;
}

const filteredSamples = computed(() => {
  const keyword = sampleFilters.keyword.trim().toLowerCase();
  if (!keyword) return sampleItems.value;
  return sampleItems.value.filter((item) => {
    return [item.sample_name, item.preview_text, item.text_content]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(keyword));
  });
});

onMounted(async () => {
  syncTabFromRoute();
  await refreshAll();
  await loadKgSubgraph();
  await loadAugmentationHistory();
});

watch(
  () => route.query.tab,
  async () => {
    syncTabFromRoute();
    if (activeTab.value === "kg") {
      await loadKgSubgraph();
    }
  },
);

watch(activeTab, (value) => {
  pushTab(value);
});
</script>

<template>
  <div class="workspace-detail">
    <AlgoWorkspaceHero
      :title="dataset?.name || '数据接入工作台'"
      :description="dataset?.description || '围绕一个数据集完成接入、图谱、对齐、增强与导出。'"
      back-path="/ops/data/import"
      show-back
    >
      <template #aside>
        <div class="hero-meta">
          <el-tag effect="plain">{{ datasetModalityLabel(dataset?.modality) }}</el-tag>
          <el-tag :type="statusTagType(dataset?.status)" effect="light">{{ dataset?.status || "-" }}</el-tag>
          <div class="hero-bytes">{{ formatBytes(dataset?.uploaded_bytes) }}</div>
        </div>
      </template>
    </AlgoWorkspaceHero>

    <section class="metric-strip">
      <article class="metric-card">
        <span>样本总量</span>
        <strong>{{ dataset?.sample_count || 0 }}</strong>
      </article>
      <article class="metric-card">
        <span>图片样本</span>
        <strong>{{ dataset?.image_sample_count || 0 }}</strong>
      </article>
      <article class="metric-card">
        <span>视频样本</span>
        <strong>{{ dataset?.video_sample_count || 0 }}</strong>
      </article>
      <article class="metric-card">
        <span>文本样本</span>
        <strong>{{ dataset?.text_sample_count || 0 }}</strong>
      </article>
      <article class="metric-card">
        <span>最近导入</span>
        <strong>{{ latestImportJob?.status || recentJobs[0]?.status || "暂无" }}</strong>
      </article>
    </section>

    <section v-if="degradedWarnings.length" class="warning-strip">
      <el-alert
        v-for="warning in degradedWarnings"
        :key="warning"
        :title="warning"
        type="warning"
        :closable="false"
        show-icon
      />
    </section>

    <section class="card-surface tab-shell">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="概览" name="overview" />
        <el-tab-pane label="样本管理" name="samples" />
        <el-tab-pane label="知识图谱" name="kg" />
        <el-tab-pane label="跨媒体对齐" name="alignment" />
        <el-tab-pane label="数据增强" name="augmentation" />
        <el-tab-pane label="导出" name="export" />
      </el-tabs>
    </section>

    <section v-if="activeTab === 'overview'" class="overview-grid">
      <article class="card-surface panel">
        <div class="panel-head">
          <h3>处理状态</h3>
        </div>
        <div class="processing-grid">
          <div v-for="card in processingCards" :key="card.label" class="processing-card">
            <div class="processing-top">
              <span>{{ card.label }}</span>
              <el-tag :type="statusTagType(card.status)" effect="light">{{ card.status }}</el-tag>
            </div>
            <el-progress :percentage="card.progress" :stroke-width="10" />
            <div class="processing-stats">
              <span v-for="(value, key) in card.stats" :key="String(key)">{{ key }}: {{ value }}</span>
            </div>
          </div>
        </div>
      </article>

      <article class="card-surface panel">
        <div class="panel-head">
          <h3>最近任务</h3>
        </div>
        <el-table :data="recentJobs" empty-text="暂无任务">
          <el-table-column prop="job_type" label="任务" min-width="150" />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" effect="light">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" min-width="180" />
        </el-table>
      </article>

      <article class="card-surface panel">
        <div class="panel-head">
          <h3>导出产物</h3>
        </div>
        <el-empty v-if="!Object.keys(exportArtifact).length" description="暂无导出产物" />
        <div v-else class="artifact-panel">
          <div><span>格式</span><strong>{{ exportArtifactFormat || "-" }}</strong></div>
          <div><span>文件大小</span><strong>{{ formatBytes(Number(exportArtifact.file_size_bytes || 0)) }}</strong></div>
          <div><span>对象路径</span><strong class="mono">{{ exportArtifact.object_key || "-" }}</strong></div>
          <button v-if="exportArtifact.download_url" type="button" class="artifact-link artifact-button" @click="downloadExportArtifact">{{ exportDownloadLabel }}</button>
        </div>
      </article>
    </section>

    <section v-else-if="activeTab === 'samples'" class="samples-grid">
      <article class="card-surface panel">
        <div class="panel-head">
          <h3>ZIP 导入</h3>
          <span class="hint">支持图片/视频批量包，并识别同名 .txt / .json 侧车</span>
        </div>
        <input type="file" accept=".zip" @change="handleZipChange" />
        <div class="action-row">
          <el-button type="primary" :loading="importLoading || importPolling" @click="submitZipUpload">上传并导入</el-button>
          <el-button @click="fetchSamples">刷新样本</el-button>
        </div>
        <div v-if="latestImportJob" class="job-panel">
          <div><span>任务 ID</span><strong class="mono">{{ latestImportJob.id }}</strong></div>
          <div><span>状态</span><strong>{{ latestImportJob.status }}</strong></div>
          <div><span>摘要</span><strong>{{ formatImportJobSummary(latestImportJob.result_summary) }}</strong></div>
        </div>
      </article>

      <article v-if="canUploadImage" class="card-surface panel">
        <div class="panel-head">
          <h3>图片直传</h3>
          <span class="hint">支持 PNG、JPG、JPEG、WEBP、GIF、BMP</span>
        </div>
        <input type="file" accept="image/*,.png,.jpg,.jpeg,.webp,.gif,.bmp" multiple @change="handleImageChange" />
        <div class="action-row">
          <el-button type="primary" :loading="imageUploadLoading" @click="submitImageUpload">上传图片</el-button>
          <span class="hint" v-if="imageFiles.length">已选择 {{ imageFiles.length }} 个文件</span>
        </div>
      </article>

      <article v-if="canUploadVideo" class="card-surface panel">
        <div class="panel-head">
          <h3>视频上传</h3>
          <span class="hint">支持 MP4、MOV、AVI、MKV、WEBM、M4V</span>
        </div>
        <input type="file" accept="video/*,.mp4,.mov,.avi,.mkv,.webm,.m4v" multiple @change="handleVideoChange" />
        <div class="action-row">
          <el-button type="primary" :loading="videoUploadLoading" @click="submitVideoUpload">上传视频</el-button>
          <span class="hint" v-if="videoFiles.length">已选择 {{ videoFiles.length }} 个文件</span>
        </div>
      </article>

      <article v-if="canUploadText" class="card-surface panel">
        <div class="panel-head">
          <h3>文本直录</h3>
          <span class="hint">适合投诉描述、检验备注、标注文本等快速录入</span>
        </div>
        <el-form label-position="top">
          <el-form-item label="样本名称">
            <el-input v-model="textSampleForm.sample_name" placeholder="可选，例如：case-001.txt" />
          </el-form-item>
          <el-form-item label="文本内容">
            <el-input v-model="textSampleForm.text_content" type="textarea" :rows="6" placeholder="输入文本样本内容" />
          </el-form-item>
          <div class="action-row">
            <el-button type="primary" :loading="textUploadLoading" @click="submitTextSample">添加文本</el-button>
          </div>
        </el-form>
      </article>

      <article class="card-surface panel">
        <div class="panel-head">
          <h3>样本列表</h3>
          <span class="hint">共 {{ sampleTotal }} 条</span>
        </div>
        <div class="filter-row">
          <el-input v-model="sampleFilters.keyword" clearable placeholder="搜索样本名或预览" />
          <el-select v-model="sampleFilters.sample_type" clearable placeholder="全部样本" @change="fetchSamples">
            <el-option label="图片" value="image" />
            <el-option label="视频" value="video" />
            <el-option label="文本" value="text" />
          </el-select>
        </div>
        <el-table :data="filteredSamples" v-loading="datasetStore.sampleLoading" empty-text="暂无样本">
          <el-table-column prop="sample_name" label="样本" min-width="170" />
          <el-table-column label="类型" width="96">
            <template #default="{ row }">{{ sampleTypeLabel(row.sample_type) }}</template>
          </el-table-column>
          <el-table-column prop="preview_text" label="预览" min-width="260" />
          <el-table-column label="增强" width="92">
            <template #default="{ row }">
              <el-tag v-if="row.is_augmented" type="warning" effect="light">增强</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140">
            <template #default="{ row }">
              <el-button link @click="openPreview(row)">预览</el-button>
              <el-button link type="danger" @click="removeSample(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </article>
    </section>

    <section v-else-if="activeTab === 'kg'" class="kg-grid">
      <article class="card-surface panel graph-panel">
        <div class="panel-head">
          <h3>知识图谱子图</h3>
          <div class="action-row compact">
            <el-input v-model="graphKeyword" clearable placeholder="关键词过滤" class="graph-filter" />
            <el-select v-model="graphEntityType" clearable placeholder="实体类型" class="graph-filter">
              <el-option label="Defect" value="Defect" />
              <el-option label="Part" value="Part" />
              <el-option label="Process" value="Process" />
              <el-option label="Attribute" value="Attribute" />
            </el-select>
            <el-button @click="loadKgSubgraph">刷新子图</el-button>
            <el-button type="primary" @click="startProcessing('kg')">启动构建</el-button>
          </div>
        </div>
        <div ref="chartRef" class="graph-canvas" v-loading="graphLoading" />
        <div class="subgraph-stats">
          <span v-for="(value, key) in kgSubgraph.stats" :key="String(key)">{{ key }}: {{ value }}</span>
        </div>
      </article>

      <article class="card-surface panel">
        <div class="panel-head">
          <h3>人工维护</h3>
        </div>
        <el-form label-position="top">
          <el-form-item label="实体名">
            <el-input v-model="kgForm.name" />
          </el-form-item>
          <el-form-item label="实体类型">
            <el-input v-model="kgForm.entity_type" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="kgForm.description" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item label="扩展词典(JSON)">
            <el-input v-model="kgConfig.entity_lexicon" type="textarea" :rows="2" placeholder='{"Defect":["划痕"]}' />
          </el-form-item>
          <el-form-item label="关系规则(JSON)">
            <el-input v-model="kgConfig.relation_rules" type="textarea" :rows="2" placeholder='[{"source":"Part","target":"Defect","relation":"HAS_DEFECT"}]' />
          </el-form-item>
          <el-button type="primary" @click="startProcessing('kg')">启动构建</el-button>
          <el-button @click="loadKgSubgraph">刷新子图</el-button>
          <el-button type="primary" plain @click="addKgEntity">新增实体</el-button>
        </el-form>
        <el-divider />
        <el-form label-position="top">
          <el-form-item label="源实体">
            <el-select v-model="kgRelationForm.source_entity_id" placeholder="选择源实体">
              <el-option v-for="item in kgEntities" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="目标实体">
            <el-select v-model="kgRelationForm.target_entity_id" placeholder="选择目标实体">
              <el-option v-for="item in kgEntities" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="关系类型">
            <el-input v-model="kgRelationForm.relation_type" />
          </el-form-item>
          <el-button type="primary" @click="addKgRelation">新增关系</el-button>
        </el-form>
        <el-divider />
        <div class="entity-list">
          <div v-for="item in kgEntities.slice(0, 8)" :key="item.id" class="entity-item">
            <strong>{{ item.name }}</strong>
            <span>{{ item.entity_type }}</span>
          </div>
        </div>
      </article>
    </section>

    <section v-else-if="activeTab === 'alignment'" class="card-surface panel">
      <div class="panel-head">
        <h3>跨媒体对齐</h3>
        <div class="action-row compact">
          <el-input-number v-model="alignmentMinScore" :min="0" :max="1" :step="0.05" placeholder="最小分数" />
          <el-switch v-model="alignmentOnlyConfirmed" active-text="仅确认项" />
          <el-button @click="startProcessing('alignment')">启动自动对齐</el-button>
        </div>
      </div>
      <div class="manual-add">
          <el-select v-model="alignmentCandidateSource" placeholder="选择图片样本">
            <el-option v-for="item in alignmentSourceOptions" :key="item.id" :label="item.sample_name || item.id" :value="item.id" />
          </el-select>
          <el-select v-model="alignmentCandidateTarget" placeholder="选择文本样本">
            <el-option v-for="item in alignmentTargetOptions" :key="item.id" :label="item.sample_name || item.id" :value="item.id" />
          </el-select>
          <el-input-number v-model="alignmentForm.similarity_score" :min="0" :max="1" :step="0.01" />
          <el-button type="primary" @click="addAlignmentPair">手工新增</el-button>
        </div>
        <el-table :data="alignmentPairs" empty-text="暂无对齐结果">
          <el-table-column prop="source_sample_id" label="图片样本" min-width="170" />
          <el-table-column prop="target_sample_id" label="文本样本" min-width="170" />
          <el-table-column prop="similarity_score" label="分数" width="100" />
          <el-table-column label="方式" width="120">
            <template #default="{ row }">{{ row.payload_json?.alignment_method || '-' }}</template>
          </el-table-column>
          <el-table-column prop="confirmation_status" label="状态" width="120" />
          <el-table-column label="操作" width="140">
            <template #default="{ row }">
            <el-button v-if="row.confirmation_status !== 'confirmed'" link type="primary" @click="confirmAlignmentPair(row.id)">确认</el-button>
            <el-button link type="danger" @click="deleteAlignmentPair(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section v-else-if="activeTab === 'augmentation'" class="augmentation-grid">
      <article class="card-surface panel">
        <div class="panel-head">
          <h3>增强建议</h3>
          <div class="action-row compact">
            <el-button @click="loadAugmentationHistory">刷新历史</el-button>
            <el-button type="primary" @click="startProcessing('augmentation')">生成建议</el-button>
            <el-button type="success" :disabled="!augmentationSelected.length" @click="applyAugmentation">应用选中</el-button>
          </div>
        </div>
        <el-table :data="augmentationProposals" row-key="id" @selection-change="handleAugmentationSelection">
          <el-table-column type="selection" width="48" />
          <el-table-column prop="name" label="名称" min-width="200" />
          <el-table-column prop="augmentation_method" label="方法" width="160" />
          <el-table-column prop="description" label="生成文本" min-width="260" />
          <el-table-column label="应用结果" width="180">
            <template #default="{ row }">
              {{ row.created_sample_id || (row.created_sample_ids || []).join(", ") || "-" }}
            </template>
          </el-table-column>
        </el-table>
      </article>

      <article class="card-surface panel">
        <div class="panel-head">
          <h3>增强历史</h3>
        </div>
        <el-empty v-if="!augmentationHistory.length" description="暂无历史" />
        <div v-else class="history-list">
          <div v-for="(item, index) in augmentationHistory" :key="index" class="history-item">
            <strong>{{ item.name || item.id }}</strong>
            <span>{{ item.augmentation_method || "-" }}</span>
            <span>{{ item.created_sample_id || (item.created_sample_ids || []).join(", ") || "-" }}</span>
          </div>
        </div>
      </article>
    </section>

    <section v-else class="export-grid">
      <article class="card-surface panel">
        <div class="panel-head">
          <h3>导出配置</h3>
        </div>
        <label class="export-format">
          <span>导出格式</span>
          <el-select v-model="exportConfig.format">
            <el-option
              v-for="item in supportedExportFormats"
              :key="item.value"
              :label="item.label"
              :value="item.value"
              :disabled="item.disabled"
            />
          </el-select>
        </label>
        <div class="ratio-grid">
          <label>
            <span>Train</span>
            <el-input-number v-model="exportConfig.train_ratio" :min="0" :max="1" :step="0.05" />
          </label>
          <label>
            <span>Val</span>
            <el-input-number v-model="exportConfig.val_ratio" :min="0" :max="1" :step="0.05" />
          </label>
          <label>
            <span>Test</span>
            <el-input-number v-model="exportConfig.test_ratio" :min="0" :max="1" :step="0.05" />
          </label>
        </div>
        <div class="switch-list">
          <el-switch v-model="exportConfig.include_augmented" active-text="包含增强样本" />
          <el-switch v-model="exportConfig.only_confirmed_alignment" active-text="仅确认对齐" />
        </div>
        <el-button class="mt-4" type="primary" @click="startProcessing('export')">创建导出</el-button>
      </article>

      <article class="card-surface panel">
        <div class="panel-head">
          <h3>导出产物</h3>
        </div>
        <el-empty v-if="!Object.keys(exportArtifact).length" description="暂无导出结果" />
        <div v-else class="artifact-panel">
          <div><span>格式</span><strong>{{ exportArtifactFormat || "-" }}</strong></div>
          <div><span>路径</span><strong class="mono">{{ exportArtifact.object_key || "-" }}</strong></div>
          <div><span>文件大小</span><strong>{{ formatBytes(Number(exportArtifact.file_size_bytes || 0)) }}</strong></div>
          <div><span>切分统计</span><strong class="mono">{{ JSON.stringify(exportArtifact.split_counts || {}) }}</strong></div>
          <button v-if="exportArtifact.download_url" type="button" class="artifact-link artifact-button" @click="downloadExportArtifact">{{ exportDownloadLabel }}</button>
        </div>
      </article>
    </section>

    <el-dialog v-model="previewVisible" title="样本预览" width="720px">
      <template v-if="previewPayload">
        <div class="preview-dialog">
          <div class="preview-meta">
            <div><span>样本名</span><strong>{{ previewPayload.sample_name || previewPayload.id }}</strong></div>
            <div><span>类型</span><strong>{{ sampleTypeLabel(previewPayload.sample_type) }}</strong></div>
            <div><span>大小</span><strong>{{ formatBytes(previewPayload.size_bytes) }}</strong></div>
          </div>
          <video
            v-if="previewPayload.sample_type === 'video' && previewPayload.download_url"
            class="preview-video"
            :src="previewPayload.download_url"
            controls
          />
          <pre class="preview-code">{{ JSON.stringify(previewPayload, null, 2) }}</pre>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.workspace-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hero-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}

.hero-bytes {
  color: #0f766e;
  font-weight: 600;
}

.preview-video {
  width: 100%;
  max-height: 360px;
  border-radius: 16px;
  background: #000;
}

.metric-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.metric-card {
  padding: 16px 18px;
  background: #fff;
  border: 1px solid #e4e4e7;
  border-radius: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.metric-card span {
  color: #71717a;
  font-size: 13px;
}

.metric-card strong {
  color: #18181b;
  font-size: 26px;
}

.warning-strip {
  display: grid;
  gap: 8px;
}

.tab-shell {
  padding: 6px 18px 0;
}

.overview-grid,
.samples-grid,
.kg-grid,
.augmentation-grid,
.export-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.panel {
  padding: 18px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.panel-head h3 {
  margin: 0;
  font-size: 17px;
  color: #18181b;
}

.hint {
  color: #71717a;
  font-size: 12px;
}

.processing-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.processing-card {
  border: 1px solid #e4e4e7;
  border-radius: 16px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.processing-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.processing-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: #52525b;
  font-size: 12px;
}

.artifact-panel,
.job-panel {
  display: grid;
  gap: 12px;
}

.artifact-panel > div,
.job-panel > div,
.preview-meta > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.artifact-panel span,
.job-panel span,
.preview-meta span {
  color: #71717a;
}

.artifact-link {
  color: #2563eb;
  font-weight: 600;
}

.artifact-button {
  border: 0;
  background: transparent;
  padding: 0;
  cursor: pointer;
  text-align: left;
  align-self: flex-start;
}

.filter-row,
.action-row,
.manual-add {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.action-row.compact {
  gap: 8px;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  word-break: break-all;
}

.graph-panel {
  grid-column: span 1;
}

.graph-canvas {
  height: 420px;
  border: 1px solid #e4e4e7;
  border-radius: 16px;
  background: linear-gradient(180deg, #fcfcfd 0%, #f8fafc 100%);
}

.subgraph-stats {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: #52525b;
  font-size: 12px;
}

.graph-filter {
  width: 160px;
}

.entity-list,
.history-list {
  display: grid;
  gap: 10px;
}

.entity-item,
.history-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid #f4f4f5;
  padding-bottom: 10px;
}

.ratio-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.export-format {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 16px;
  color: #52525b;
  font-size: 13px;
}

.ratio-grid label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #52525b;
  font-size: 13px;
}

.switch-list {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.preview-dialog {
  display: grid;
  gap: 14px;
}

.preview-meta {
  display: grid;
  gap: 8px;
}

.preview-code {
  margin: 0;
  padding: 16px;
  border-radius: 16px;
  background: #111827;
  color: #e5eef9;
  overflow: auto;
  font-size: 12px;
}

@media (max-width: 1024px) {
  .metric-strip,
  .overview-grid,
  .samples-grid,
  .kg-grid,
  .augmentation-grid,
  .export-grid,
  .processing-grid {
    grid-template-columns: 1fr;
  }

  .hero-meta {
    align-items: flex-start;
  }
}
</style>
