import type { RagSpace } from "@/types/rag-space.types";

export interface RagSpaceActor {
  userId: string;
  orgId: string;
  role: string;
  canWrite: boolean;
}

// Match the API's owner check. Seeing a shared space is not permission to edit it.
export function canWriteRagSpace(space: RagSpace | null, actor: RagSpaceActor): boolean {
  if (!space || !actor.userId || !actor.orgId || !actor.canWrite || space.org_id !== actor.orgId) return false;
  return space.created_by === actor.userId;
}
