import type {
  Deployment,
  DeploymentResultSummaryRecord,
  Experiment,
  FineTuneRun,
  OfflineEvaluation,
  OfflineEvaluationResultSummaryRecord,
  OnlineValidation,
  OnlineValidationResultSummaryRecord,
  SummaryArtifactItem,
  SummaryHighlightItem,
  SummaryLogItem,
  SummaryMetricItem,
  TrainingArtifact,
  TrainingJob,
  TrainingResultSummaryRecord,
} from "@/types/algo-workspace.types";

type GenericRecord = Record<string, unknown>;

export interface ResourceSummaryViewModel {
  highlights: SummaryHighlightItem[];
  metrics: SummaryMetricItem[];
  artifacts: SummaryArtifactItem[];
  logs: SummaryLogItem[];
}

function isRecord(value: unknown): value is GenericRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function toMetricItems(metrics: GenericRecord, labels?: Record<string, string>): SummaryMetricItem[] {
  return Object.entries(metrics).map(([key, value]) => ({
    key,
    label: labels?.[key] || key,
    value,
  }));
}

function toArtifactItem(artifact: TrainingArtifact): SummaryArtifactItem {
  const metaEntries = Object.entries(artifact).filter(([key]) => !["name", "path", "type", "download_url"].includes(key));
  return {
    title: String(artifact.name || artifact.type || "未命名产物"),
    subtitle: artifact.type ? `类型：${artifact.type}` : undefined,
    type: artifact.type || null,
    path: typeof artifact.path === "string" ? artifact.path : null,
    link: typeof artifact.download_url === "string" ? artifact.download_url : null,
    meta: metaEntries.length ? Object.fromEntries(metaEntries) : null,
  };
}

function toLogItems(logs: unknown[]): SummaryLogItem[] {
  return logs.map((item) => {
    if (typeof item === "string") {
      return { text: item };
    }
    if (isRecord(item)) {
      return {
        text: String(item.text || item.message || JSON.stringify(item)),
        level: typeof item.level === "string" ? item.level : null,
        timestamp: typeof item.timestamp === "string" ? item.timestamp : null,
      };
    }
    return { text: String(item) };
  });
}

function compactValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return `${value.length} 项`;
  }
  if (isRecord(value)) {
    const pairs = Object.entries(value).slice(0, 3).map(([key, item]) => `${key}=${String(item)}`);
    return pairs.length ? pairs.join("，") : "{}";
  }
  return value;
}

export function buildTrainingSummaryViewModel(resource: TrainingJob | FineTuneRun | null | undefined): ResourceSummaryViewModel {
  const resultSummary = (resource?.result_summary || {}) as TrainingResultSummaryRecord;
  const summary = isRecord(resultSummary.summary) ? resultSummary.summary : {};
  const metrics = isRecord(resultSummary.metrics) ? resultSummary.metrics : {};
  const metricSummary = isRecord(metrics.summary) ? metrics.summary : {};
  const highlights: SummaryHighlightItem[] = [
    { label: "最佳验证精度", value: metricSummary.best_val_accuracy ?? "-" },
    { label: "最终训练损失", value: metricSummary.final_train_loss ?? "-" },
  ];
  if (summary.base_checkpoint) {
    highlights.push({ label: "基础检查点", value: summary.base_checkpoint });
  }
  if (summary.effective_hyperparameters) {
    highlights.push({
      label: "有效超参数",
      value: compactValue(summary.effective_hyperparameters),
      hint: JSON.stringify(summary.effective_hyperparameters),
    });
  }

  const detailMetrics = Object.entries(metrics)
    .filter(([key]) => key !== "summary")
    .reduce<GenericRecord>((acc, [key, value]) => {
      acc[key] = value;
      return acc;
    }, {});

  if (Object.keys(metricSummary).length) {
    Object.entries(metricSummary).forEach(([key, value]) => {
      if (!highlights.some((item) => item.label === key || item.value === value)) {
        detailMetrics[key] = value;
      }
    });
  }

  return {
    highlights,
    metrics: toMetricItems(detailMetrics),
    artifacts: Array.isArray(resultSummary.artifacts) ? resultSummary.artifacts.map(toArtifactItem) : [],
    logs: Array.isArray(resultSummary.logs) ? toLogItems(resultSummary.logs) : [],
  };
}

