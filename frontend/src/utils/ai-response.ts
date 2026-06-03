export interface NormalizedAiResponse {
  content: string;
  summary?: string;
}

export function normalizeAiResponseText(value: unknown): NormalizedAiResponse {
  const content = String(value ?? "").trim();
  const parsed = extractJsonObject(content) || extractLooseAnswerSummary(content) || extractBareAnswerSummary(content);
  if (!parsed) return { content };

  const answer = typeof parsed.answer === "string" ? parsed.answer.trim() : "";
  const summary = typeof parsed.summary === "string" ? parsed.summary.trim() : "";
  const text = typeof parsed.text === "string" ? parsed.text.trim() : "";
  return {
    content: answer || text || summary || content,
    ...(summary ? { summary } : {}),
  };
}

function extractJsonObject(text: string): Record<string, unknown> | null {
  if (!text) return null;

  const candidates = [
    text,
    ...Array.from(text.matchAll(/```(?:json)?\s*([\s\S]*?)```/gi), (match) => match[1] || ""),
    ...jsonSpans(text),
  ].map((item) => item.trim()).filter(Boolean);

  candidates.sort((a, b) => Number(!a.includes("\"answer\"")) - Number(!b.includes("\"answer\"")) || a.length - b.length);

  for (let candidate of candidates) {
    if (candidate.toLowerCase().startsWith("json")) {
      candidate = candidate.slice(4).trim();
    }
    try {
      const parsed = JSON.parse(candidate);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      const loose = extractLooseAnswerSummary(candidate);
      if (loose) return loose;
    }
  }
  return null;
}

function extractLooseAnswerSummary(text: string): Record<string, unknown> | null {
  if (!/["']?answer["']?\s*:/i.test(text)) return null;
  const answer = extractLooseStringField(text, "answer");
  const summary = extractLooseStringField(text, "summary");
  const fallbackText = extractLooseStringField(text, "text");
  if (!answer && !summary && !fallbackText) return null;
  return {
    ...(answer ? { answer } : {}),
    ...(summary ? { summary } : {}),
    ...(fallbackText ? { text: fallbackText } : {}),
  };
}

function extractBareAnswerSummary(text: string): Record<string, unknown> | null {
  if (!/^\s*(?:answer|summary|text)\s*[:：]/i.test(text)) return null;
  const answer = extractBareStringField(text, "answer");
  const summary = extractBareStringField(text, "summary");
  const fallbackText = extractBareStringField(text, "text");
  if (!answer && !summary && !fallbackText) return null;
  return {
    ...(answer ? { answer } : {}),
    ...(summary ? { summary } : {}),
    ...(fallbackText ? { text: fallbackText } : {}),
  };
}

function extractLooseStringField(text: string, field: string): string {
  const key = `["']?${field}["']?\\s*:\\s*["']`;
  const re = new RegExp(`${key}([\\s\\S]*?)(?=["']?\\s*,\\s*["']?(?:answer|summary|text|message_type|ui_schema|rag_summary|citations|quality|metadata)["']?\\s*:|["']?\\s*\\}\\s*$)`, "i");
  const match = re.exec(text.trim());
  if (!match) return "";
  return match[1]
    .replace(/\\n/g, "\n")
    .replace(/\\"/g, "\"")
    .trim();
}

function extractBareStringField(text: string, field: string): string {
  const re = new RegExp(
    `(?:^|\\n)\\s*${field}\\s*[:：]\\s*([\\s\\S]*?)(?=\\n\\s*(?:answer|summary|text|message_type|ui_schema|rag_summary|citations|quality|metadata)\\s*[:：]|$)`,
    "i",
  );
  const match = re.exec(text.trim());
  return match ? match[1].trim() : "";
}

function jsonSpans(text: string): string[] {
  const spans: string[] = [];
  for (let start = text.indexOf("{"); start >= 0; start = text.indexOf("{", start + 1)) {
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let index = start; index < text.length; index += 1) {
      const char = text[index];
      if (escaped) {
        escaped = false;
        continue;
      }
      if (char === "\\" && inString) {
        escaped = true;
        continue;
      }
      if (char === "\"") {
        inString = !inString;
        continue;
      }
      if (inString) continue;
      if (char === "{") depth += 1;
      if (char === "}") depth -= 1;
      if (depth === 0) {
        spans.push(text.slice(start, index + 1));
        break;
      }
    }
  }
  return spans;
}
