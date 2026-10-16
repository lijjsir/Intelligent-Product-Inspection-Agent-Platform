const labels: Record<string, string> = {
  pending: "待处理", queued: "排队中", running: "检测中", done: "已完成", failed: "检测失败",
  reviewing: "复核中", collecting: "采集中", awaiting_review: "待复核", cancelled: "已取消",
};

export function taskStatusLabel(status: string) {
  return labels[status] || status;
}
