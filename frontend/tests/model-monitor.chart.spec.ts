import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { describe, expect, it } from "vitest";

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(resolve(__dirname, "../src/views/ops/ModelMonitorView.vue"), "utf-8");

describe("model monitor chart switching", () => {
  it("replaces chart options so pie mode does not inherit cartesian axes", () => {
    const setOptionCalls = source.match(/mainChart\.setOption\(\{/g) ?? [];
    const replacingCalls = source.match(/\}, true\);/g) ?? [];

    expect(setOptionCalls).toHaveLength(3);
    expect(replacingCalls.length).toBeGreaterThanOrEqual(setOptionCalls.length);
  });

  it("does not show a duplicate call ranking tab", () => {
    expect(source).not.toContain("ranking");
    expect(source).not.toContain("调用排行");
  });
});
