export type MessageType = "user" | "agent" | "agent_streaming" | "system" | "summary" | "action_item";

export interface MentionInfo {
  agent_id: string;
  agent_name: string;
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
}

export interface MeetingRoomMember {
  id: string;
  room_id: string;
  user_id: string;
  username: string;
  role: "host" | "member" | string;
  joined_at?: string | null;
}

export interface MeetingRoom {
  id: string;
  org_id: string;
  title: string;
  access_code: string;
  created_by: string;
  status: string;
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
}

export interface MeetingRoomJoin {
  access_code: string;
  password?: string | null;
}

export interface MeetingAddAgentRequest {
  agent_id: string;
  role: string;
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
  include_project_shared: boolean;
  include_personal_authorized: boolean;
}

export interface MeetingAgentRunRequest {
  query: string;
  mode?: "auto" | MeetingAgentSubgraph;
  memory_scope?: MeetingMemoryScope;
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
  memory_type: string;
  status: string;
  recommended_scope: string;
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
  memory_type: string;
  status: string;
  scope: string;
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
  | { event: "agent_run_started"; room_id: string; message_id: string; agent_id: string; agent_name: string; workflow_run_id: string }
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
