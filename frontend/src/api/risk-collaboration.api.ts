import { http } from "./http";
import type { RiskCollaboration } from "@/types/risk-collaboration.types";
const quiet = { suppressErrorToast: true };
export const riskCollaborationApi = {
  participants: () =>
    http.get<Array<{ id: string; name: string }>>("/v1/risk-collaborations/participants", quiet),
  list: (caseId: string) =>
    http.get<RiskCollaboration[]>(`/v1/risk-cases/${caseId}/collaborations`, quiet),
  get: (id: string) => http.get<RiskCollaboration>(`/v1/risk-collaborations/${id}`, quiet),
  create: (
    caseId: string,
    payload: {
      assessment_id: string;
      expected_basis_hash: string;
      request_key: string;
      coordinator_id: string;
      participant_ids: string[];
      purpose: string;
    },
  ) => http.post<RiskCollaboration>(`/v1/risk-cases/${caseId}/collaborations`, payload, quiet),
};
