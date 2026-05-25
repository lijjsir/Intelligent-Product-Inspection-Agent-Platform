import { beforeEach, describe, expect, it, vi } from "vitest";
import { writeTextToClipboard } from "@/utils/clipboard";

describe("clipboard util", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("uses Clipboard API when available", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });

    await expect(writeTextToClipboard("hello")).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith("hello");
  });

  it("falls back to execCommand when Clipboard API fails", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const execCommand = vi.fn().mockReturnValue(true);
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: execCommand,
    });

    await expect(writeTextToClipboard("fallback")).resolves.toBe(true);
    expect(execCommand).toHaveBeenCalledWith("copy");
  });
});
