import { describe, expect, it, vi } from "vitest";
import type { ExportJob } from "@/types/governance.types";
import { waitForReportExport } from "./wait-for-report-export";
const job = (status: ExportJob["status"], error?: string) =>
  ({ id: "fixed-export", status, error_message: error }) as ExportJob;
describe("report export progress", () => {
  it("reuses an in-flight export until its original job succeeds", async () => {
    const load = vi
      .fn()
      .mockResolvedValueOnce(job("running"))
      .mockResolvedValueOnce(job("success"));
    expect(
      (await waitForReportExport(job("pending"), load, { pause: async () => {} })).status,
    ).toBe("success");
    expect(load.mock.calls).toEqual([["fixed-export"], ["fixed-export"]]);
  });
  it("surfaces generation failure instead of downloading a failed job", async () => {
    await expect(waitForReportExport(job("failed", "原件已撤回"), vi.fn())).rejects.toThrow(
      "原件已撤回",
    );
  });
  it("bounds waiting and leaves an explicit pending message", async () => {
    const load = vi.fn().mockResolvedValue(job("running"));
    await expect(
      waitForReportExport(job("pending"), load, { attempts: 2, pause: async () => {} }),
    ).rejects.toThrow("仍在生成");
    expect(load).toHaveBeenCalledTimes(2);
  });
});
