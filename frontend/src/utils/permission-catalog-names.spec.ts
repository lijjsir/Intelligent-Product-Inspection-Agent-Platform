import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { ADMIN_MENU_GROUPS } from "./admin-workspace";

describe("permission names follow current administrator navigation", () => {
  const catalog = readFileSync(
    resolve(process.cwd(), "../backend/app/core/permission_catalog.py"),
    "utf8",
  );
  const menu = ADMIN_MENU_GROUPS.flatMap((group) => group.items);
  for (const [key, path] of [
    ["product_master_read", "/governance/admin/quality-products"],
    ["inspection_standard_library_read", "/governance/admin/inspection-standards"],
    ["inspection_spec_read", "/governance/admin/ai-review-gates"],
    ["role_read", "/governance/admin/roles-orgs"],
    ["memory_governance", "/governance/memory"],
  ]) {
    it(`${key} matches its current menu title`, () => {
      const title = menu.find((item) => item.path === path)?.title;
      expect(title).toBeTruthy();
      const match = catalog.match(new RegExp(`"${key}"\\s*:\\s*\\("[^"]+",\\s*"([^"]+)"`));
      expect(match?.[1]).toBe(title);
    });
  }
  it("does not expose retired labels as permission names", () => {
    expect(catalog).not.toContain('"产品主数据"');
    expect(catalog).not.toContain('"检验规范"');
    expect(catalog).not.toContain('"检验标准库"');
  });
});
