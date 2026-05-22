import { http } from "./http";

export interface StreamSessionResponse {
  stream_token: string;
  expires_at: string;
  resource: "chat" | "task" | "meeting";
  resource_id: string;
}

export const streamApi = {
  create(resource: "chat" | "task" | "meeting", resourceId: string) {
    return http.post<StreamSessionResponse>("/v1/streams/session", {
      resource,
      resource_id: resourceId,
    });
  },
};
