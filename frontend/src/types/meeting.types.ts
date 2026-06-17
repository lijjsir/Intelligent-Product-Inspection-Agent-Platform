export type MessageType = "user" | "agent" | "agent_streaming" | "system" | "summary" | "action_item";
export type MeetingDataDomain =
  | "quality"
  | "standard"
  | "meeting"
  | "memory"
  | "platform_ops"
  | "model_billing"
  | "org_admin"
  | "data_access"
  | "security_audit"
  | "ai_conversation";

export interface MentionInfo {
  agent_id: string;
  agent_name: string;
}

export interface MeetingAttachment {
  id: string;
  name: string;
  url: string;
  content_type?: string | null;
  size_bytes: number;
  kind: "image" | "file" | string;
  bucket?: string | null;
  object_key?: string | null;
}

export interface MeetingQuoteSnapshot {
  source: "agent" | "user" | "private" | string;
  author: string;
  content: string;
  created_at?: string | null;
}

export interface MeetingMessage {
  id: string;
  room_id: string;
  user_id: string;
  username: string;
  seq_no: number;
  content: string;
  message_type: MessageType;
  agent_id?: string | null;
  mentions?: MentionInfo[] | null;
  quote_message_id?: string | null;
  metadata_json?: Record<string, unknown> | null;
  private_recipient_user_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MeetingRoomAgent {
  id: string;
  room_id: string;
  agent_id: string;
  agent_name: string;
  role: "participant" | "observer";
  added_by: string;
  allowed_domains: MeetingDataDomain[];
  allowed_tools: string[];
}

export interface MeetingRoomMember {
  id: string;
  room_id: string;
  user_id: string;
  username: string;
  role: "host" | "member" | string;
  joined_at?: string | null;
}

export interface MeetingBusinessContextTask {
  id: string;
  product_id: string;
  spec_code: string;
  status: string;
  priority?: number | null;
  has_result: boolean;
  has_stability: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MeetingBusinessContext {
  task_ids: string[];
  product_ids: string[];
  batch_nos: string[];
  standard_ids: string[];
  tasks: MeetingBusinessContextTask[];
}

export interface MeetingMemberRoleUpdate {
  role: "host" | "member";
}

export interface MeetingRoom {
  id: string;
  org_id: string;
  title: string;
  access_code: string;
  created_by: string;
  status: string;
  visibility: "private" | "team" | "org" | "restricted" | string;
  allowed_data_domains: MeetingDataDomain[];
  memory_policy?: Record<string, unknown> | null;
  audit_policy?: Record<string, unknown> | null;
  business_context?: MeetingBusinessContext | null;
  member_count: number;
  agent_count?: number;
  last_message_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MeetingRoomDetail extends MeetingRoom {
  agents: MeetingRoomAgent[];
  members: MeetingRoomMember[];
}

export interface MeetingRoomCreate {
  title: string;
  password?: string | null;
  visibility?: "private" | "team" | "org" | "restricted";
  allowed_data_domains?: MeetingDataDomain[] | null;
  business_context?: Partial<MeetingBusinessContext> | null;
}

export interface MeetingRoomUpdate {
  title?: string | null;
  visibility?: "private" | "team" | "org" | "restricted" | null;
  allowed_data_domains?: MeetingDataDomain[] | null;
  business_context?: Partial<MeetingBusinessContext> | null;
}

export interface MeetingRoomJoin {
  access_code: string;
  password?: string | null;
}

export interface MeetingAddAgentRequest {
  agent_id: string;
  role: string;
  allowed_domains?: MeetingDataDomain[] | null;
  allowed_tools?: string[] | null;
}

export interface MeetingContextPreview {
  room_id: string;
  user_role: string;
  room_role: string;
  allowed_domains: MeetingDataDomain[];
  denied_domains: MeetingDataDomain[];
  agent_permissions: Array<{
    agent_id: string;
    agent_name: string;
    role: string;
    allowed_domains: MeetingDataDomain[];
    allowed_tools: string[];
  }>;
  query_examples: string[];
  guardrails: string[];
  business_context?: MeetingBusinessContext | null;
}

export interface MeetingAgentQueryAudit {
  id: string;
  room_id: string;
  user_id: string;
  agent_id: string;
  question: string;
  intent?: string | null;
  requested_domains: MeetingDataDomain[];
  allowed_domains: MeetingDataDomain[];
  denied_domains: MeetingDataDomain[];
  tool_calls: Array<Record<string, unknown>>;
  source_refs: Array<Record<string, unknown>>;
  memory_reads: Array<Record<string, unknown>>;
  redacted_fields: string[];
  decision: "allowed" | "partial" | "denied" | string;
  created_at?: string | null;
}

export type MeetingAgentSubgraph =
  | "risk_forecast"
  | "evidence_query"
  | "standard_explain"
  | "meeting_summary"
  | "memory_transfer"
  | "action_items";

export interface MeetingMemoryScope {
  include_meeting: boolean;
  include_confirmed: boolean;
  include_personal_authorized: boolean;
}

export type MeetingMemoryPublishScope =
  | "meeting"
  | "inspection_task"
  | "product"
  | "standard"
  | "rag_space"
  | "user"
  | "role"
  | "workspace"
  | "organization"
  | "batch";

export type MeetingMemoryType =
  | "decision"
  | "quality_fact"
  | "risk_insight"
  | "quality_pattern"
  | "action_suggestion"
  | string;

export interface MeetingMemoryConfirmPayload {
  title?: string | null;
  content?: string | null;
  scope?: MeetingMemoryPublishScope;
  scope_id?: string | null;
  publish_reason?: string | null;
  is_business_memory?: boolean | null;
}

export interface MeetingMemoryDisputePayload {
  reason: string;
  conflicting_memory_id?: string | null;
}

export interface MeetingAgentRunRequest {
  query: string;
  mode?: "auto" | MeetingAgentSubgraph;
  memory_scope?: MeetingMemoryScope;
  attachments?: MeetingAttachment[];
  workflow_run_id?: string | null;
}

export interface MeetingMemorySource {
  memory_id: string;
  scope: string;
  title: string;
  summary: string;
}

export interface MeetingCandidateMemory {
  memory_id: string;
  title: string;
  content: string;
  summary: string;
  memory_type: MeetingMemoryType;
  status: string;
  memory_category: "business_memory" | "meeting_memory" | "rejected_noise" | string;
  recommended_scope: string;
  recommended_scope_id?: string | null;
  source_refs: Array<Record<string, unknown>>;
  business_context?: Partial<MeetingBusinessContext> | Record<string, unknown> | null;
  shareability?: {
    allowed_scopes?: string[];
    missing_bindings?: string[];
    requires_host_confirmation?: boolean;
    cross_room_allowed?: boolean;
    organization_scope_enabled?: boolean;
    [key: string]: unknown;
  } | null;
  warnings: string[];
  affected_objects?: Record<string, unknown> | null;
  evidence_refs?: Array<Record<string, unknown>>;
  forecast_window?: Record<string, unknown> | null;
  risk_level?: string | null;
  recommended_actions?: string[];
  source_room_id?: string | null;
  confidence?: number | null;
  source_message_id?: string | null;
  created_at?: string | null;
}

export interface MeetingAgentRunResponse {
  selected_subgraph: MeetingAgentSubgraph | string;
  answer: string;
  message: MeetingMessage;
  memory_sources: MeetingMemorySource[];
  candidate_memories: MeetingCandidateMemory[];
}

export interface MeetingMemory {
  memory_id: string;
  title: string;
  content: string;
  summary: string;
  memory_type: MeetingMemoryType;
  status: string;
  scope: string;
  scope_type?: string | null;
  scope_id?: string | null;
  memory_category: "business_memory" | "meeting_memory" | "rejected_noise" | string;
  recommended_scope?: string | null;
  recommended_scope_id?: string | null;
  source_refs: Array<Record<string, unknown>>;
  business_context?: Partial<MeetingBusinessContext> | Record<string, unknown> | null;
  shareability?: {
    allowed_scopes?: string[];
    missing_bindings?: string[];
    requires_host_confirmation?: boolean;
    cross_room_allowed?: boolean;
    organization_scope_enabled?: boolean;
    [key: string]: unknown;
  } | null;
  warnings: string[];
  affected_objects?: Record<string, unknown> | null;
  evidence_refs?: Array<Record<string, unknown>>;
  forecast_window?: Record<string, unknown> | null;
  risk_level?: string | null;
  recommended_actions?: string[];
  source_room_id?: string | null;
  publish_reason?: string | null;
  version_parent_id?: string | null;
  confidence?: number | null;
  source_message_id?: string | null;
  created_by?: string | null;
  confirmed_by?: string | null;
  confirmed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MeetingActionItem {
  id: string;
  room_id: string;
  title: string;
  description?: string | null;
  owner_id?: string | null;
  owner_name: string;
  due_at?: string | null;
  status: "open" | "in_progress" | "done" | "cancelled" | string;
  source_message_id?: string | null;
  created_by: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MeetingActionItemCreate {
  title: string;
  description?: string | null;
  owner_id?: string | null;
  due_at?: string | null;
  source_message_id?: string | null;
}

export interface MeetingActionItemUpdate {
  title?: string | null;
  description?: string | null;
  owner_id?: string | null;
  due_at?: string | null;
  status?: "open" | "in_progress" | "done" | "cancelled" | string | null;
}

// ── SSE Event Types ──────────────────────────────────────────────

export type MeetingStreamEvent =
  | { event: "message_created"; room_id: string; message: MeetingMessage }
  | { event: "agent_run_started"; room_id: string; message_id: string; agent_id: string; agent_name: string; workflow_run_id: string; query?: string | null }
  | { event: "message_delta"; room_id: string; message_id: string; agent_id: string; delta: string; workflow_run_id: string }
  | { event: "message_final"; room_id: string; message_id: string; agent_id: string; content: string; workflow_run_id: string }
  | { event: "agent_run_failed"; room_id: string; message_id: string; agent_id: string; agent_name: string; workflow_run_id: string; error: string };

// ── Admin Types ──────────────────────────────────────────────────

export interface AdminMeetingRoom extends MeetingRoom {
  created_by_username: string;
  message_count: number;
  member_count: number;
  agent_count: number;
}
