import type { ChatAttachment, ChatMessagePayload } from "@/types/chat.types";

const IMAGE_EXTENSION_PATTERN = /\.(?:apng|avif|bmp|gif|ico|jpe?g|png|svg|webp)(?:[?#].*)?$/i;

function hasImageExtension(value?: string | null): boolean {
  return IMAGE_EXTENSION_PATTERN.test(String(value || "").trim());
}

export function agentLabel(payload: Pick<ChatMessagePayload, "agent"> | null | undefined): string {
  if (payload?.agent === "chat") return "ChatAgent";
  if (payload?.agent === "inspection_task") return "InspectionTaskAgent";
  return "";
}

export function isImageAttachment(
  attachment: Pick<ChatAttachment, "kind" | "content_type" | "name" | "url">,
): boolean {
  const kind = String(attachment.kind || "").toLowerCase();
  const contentType = String(attachment.content_type || "").toLowerCase();
  return kind === "image" || contentType.startsWith("image/") || hasImageExtension(attachment.name) || hasImageExtension(attachment.url);
}
