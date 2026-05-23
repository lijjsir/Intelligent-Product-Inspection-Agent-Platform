import { describe, expect, it } from "vitest";
import { agentLabel } from "./chat-rendering";

describe("chat rendering helpers", () => {
  it("uses new route agent names without quality_chat fallback labels", () => {
    expect(agentLabel({ agent: "chat" })).toBe("ChatAgent");
    expect(agentLabel({ agent: "inspection_task" })).toBe("InspectionTaskAgent");
    expect(agentLabel({ agent: "quality_chat" })).toBe("");
  });
});
