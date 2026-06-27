import { describe, expect, it } from "vitest";

import { attachmentDisplayName, isImageAttachment } from "./attachments";

describe("attachment helpers", () => {
  it("detects image attachments from kind, mime type, content type, name, or url", () => {
    expect(isImageAttachment({ kind: "image", name: "asset.bin" })).toBe(true);
    expect(isImageAttachment({ content_type: "image/png", name: "asset" })).toBe(true);
    expect(isImageAttachment({ mime_type: "image/webp", file_name: "asset" })).toBe(true);
    expect(isImageAttachment({ name: "photo.JPG" })).toBe(true);
    expect(isImageAttachment({ url: "/api/v1/files/chat-attachments/x.svg?token=1" })).toBe(true);
    expect(isImageAttachment({ kind: "file", content_type: "application/pdf", name: "report.pdf" })).toBe(false);
  });

  it("uses file_name as the display name fallback", () => {
    expect(attachmentDisplayName({ file_name: "001.png" })).toBe("001.png");
    expect(attachmentDisplayName({})).toBe("附件");
  });
});
