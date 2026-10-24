import { describe, expect, it } from "vitest";
import type { SupervisionRecord } from "@/types/supervision.types";
import {
  sessionItemCount,
  sessionMissingConfiguration,
  sessionStatusLabel,
} from "@/utils/laboratory-session";

const session = (data: Record<string, unknown>, status = "active") =>
  ({ id: "batch", kind: "inspection-sessions", status, data }) as SupervisionRecord;
describe("laboratory preparation and execution labels", () => {
  it("shows incomplete measurement setup instead of calling an active record ready", () => {
    const record = session({
      task_id: "task",
      input_mode: "measurement",
      sample_ids: ["sample"],
      device_ids: [],
      test_items: [],
    });
    expect(sessionStatusLabel(record)).toBe("待准备");
    expect(sessionMissingConfiguration(record)).toEqual(["关联检测设备", "配置检测项目"]);
  });
  it("recognizes adaptive required and candidate items", () => {
    const record = session({
      task_id: "task",
      input_mode: "measurement",
      sample_ids: ["sample"],
      device_ids: ["device"],
      adaptive_enabled: true,
      required_items: [{ item: "required" }],
      candidate_items: [{ item: "candidate" }],
      test_items: [],
    });
    expect(sessionItemCount(record)).toBe(2);
    expect(sessionMissingConfiguration(record)).toEqual([]);
  });
  it("does not require a measuring device for image input", () => {
    const record = session({
      task_id: "task",
      input_mode: "image",
      sample_ids: ["sample"],
      test_items: [],
    });
    expect(sessionMissingConfiguration(record)).toEqual([]);
  });
  it("identifies missing tasks and input mode and preserves confirmed status", () => {
    expect(sessionMissingConfiguration(session({}))).toEqual([
      "关联检测任务",
      "登记样品",
      "选择输入方式",
      "配置检测项目",
    ]);
    expect(sessionStatusLabel(session({}, "signed"))).toBe("已确认");
  });
});
