import { http } from "./http";
import type { RiskCollaboration } from "@/types/risk-collaboration.types";
import type { ReferencePage,ReferenceQuery } from './supervision.api';
const quiet = { suppressErrorToast: true };
export const riskCollaborationApi = {
  participantPage:(query:ReferenceQuery)=>http.get<ReferencePage>('/v1/risk-collaborations/participant-pages',{...quiet,params:{...query,size:20},paramsSerializer:{indexes:null}}),
  page: (caseId:string,params:{assessment_id?:string;cursor?:string})=>http.get<{items:RiskCollaboration[];next_cursor:string|null;has_more:boolean}>(`/v1/risk-cases/${caseId}/collaboration-pages`,{...quiet,params:{...params,size:20}}),
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
