export interface AttachmentLike {
  kind?: string | null;
  name?: string | null;
  file_name?: string | null;
  url?: string | null;
  content_type?: string | null;
  mime_type?: string | null;
}

const IMAGE_ATTACHMENT_EXT_PATTERN = /\.(?:apng|avif|bmp|gif|ico|jpe?g|png|svg|webp)(?:[?#].*)?$/i;

export function attachmentDisplayName(attachment: AttachmentLike) {
  return String(attachment.name || attachment.file_name || "附件");
}

export function isImageAttachment(attachment: AttachmentLike) {
  const kind = String(attachment.kind || "").toLowerCase();
  const contentType = String(attachment.content_type || attachment.mime_type || "").toLowerCase();
  const name = attachmentDisplayName(attachment);
  const url = String(attachment.url || "");
  return kind === "image" || contentType.startsWith("image/") || IMAGE_ATTACHMENT_EXT_PATTERN.test(name) || IMAGE_ATTACHMENT_EXT_PATTERN.test(url);
}
