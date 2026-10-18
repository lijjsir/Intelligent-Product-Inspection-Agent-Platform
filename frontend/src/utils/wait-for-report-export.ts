import type { ExportJob } from "@/types/governance.types";

export class ReportExportError extends Error {}

export async function waitForReportExport(
  initial: ExportJob,
  load: (id: string) => Promise<ExportJob>,
  options: { attempts?: number; pause?: () => Promise<void> } = {},
): Promise<ExportJob> {
  let job = initial;
  const pause = options.pause || (() => new Promise<void>((resolve) => setTimeout(resolve, 500)));
  const deadline = Date.now() + 30000;
  for (let i = 0; ; i++) {
    if (job.status === "success") return job;
    if (!["pending", "running"].includes(job.status))
      throw new ReportExportError(job.error_message || "导出失败，请重新生成报告文件");
    if (i >= (options.attempts ?? 60) || Date.now() >= deadline)
      throw new ReportExportError("报告仍在生成，请稍后重试；系统会复用同一导出记录");
    await pause();
    job = await load(job.id);
  }
}
