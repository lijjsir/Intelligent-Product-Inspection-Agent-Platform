export const admissionLabels: Record<string, string> = {
  pending: "待处理", parsing: "解析中", parsed: "解析完成", failed: "处理失败",
  needs_information: "待补充", disputed: "存在分歧", approved: "已核验", rejected: "已退回",
  unpublished: "未发布", publishing: "发布处理中", published: "已发布", suspended: "已暂停", withdrawn: "已撤回",
  needs_review: "待核对候选", no_candidates: "未识别明确要求", confirmed: "已确认", done: "已完成",
};
export function admissionLabel(value?: string) { return admissionLabels[value || ""] || value || "待处理"; }
export function metadataDifferences(a: Record<string, unknown>, b: Record<string, unknown>) {
  return [...new Set([...Object.keys(a), ...Object.keys(b)])].filter(key => JSON.stringify(a[key]) !== JSON.stringify(b[key]))
    .map(key => ({key, before: a[key], after: b[key]}));
}
