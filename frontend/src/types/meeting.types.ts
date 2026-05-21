export interface MeetingRoom {
  id: string;
  org_id: string;
  title: string;
  access_code: string;
  created_by: string;
  status: string;
  member_count: number;
  last_message_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MeetingMessage {
  id: string;
  room_id: string;
  user_id: string;
  username: string;
  seq_no: number;
  content: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MeetingRoomCreate {
  title: string;
  password?: string | null;
}

export interface MeetingRoomJoin {
  access_code: string;
  password?: string | null;
}
