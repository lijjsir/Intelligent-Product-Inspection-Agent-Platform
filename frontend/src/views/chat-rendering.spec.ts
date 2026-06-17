import { describe, expect, it } from "vitest";
import { agentLabel, isImageAttachment } from "./chat-rendering";

describe("chat rendering helpers", () => {
  it("uses new route agent names without quality_chat fallback labels", () => {
    expect(agentLabel({ agent: "chat" })).toBe("ChatAgent");
    expect(agentLabel({ agent: "inspection_task" })).toBe("InspectionTaskAgent");
    expect(agentLabel({ agent: "quality_chat" })).toBe("");
  });

  it("recognizes image attachments from kind, content type, name, or url", () => {
    expect(isImageAttachment({ kind: "image", content_type: null, name: "upload.bin", url: "/files/upload.bin" })).toBe(true);
    expect(isImageAttachment({ kind: "file", content_type: "image/png", name: "upload.bin", url: "/files/upload.bin" })).toBe(true);
    expect(isImageAttachment({ kind: "file", content_type: null, name: "001.png", url: "/files/raw" })).toBe(true);
    expect(isImageAttachment({ kind: "file", content_type: null, name: "raw", url: "/files/raw.webp?token=1" })).toBe(true);
    expect(isImageAttachment({ kind: "file", content_type: null, name: "report.pdf", url: "/files/report.pdf" })).toBe(false);
  });
});
