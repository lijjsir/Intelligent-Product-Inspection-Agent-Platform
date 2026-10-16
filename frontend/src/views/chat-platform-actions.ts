import type { ChatMessage } from '@/types/chat.types';

export interface PlatformTaskLink { id: string; product: string; status: string; hasResult: boolean }

export function platformTaskLinks(message: ChatMessage): PlatformTaskLink[] {
  const output = new Map<string, PlatformTaskLink>();
  const rawArtifacts = message.payload?.artifacts;
  const artifacts = Array.isArray(rawArtifacts) ? rawArtifacts : [];
  for (const artifact of artifacts) {
    if (!artifact || typeof artifact !== 'object') continue;
    if (!['task_status', 'quality_report'].includes(artifact.type)) continue;
    const content = artifact.content || {};
    const rows = Array.isArray(content.tasks) ? content.tasks : [content];
    for (const value of rows) {
      if (!value || typeof value !== 'object') continue;
      const row = value as Record<string, unknown>;
      const id = String(row.task_id || '').trim();
      if (!id || row.found === false) continue;
      output.set(id, { id, product: String(row.product_name || row.product_id || '检测任务'), status: String(row.status || ''), hasResult: row.result_found === true });
    }
  }
  return [...output.values()].slice(0, 5);
}

export function offersTaskCreation(message: ChatMessage): boolean {
  return message.role === 'assistant' && (message.message_type === 'action_blocked' || message.payload?.route_decision?.sub_route === 'action_blocked');
}

export function platformSources(message: ChatMessage) {
  const rawCitations = message.payload?.citations;
  const citations = Array.isArray(rawCitations) ? rawCitations : [];
  return citations.filter((item) => item && typeof item === 'object').slice(0, 6).map((item, index) => ({
    label: String(item.title || item.file_name || item.source || `引用资料 ${index + 1}`).split(/[\\/]/).pop() || `引用资料 ${index + 1}`,
    quote: String(item.quote || item.excerpt || '').slice(0, 240),
  }));
}
