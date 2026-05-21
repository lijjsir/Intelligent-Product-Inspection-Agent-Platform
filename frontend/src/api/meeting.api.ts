import { http } from "./http";
import type { MeetingMessage, MeetingRoom, MeetingRoomCreate, MeetingRoomJoin } from "@/types/meeting.types";

export const meetingApi = {
  listRooms(limit = 100) {
    return http.get<MeetingRoom[]>("/v1/meetings/rooms", { params: { limit } });
  },

  createRoom(payload: MeetingRoomCreate) {
    return http.post<MeetingRoom>("/v1/meetings/rooms", payload);
  },

  joinRoom(payload: MeetingRoomJoin) {
    return http.post<MeetingRoom>("/v1/meetings/rooms/join", payload);
  },

  listMessages(roomId: string, afterSeq = 0, limit = 200) {
    return http.get<MeetingMessage[]>(`/v1/meetings/rooms/${roomId}/messages`, {
      params: { after_seq: afterSeq, limit },
    });
  },

  sendMessage(roomId: string, content: string) {
    return http.post<MeetingMessage>(`/v1/meetings/rooms/${roomId}/messages`, { content });
  },
};
