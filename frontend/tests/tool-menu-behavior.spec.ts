import { describe, expect, it } from "vitest";

import {
  resolveMenuGroupLandingPath,
  toggleActiveMenuGroupTitle,
  type MenuGroup,
} from "@/composables/useMenu";

describe("tool menu group behavior", () => {
  const toolGroup: MenuGroup = {
    title: "Tool Management",
    items: [
      { title: "Overview", path: "/ops/tools" },
      { title: "Catalog", path: "/ops/tools/catalog" },
      { title: "Import", path: "/ops/tools/import" },
    ],
  };

  it("uses the first enabled child as the landing path when the group is clicked", () => {
    expect(resolveMenuGroupLandingPath(toolGroup)).toBe("/ops/tools");
  });

  it("keeps menu groups collapsed by default", () => {
    expect(toggleActiveMenuGroupTitle([], toolGroup.title)).toEqual(["Tool Management"]);
  });

  it("toggles an expanded parent group closed when clicked again", () => {
    expect(toggleActiveMenuGroupTitle(["Tool Management"], toolGroup.title)).toEqual([]);
  });
});
