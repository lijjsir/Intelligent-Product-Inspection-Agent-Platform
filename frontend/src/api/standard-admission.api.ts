import { http } from "./http";
import type { StandardCandidate, StandardRevision, RevisionAction, StandardReviewQueue } from "@/types/standard-admission.types";
const base = (id: string) => `/v1/standard-documents/${id}/revisions`;
export const standardAdmissionApi = {
  reviewQueue(params: {scope:string;keyword?:string;domain?:string;page?:number;size?:number}) {
    return http.get<StandardReviewQueue>("/v1/standards/review-queue",{params});
  },
  reviewers() { return http.get<{id:string;name:string}[]>("/v1/standards/reviewers"); },
  assignment(id:string,rid:string,payload:RevisionAction & {operation:"assign"|"claim"|"release";reviewer_id?:string|null;due_at?:string|null}) {
    return http.post<StandardRevision>(`${base(id)}/${rid}/assignment`,payload);
  },
  candidateReview(id:string,rid:string,payload:RevisionAction & {candidate_id:string;decision:"confirm"|"needs_information"|"reject"}) {
    return http.post<StandardRevision>(`${base(id)}/${rid}/candidate-review`,payload);
  },
  requirementsDraft(id:string,rid:string,payload:RevisionAction) {
    return http.post<StandardRevision>(`${base(id)}/${rid}/requirements-draft`,payload);
  },
  revisions(id: string) { return http.get<StandardRevision[]>(base(id)); },
  detail(id: string, rid: string) { return http.get<StandardRevision>(`${base(id)}/${rid}`); },
  amend(id: string, payload: Record<string, unknown>) { return http.post<StandardRevision>(base(id), payload); },
  review(id: string, rid: string, payload: RevisionAction & {decision: string; conflict_resolution?: string}) {
    return http.post<StandardRevision>(`${base(id)}/${rid}/review`, payload);
  },
  action(id: string, rid: string, action: "publish"|"withdraw"|"retry", payload: RevisionAction) {
    return http.post<StandardRevision>(`${base(id)}/${rid}/${action}`, payload);
  },
  candidate(id: string, rid: string, payload: RevisionAction & Partial<StandardCandidate> & {candidate_id: string}) {
    return http.post<StandardRevision>(`${base(id)}/${rid}/candidates`, payload);
  },
  file(id: string, rid: string) { return http.get<Blob>(`${base(id)}/${rid}/file`, {responseType: "blob"}); },
  applicability(id: string, rid: string, payload: {product_category:string; production_date:string|null; conditions:string}) {
    return http.post<{status:string; missing_fields:string[]; mismatches:string[]; scope_notes:string;notice:string}>(`${base(id)}/${rid}/applicability`,payload);
  },
  requirements() { return http.get<(StandardCandidate & {document_id:string;revision_id:string;library_id:string;library_name:string;standard_no:string;publication_status:string;usage_status:string})[]>("/v1/standards/requirements"); },
};
