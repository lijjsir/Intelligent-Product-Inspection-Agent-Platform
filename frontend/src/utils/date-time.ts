function pad2(value: number) {
  return String(value).padStart(2, "0");
}

export function parseServerDateTime(value?: string | null) {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const isoLike = trimmed.includes("T") ? trimmed : trimmed.replace(" ", "T");
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(isoLike) ? isoLike : `${isoLike}Z`;
  const parsed = new Date(normalized);
  if (!Number.isNaN(parsed.getTime())) return parsed;
  const fallback = new Date(trimmed);
  return Number.isNaN(fallback.getTime()) ? null : fallback;
}

export function formatServerDateTime(
  value?: string | null,
  options: { includeSeconds?: boolean } = {},
) {
  if (!value) return "";
  const parsed = parseServerDateTime(value);
  if (!parsed) return value;
  const base = `${parsed.getFullYear()}-${pad2(parsed.getMonth() + 1)}-${pad2(parsed.getDate())}`;
  const time = `${pad2(parsed.getHours())}:${pad2(parsed.getMinutes())}`;
  if (options.includeSeconds) {
    return `${base} ${time}:${pad2(parsed.getSeconds())}`;
  }
  return `${base} ${time}`;
}