export function buildOfflineEvaluationSummaryViewModel(resource: OfflineEvaluation | null | undefined): ResourceSummaryViewModel {
  const resultSummary = (resource?.result_summary || {}) as OfflineEvaluationResultSummaryRecord;
  const metrics = isRecord(resultSummary.metrics) ? resultSummary.metrics : {};
  const highlights: SummaryHighlightItem[] = [
    { label: "准确率", value: metrics.accuracy ?? "-" },
    { label: "F1 分数", value: metrics.f1 ?? "-" },
    { label: "mAP", value: metrics.mAP ?? "-" },
    { label: "IoU", value: metrics.IoU ?? "-" },
    { label: "AR", value: metrics.AR ?? "-" },
    { label: "样本数", value: metrics.sample_count ?? "-" },
  ];

  return {
    highlights,
    metrics: toMetricItems(metrics, {
      accuracy: "准确率",
      f1: "F1 分数",
      mAP: "mAP",
      IoU: "IoU",
      AR: "AR",
      sample_count: "样本数",
    }),
    artifacts: Array.isArray(resultSummary.artifacts) ? resultSummary.artifacts.map(toArtifactItem) : [],
    logs: Array.isArray(resultSummary.logs) ? toLogItems(resultSummary.logs) : [],
  };
}

export function buildOnlineValidationSummaryViewModel(resource: OnlineValidation | null | undefined): ResourceSummaryViewModel {
  const resultSummary = (resource?.result_summary || {}) as OnlineValidationResultSummaryRecord;
  const metrics = isRecord(resultSummary.metrics) ? resultSummary.metrics : {};
  const highlights: SummaryHighlightItem[] = [
    { label: "通过率", value: metrics.shadow_pass_rate ?? "-", unit: typeof metrics.shadow_pass_rate === "number" ? "" : undefined },
    { label: "平均延迟", value: metrics.avg_latency_ms ?? "-", unit: "ms" },
    { label: "吞吐", value: metrics.throughput_qps ?? "-", unit: "qps" },
    { label: "回放数", value: metrics.replay_count ?? 0 },
    { label: "基线状态", value: metrics.baseline_runtime_status || "-" },
  ];
  return {
    highlights,
    metrics: toMetricItems(metrics, {
      shadow_pass_rate: "通过率",
      avg_latency_ms: "平均延迟",
      throughput_qps: "吞吐",
      replay_count: "回放数",
      baseline_runtime_status: "基线状态",
    }),
    artifacts: Array.isArray(resultSummary.artifacts) ? resultSummary.artifacts.map(toArtifactItem) : [],
    logs: Array.isArray(resultSummary.logs) ? toLogItems(resultSummary.logs) : [],
  };
}

export function buildDeploymentSummaryViewModel(resource: Deployment | null | undefined): ResourceSummaryViewModel {
  const resultSummary = (resource?.result_summary || {}) as DeploymentResultSummaryRecord;
  const runtimeRegistration = isRecord(resultSummary.runtime_registration) ? resultSummary.runtime_registration : {};
  const highlights: SummaryHighlightItem[] = [
    { label: "运行状态", value: runtimeRegistration.status || "-" },
    { label: "模型标识", value: runtimeRegistration.model_key || "-" },
    { label: "服务入口", value: runtimeRegistration.endpoint_placeholder || "-" },
    { label: "服务提供方", value: runtimeRegistration.provider || "-" },
  ];
  const metrics: SummaryMetricItem[] = toMetricItems(runtimeRegistration, {
    source_type: "来源类型",
    source_id: "来源资源",
    model_key: "模型标识",
    provider: "服务提供方",
    endpoint_placeholder: "服务入口",
    inference_config: "推理配置",
    status: "运行状态",
  });

  return {
    highlights,
    metrics,
    artifacts: Array.isArray(resultSummary.artifacts) ? resultSummary.artifacts.map(toArtifactItem) : [],
    logs: Array.isArray(resultSummary.logs) ? toLogItems(resultSummary.logs) : [],
  };
}

export function buildExperimentSummaryViewModel(resource: Experiment | null | undefined): ResourceSummaryViewModel {
  const resultSummary = isRecord(resource?.result_summary) ? resource?.result_summary : {};
  const metrics = isRecord(resultSummary.metrics) ? resultSummary.metrics : {};
  const artifacts = Array.isArray(resultSummary.artifacts) ? resultSummary.artifacts : [];
  const summary = isRecord(resultSummary.summary) ? resultSummary.summary : {};
  const highlights: SummaryHighlightItem[] = [
    { label: "训练任务数", value: metrics.training_jobs ?? 0 },
    { label: "微调任务数", value: metrics.fine_tunes ?? 0 },
    { label: "离线评测数", value: metrics.offline_evaluations ?? 0 },
    { label: "部署记录数", value: metrics.deployments ?? 0 },
  ];
  if (summary.status) {
    highlights.unshift({ label: "汇总状态", value: summary.status });
  }

  return {
    highlights,
    metrics: toMetricItems(metrics),
    artifacts: artifacts.map((item) => toArtifactItem(item as TrainingArtifact)),
    logs: Array.isArray(resultSummary.logs) ? toLogItems(resultSummary.logs) : [],
  };
}

export function summarizeMetrics(metrics: Record<string, unknown>, fields: Array<{ key: string; label: string }>): string {
  const pairs = fields
    .map(({ key, label }) => {
      const value = metrics[key];
      return value === undefined || value === null || value === "" ? null : `${label}: ${String(value)}`;
    })
    .filter(Boolean);
  return pairs.join(" / ");
}
