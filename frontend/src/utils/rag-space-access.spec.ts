import { describe, expect, it } from "vitest";
import type { RagSpace } from "@/types/rag-space.types";
import { canWriteRagSpace } from "./rag-space-access";

const space = { id: "space-1", org_id: "org-1", created_by: "expert-1" } as RagSpace;
const expert = { userId: "expert-1", orgId: "org-1", role: "expert", canWrite: true };

describe("RAG space maintenance boundaries", () => {
  it("allows the owner to maintain their own documents", () => {
    expect(canWriteRagSpace(space, expert)).toBe(true);
  });
  it("keeps system and other users' visible spaces read-only for experts", () => {
    expect(canWriteRagSpace({ ...space, created_by: null }, expert)).toBe(false);
    expect(canWriteRagSpace({ ...space, created_by: "expert-2" }, expert)).toBe(false);
  });
  it("requires both write permission and the current organization", () => {
    expect(canWriteRagSpace(space, { ...expert, canWrite: false })).toBe(false);
    expect(canWriteRagSpace(space, { ...expert, orgId: "org-2" })).toBe(false);
    expect(canWriteRagSpace(space, { ...expert, userId: "" })).toBe(false);
    expect(canWriteRagSpace(null, expert)).toBe(false);
  });
  it("does not give administrators maintenance of private or system spaces", () => {
    const admin = { ...expert, userId: "admin-1", role: "admin" };
    expect(canWriteRagSpace({ ...space, created_by: null }, admin)).toBe(false);
    expect(canWriteRagSpace(space,admin)).toBe(false);
    expect(canWriteRagSpace({ ...space, org_id: "org-2" }, admin)).toBe(false);
  });
});
