import { STATUS_LABELS, type SupervisionRecord } from "@/types/supervision.types";

export function sessionItemCount(session: SupervisionRecord): number {
  const data = session.data;
  const items = data.adaptive_enabled
    ? [...(data.required_items || []), ...(data.candidate_items || [])]
    : data.test_items || [];
  return items.length;
}

export function sessionMissingConfiguration(session: SupervisionRecord): string[] {
  const missing: string[] = [];
  if (!session.data.task_id) missing.push("关联检测任务");
  if (!session.data.sample_ids?.length) missing.push("登记样品");
  if (!session.data.input_mode) missing.push("选择输入方式");
  if (
    ["measurement", "mixed"].includes(session.data.input_mode) &&
    !session.data.device_ids?.length
  )
    missing.push("关联检测设备");
  if (session.data.input_mode !== "image" && sessionItemCount(session) === 0)
    missing.push("配置检测项目");
  return missing;
}

export function sessionStatusLabel(session: SupervisionRecord): string {
  if (["active", "draft"].includes(session.status)) return "待准备";
  if (session.status === "signed") return "已确认";
  return STATUS_LABELS[session.status] || session.status;
}
