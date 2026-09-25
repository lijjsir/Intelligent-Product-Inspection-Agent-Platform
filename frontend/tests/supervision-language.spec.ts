import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

const srcRoot = resolve(process.cwd(), "src");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(vue|ts)$/.test(name) && !name.endsWith(".spec.ts") ? [path] : [];
  });
}

describe("quality-supervision user-facing language", () => {
  it("does not expose proposal-document wording in frontend source", () => {
    const offenders = sourceFiles(srcRoot)
      .filter((path) => /申报/.test(readFileSync(path, "utf8")))
      .map((path) => relative(srcRoot, path));

    expect(offenders).toEqual([]);
  });
});
