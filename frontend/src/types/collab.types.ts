export type CollabParticipantType = "user" | "meeting_room" | "agent";

export type CollabMessageType =
  | "text"
  | "file"
  | "image"
  | "system"
  | "memory_card"
  | "action_request";

export type CollabActionStatus = "pending" | "accepted" | "rejected" | "done";

export interface CollabAttachmentPayload {
  id: string;
  name: string;
  url: string;
  content_type?: string | null;
  size_bytes: number;
  kind: "image" | "file" | string;
  bucket?: string | null;
  object_key?: string | null;
}

export interface CollabThreadParticipant {
  id: string;
  thread_id: string;
  participant_type: CollabParticipantType | string;
  participant_id: string;
  role: "owner" | "participant" | string;
  last_read_message_id?: string | null;
  joined_at?: string | null;
}

export interface CollabThread {
  id: string;
  org_id: string;
  thread_type: string;
  source_type: CollabParticipantType | string;
  source_id: string;
  target_type: CollabParticipantType | string;
  target_id: string;
  title: string;
  status: "active" | "closed" | "archived" | string;
  created_by: string;
  last_message_at?: string | null;
  unread_count: number;
  metadata_json?: Record<string, unknown> | null;
  participants: CollabThreadParticipant[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CollabTarget {
  target_type: CollabParticipantType;
  target_id: string;
  label: string;
  description?: string | null;
  group?: string | null;
}

export interface CollabThreadCreatePayload {
  target_type: CollabParticipantType;
  target_id: string;
  title?: string | null;
  source_type?: CollabParticipantType;
  source_id?: string | null;
  metadata_json?: Record<string, unknown> | null;
}

export interface CollabFileAsset {
  id: string;
  bucket: string;
  object_key: string;
  url: string;
  file_name: string;
  mime_type?: string | null;
  size_bytes: number;
  checksum: string;
}

export interface CollabMessageReceipt {
  id: string;
  message_id: string;
  thread_id: string;
  recipient_type: CollabParticipantType | string;
  recipient_id: string;
  delivered_at?: string | null;
  read_at?: string | null;
  acted_at?: string | null;
  action_status: CollabActionStatus | string;
}

export interface CollabMessage {
  id: string;
  org_id: string;
  thread_id: string;
  sender_type: CollabParticipantType | string;
  sender_id: string;
  message_type: CollabMessageType | string;
  content: string;
  reply_to_message_id?: string | null;
  metadata_json?: Record<string, unknown> | null;
  attachments: CollabFileAsset[];
  receipts: CollabMessageReceipt[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CollabMessageCreatePayload {
  content: string;
  message_type?: CollabMessageType;
  reply_to_message_id?: string | null;
  attachments?: CollabAttachmentPayload[];
  metadata_json?: Record<string, unknown> | null;
}

export interface CollabMessageActionPayload {
  action_status: "accepted" | "rejected" | "done";
}

export interface CollabUploadResponse {
  items: CollabAttachmentPayload[];
}

export type CollabStreamEvent =
  | {
      event: "collab_message_created";
      thread_id: string;
      message: CollabMessage;
      unread?: boolean;
    }
  | {
      event: "collab_message_read" | "collab_message_action_updated";
      thread_id: string;
      message_id: string;
      receipt: CollabMessageReceipt;
    }
  | {
      event: "collab_message_deleted";
      thread_id: string;
      message_id: string;
    }
  | {
      event: "collab_thread_deleted";
      thread_id: string;
    };
