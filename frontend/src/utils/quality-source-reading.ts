export interface SourceTextReading {
  title: string;
  paragraphs: string[];
  cleaned: boolean;
}

const compact = (value: string) => value.replace(/\s+/g, "");
const isHeading = (line: string) => /^(?:[一二三四五六七八九十百]{1,3}、[^。！？]{1,65}|[（(][一二三四五六七八九十]{1,3}[）)][^。！？]{1,30})$/.test(line);

/** Reading-only formatting for recognizable government webpage text exports.
 * The attachment bytes, numeric tokens and the business record are never rewritten.
 * Ambiguous plain text keeps its original lines rather than guessing a document body.
 */
export function readSourceText(raw: string, webpage = false): SourceTextReading {
  const lines = raw.replace(/^\uFEFF/, "").split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  const unchanged = { title: "", paragraphs: [raw], cleaned: false };
  if (!webpage || lines.length < 5 || !lines.slice(0, 100).some(line => /^(?:你的|您当前的|当前)?位置\s*[:：]|^你的位置\s*[:：]|^您当前的位置\s*[:：]/.test(line))) return unchanged;
  const title = (lines[0] || '').split(/\s+-\s+/)[0] || '';
  if (title.length < 8 || /[:：]/.test(title)) return unchanged;
  let start = -1;
  const published = lines.findIndex(line => /^发布时间\s*[:：]\s*\d{4}[-年]/.test(line));
  if (published >= 0) start = published + 1;
  else {
    // A repeated article heading after the navigation and metadata marks the body.
    for (let i = 6; i < lines.length; i++) if (compact(lines[i]!) === compact(title)) start = i + 1;
  }
  if (start < 0 || start >= lines.length) return unchanged;
  // Remove only an exact repeated title, including a title split across inline spans.
  for (let count = 1; count <= 4 && start + count <= lines.length; count++) {
    if (compact(lines.slice(start, start + count).join('')) === compact(title)) { start += count; break; }
  }
  const body = lines.slice(start);
  const footer = body.findIndex(line => /^(?:扫一扫在手机打开当前页|扫一扫在手机打开本页|打印本页|关闭窗口|返回顶部|分享到[：:]?)$/.test(line));
  const content = footer >= 0 ? body.slice(0, footer) : body;
  if (!content.length) return unchanged;
  const paragraphs: string[] = [];
  let buffer = '';
  const flush = () => { if (buffer) paragraphs.push(buffer); buffer = ''; };
  for (const line of content) {
    if (isHeading(line) || /^附件\s*\d/.test(line)) { flush(); paragraphs.push(line); continue; }
    // Separate adjacent numeric lines: two table cells must never become one value.
    const numericBoundary = /[\d.]$/.test(buffer) && /^[+-]?\d/.test(line);
    buffer += (numericBoundary && buffer ? '\n' : '') + line;
    if (/[。！？；]$/.test(line)) flush();
  }
  flush();
  return { title, paragraphs, cleaned: true };
}

export function safeSourceUrl(provenance: Record<string, unknown>): string {
  const value = provenance.source_url || provenance.origin_label;
  if (typeof value !== 'string') return '';
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch { return ''; }
}

export function isPdfAttachment(file: { mime_type: string; file_name: string }): boolean {
  return file.mime_type?.split(';')[0]?.toLowerCase() === 'application/pdf' || /\.pdf$/i.test(file.file_name);
}
