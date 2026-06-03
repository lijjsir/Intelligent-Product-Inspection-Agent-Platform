import { describe, expect, it } from "vitest";

import { parseServerDateTime } from "./date-time";

describe("parseServerDateTime", () => {
  it("treats server timestamps without timezone as UTC", () => {
    const parsed = parseServerDateTime("2026-06-02T10:03:55");

    expect(parsed?.getTime()).toBe(Date.parse("2026-06-02T10:03:55Z"));
  });

  it("preserves explicit timezone offsets", () => {
    const parsed = parseServerDateTime("2026-06-02T18:03:55+08:00");

    expect(parsed?.getTime()).toBe(Date.parse("2026-06-02T10:03:55Z"));
  });
});
