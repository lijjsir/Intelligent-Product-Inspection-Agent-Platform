import { http } from "./http";

export interface StreamSessionResponse {
  stream_token: string;
  expires_at: string;
  resource: "chat" | "task";
  resource_id: string;
}

export const streamApi = {
  create(resource: "chat" | "task", resourceId: string) {
    return http.post<StreamSessionResponse>("/v1/streams/session", {
      resource,
      resource_id: resourceId,
    });
  },
};
