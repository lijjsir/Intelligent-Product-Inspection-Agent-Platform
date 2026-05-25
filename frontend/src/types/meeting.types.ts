export type MessageType = "user" | "agent" | "agent_streaming" | "system";

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
