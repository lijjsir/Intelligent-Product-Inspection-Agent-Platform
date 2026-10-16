export interface KnowledgeSourceRef {kind:string;id:string;quote:string;source_version?:string;authority?:string;metadata?:Record<string,any>;available_excerpt?:string}
export interface KnowledgeItem {
  id:string;memory_id:string;created_by:string;row_version:number;review_status:string;sharing_status:string;publication_status:string;
  snapshot:{claim:string;product_category:string;applicability:string;limitations:string;requested_scope:string;consent_to_review:boolean;consent_to_share:boolean;qdl?:Record<string,unknown>|null;related_memory_ids?:string[]};
  source_refs:KnowledgeSourceRef[];reviewed_by?:string;published_at?:string;created_at:string;
  actions?:{action:string;actor_id:string;reason:string;created_at:string}[];
  jobs?:{action:string;status:string;retry_count:number;error?:string}[];
}
export interface WorkspaceGrant {id:string;user_id:string;status:string;row_version:number;reason:string;allow_knowledge_submission:boolean}
