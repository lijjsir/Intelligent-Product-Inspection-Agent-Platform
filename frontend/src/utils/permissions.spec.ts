import { describe, expect, it } from "vitest";
import {
  groupPermissionFeatures,
  resolvePermissions,
  sameOverrides,
  samePermissions,
  rolePermissionCatalog,
  personalPermissionToggle,
  permissionDifference,
  personalGrantOptions,
} from "./permissions";
import { permissionsForRoute, ordinaryUserTaskRedirect } from "./permission-routes";
import { groupUsersByRole } from "./permissions";
import type { User } from "@/types/user.types";

describe("permission matrix calculations", () => {
  it("offers extra grants without any prior denial and separates recovery from fixing inherited rights", () => {
    const catalog = rolePermissionCatalog(
      [
        { key: "read", name: "模型配置", group: "algorithm", action: "查看" },
        { key: "manage", name: "模型配置", group: "algorithm", action: "管理" },
        { key: "report", name: "报告", group: "inspection", action: "下载" },
        { key: "user", name: "用户管理", group: "organization", action: "管理" },
      ],
      ["read", "manage", "report"],
    );
    const defaults = ["read", "report"];
    const options = personalGrantOptions(catalog, defaults, {});
    expect(options.extra.map((action) => action.key)).toEqual(["manage"]);
    expect(options.restore).toEqual([]);
    expect(options.fixed.map((action) => action.key)).toEqual(["read", "report"]);
    const withPersonalChanges = personalGrantOptions(catalog, defaults, {
      report: "deny",
      manage: "grant",
    });
    expect(withPersonalChanges.extra).toEqual([]);
    expect(withPersonalChanges.restore.map((action) => action.key)).toEqual(["report"]);
    expect(withPersonalChanges.fixed.map((action) => action.key)).toEqual(["read"]);
    expect(defaults).toEqual(["read", "report"]);
  });
  it("personal grants and revocations change executable permissions and remain explicit after role changes", () => {
    const before = ["model_config_read"];
    const granted = personalPermissionToggle({}, "model_config", true);
    expect(granted).toEqual({ model_config: "grant" });
    const after = resolvePermissions(before, granted);
    expect(permissionDifference(before, after)).toEqual({ granted: ["model_config"], revoked: [] });
    const denied = personalPermissionToggle(granted, "model_config", false);
    expect(denied).toEqual({ model_config: "deny" });
    expect(resolvePermissions(["model_config_read", "model_config"], denied)).toEqual([
      "model_config_read",
    ]);
    expect(permissionDifference(after, resolvePermissions(before, denied))).toEqual({
      granted: [],
      revoked: ["model_config"],
    });
    expect(resolvePermissions(["model_config_read", "model_config"], {})).toContain("model_config");
  });
  it("does not display report rights as executable while required business access is missing", () => {
    const dependencies = {
      report_read: ["task", "result"],
      report_generate: ["task", "result", "report_read"],
    };
    expect(
      resolvePermissions(
        ["task", "result", "report_read", "report_generate"],
        { result: "deny" },
        dependencies,
      ),
    ).toEqual(["task"]);
    expect(
      resolvePermissions(
        ["task", "result", "report_read", "report_generate"],
        { report_generate: "deny", feedback: "deny" },
        dependencies,
      ),
    ).toEqual(["report_read", "result", "task"]);
  });
  it("hides out-of-role actions without losing eligible permissions that are currently unchecked", () => {
    const catalog = [
      { key: "user", name: "用户管理", group: "organization", action: "管理" },
      { key: "inspection_spec_read", name: "检验规范", group: "knowledge", action: "查看" },
      { key: "inspection_spec", name: "检验规范", group: "knowledge", action: "管理" },
      { key: "task", name: "检测任务", group: "inspection", action: "使用" },
    ];
    const visible = rolePermissionCatalog(catalog, ["task", "inspection_spec_read"]);
    expect(visible.map((action) => action.key)).toEqual(["inspection_spec_read", "task"]);
    expect(visible.some((action) => action.group === "organization")).toBe(false);
    expect(
      groupPermissionFeatures(visible)
        .find((feature) => feature.name === "检验规范")
        ?.actions.map((action) => action.action),
    ).toEqual(["查看"]);
    expect(catalog).toHaveLength(4);
    expect(rolePermissionCatalog(catalog, [])).toEqual([]);
  });
  it("routes ordinary-user result lists and old report links into the personal task flow", () => {
    expect(ordinaryUserTaskRedirect("/app/results")).toBeUndefined();
    expect(ordinaryUserTaskRedirect("/app/results/task-1")).toBeUndefined();
    expect(ordinaryUserTaskRedirect("/app/export", "task-1")).toBe("/app/results/task-1");
    expect(ordinaryUserTaskRedirect("/governance/admin/inspection-standards")).toBe("/app/tasks");
  });
  it("groups mixed users in identity order with natural name sorting and full-role counts", () => {
    const users = [
      { id: "u10", username: "user10", role: "user" },
      { id: "e2", username: "expert2", role: "expert" },
      { id: "u2", username: "user2", role: "user" },
    ] as User[];
    const roles = [
      { key: "expert", label: "专家" },
      { key: "user", label: "用户" },
      { key: "algorithm_engineer", label: "算法工程师" },
    ];
    const counts = { expert: 4, user: 12, algorithm_engineer: 3 };
    const groups = groupUsersByRole(users, roles, counts);
    expect(groups.map((group) => group.key)).toEqual(["expert", "user", "algorithm_engineer"]);
    expect(groups[1].users.map((user) => user.username)).toEqual(["user2", "user10"]);
    expect(groups[1].count).toBe(12);
    expect(groups[2].users).toEqual([]);
    expect(groupUsersByRole(users, roles, counts, "expert").map((group) => group.key)).toEqual([
      "expert",
    ]);
  });
  it("keeps default, extra grants and explicit denials separate", () => {
    const defaults = ["model_config_read", "model_config"];
    const overrides = { model_config: "deny", dataset: "grant" } as const;
    expect(resolvePermissions(defaults, overrides)).toEqual(["dataset", "model_config_read"]);
    expect(defaults).toEqual(["model_config_read", "model_config"]);
    expect(resolvePermissions(defaults, {})).toEqual(["model_config", "model_config_read"]);
  });

  it("keeps explicit denial when role defaults subsequently grant a permission", () => {
    expect(resolvePermissions([], { dataset: "deny" })).toEqual([]);
    expect(resolvePermissions(["dataset"], { dataset: "deny" })).toEqual([]);
  });

  it("groups multiple actions into one feature without merging modules", () => {
    const grouped = groupPermissionFeatures([
      { key: "model_config_read", name: "模型配置", group: "algorithm", action: "查看" },
      { key: "model_config", name: "模型配置", group: "algorithm", action: "管理" },
      { key: "other", name: "模型配置", group: "other", action: "使用" },
    ]);
    expect(grouped).toHaveLength(2);
    expect(grouped[0].actions.map((action) => action.key)).toEqual([
      "model_config_read",
      "model_config",
    ]);
  });

  it("detects changes independent of selection or JSON key order", () => {
    expect(samePermissions(["dataset", "chat"], ["chat", "dataset"])).toBe(true);
    expect(samePermissions([], ["chat"])).toBe(false);
    expect(
      sameOverrides({ dataset: "deny", chat: "grant" }, { chat: "grant", dataset: "deny" }),
    ).toBe(true);
    expect(sameOverrides({ dataset: "deny" }, {})).toBe(false);
  });

  it("uses read permissions for page access and matches details and query strings", () => {
    expect(permissionsForRoute("/ops/models/config")).toEqual(["model_config_read"]);
    expect(permissionsForRoute("/ops/data/import/a?tab=samples")).toEqual(["dataset"]);
    expect(permissionsForRoute("/app/profile")).toBeUndefined();
  });
});
