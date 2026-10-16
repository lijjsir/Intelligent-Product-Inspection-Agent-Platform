import {http} from "./http";
import type {KnowledgeItem,KnowledgeSourceRef,WorkspaceGrant} from "@/types/knowledge.types";
export const knowledgeApi={
  candidates:()=>http.get<KnowledgeItem[]>("/v1/knowledge/candidates"),
  published:()=>http.get<KnowledgeItem[]>("/v1/knowledge/published"),
  detail:(id:string)=>http.get<KnowledgeItem>(`/v1/knowledge/candidates/${id}`),
  submit:(body:Record<string,unknown>)=>http.post<KnowledgeItem>("/v1/knowledge/candidates",body),
  action:(id:string,action:string,body:Record<string,unknown>)=>http.post<KnowledgeItem>(`/v1/knowledge/candidates/${id}/${action}`,body),
  source:(kind:string,id:string)=>http.post<KnowledgeSourceRef>("/v1/knowledge/source-preview",{kind,id}),
  targets:()=>http.get<{id:string;name:string;role:string}[]>("/v1/knowledge/share-targets"),
  grants:(id:string)=>http.get<WorkspaceGrant[]>(`/v1/knowledge/spaces/${id}/grants`),
  share:(id:string,body:Record<string,unknown>)=>http.post<WorkspaceGrant[]>(`/v1/knowledge/spaces/${id}/share`,body),
  revoke:(id:string,body:Record<string,unknown>)=>http.post<WorkspaceGrant[]>(`/v1/knowledge/spaces/${id}/revoke`,body),
  taskDraft:(id:string,body:Record<string,unknown>)=>http.post<{task_id:string;notice:string}>(`/v1/knowledge/materials/${id}/task-draft`,body),
};
