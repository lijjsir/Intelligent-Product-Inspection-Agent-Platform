export interface RiskCollaboration {
  reused?: boolean;
  decision_note?: string;
  id: string;
  title: string;
  case_id: string;
  case_code: string;
  assessment_id: string;
  assessment_version: number;
  is_latest: boolean;
  basis_current: boolean;
  execution_mode: "demo" | "business";
  purpose: string;
  created_by: string;
  created_at: string;
  room_id: string;
  thread_id: string;
  message_id: string;
  coordinator_id: string;
  participants: Array<{ id: string; name: string }>;
  status: string;
  room_status: string;
  source_link: string;
  discussion?: RiskCollaborationComment[];
  comments?: RiskCollaborationComment[];
}
export interface RiskCollaborationComment {
  id: string;
  author: string;
  content: string;
  created_at: string;
  origin: "meeting" | "collab";
  seq_no?: number;
}
