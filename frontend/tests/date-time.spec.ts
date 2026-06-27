import { describe, expect, it } from "vitest";
import { formatServerDateTime, parseServerDateTime } from "@/utils/date-time";

describe("server date time", () => {
  it("treats timezone-less server timestamps as UTC", () => {
    const parsed = parseServerDateTime("2026-06-25T20:29:20.305000");

    expect(parsed?.toISOString()).toBe("2026-06-25T20:29:20.305Z");
  });

  it("formats UTC timestamps in the browser local timezone", () => {
    const parsed = new Date("2026-06-25T20:29:20.305Z");
    const pad2 = (value: number) => String(value).padStart(2, "0");
    const formatted = formatServerDateTime(
      "2026-06-25T20:29:20.305000",
      { includeSeconds: true },
    );
    const expected =
      `${parsed.getFullYear()}-${pad2(parsed.getMonth() + 1)}-${pad2(parsed.getDate())} ` +
      `${pad2(parsed.getHours())}:${pad2(parsed.getMinutes())}:${pad2(parsed.getSeconds())}`;

    expect(formatted).toBe(expected);
  });
});
