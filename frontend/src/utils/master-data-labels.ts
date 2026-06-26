type CodeNameLike = {
  code?: string | null;
  name?: string | null;
};

type BatchLike = {
  batch_no?: string | null;
  name?: string | null;
};

function clean(value?: string | null) {
  return String(value || "").trim();
}

export function formatCodeName(item: CodeNameLike | null | undefined, fallback = "-") {
  if (!item) return fallback;
  const code = clean(item.code);
  const name = clean(item.name);
  if (code && name && code.toLowerCase() !== name.toLowerCase()) return `${code} · ${name}`;
  return code || name || fallback;
}

export function formatBatchLabel(item: BatchLike | null | undefined, fallback = "-") {
  if (!item) return fallback;
  const batchNo = clean(item.batch_no);
  const name = clean(item.name);
  if (batchNo && name && batchNo.toLowerCase() !== name.toLowerCase()) return `${batchNo} · ${name}`;
  return batchNo || name || fallback;
}

export function formatTaskEntityLabel(name?: string | null, code?: string | null, fallback = "-") {
  const cleanName = clean(name);
  const cleanCode = clean(code);
  if (cleanName && cleanCode && cleanName.toLowerCase() !== cleanCode.toLowerCase()) return `${cleanName}（${cleanCode}）`;
  return cleanName || cleanCode || fallback;
}
