<script lang="ts">
import { defineComponent, h, type VNodeChild } from "vue";

function inline(text: string): VNodeChild[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[RAG-\d+\])/g).map((part) => {
    if (part.startsWith('**') && part.endsWith('**')) return h('strong', part.slice(2, -2));
    if (part.startsWith('`') && part.endsWith('`')) return h('code', part.slice(1, -1));
    if (/^\[RAG-\d+\]$/.test(part)) return h('span', { class: 'answer-citation' }, `引用 ${part.match(/\d+/)?.[0]}`);
    return part;
  });
}

export default defineComponent({
  props: { content: { type: String, required: true } },
  setup(props) {
    return () => {
      const lines = props.content.split('\n');
      const children: VNodeChild[] = [];
      for (let i = 0; i < lines.length;) {
        const line = lines[i];
        if (!line.trim()) { i++; continue; }
        if (line.trim().startsWith('```')) {
          const code: string[] = [];
          i++;
          while (i < lines.length && !lines[i].trim().startsWith('```')) code.push(lines[i++]);
          if (i < lines.length) i++;
          children.push(h('pre', h('code', code.join('\n'))));
          continue;
        }
        const heading = line.match(/^\s*#{1,6}\s+(.+)$/);
        if (heading) { children.push(h('h3', inline(heading[1]))); i++; continue; }
        const list = line.match(/^\s*(?:[-*+]\s+|\d+[.)、]\s+)(.+)$/);
        if (list) {
          const ordered = /^\s*\d/.test(line);
          const items: VNodeChild[] = [];
          while (i < lines.length) {
            const item = lines[i].match(ordered ? /^\s*\d+[.)、]\s+(.+)$/ : /^\s*[-*+]\s+(.+)$/);
            if (!item) break;
            items.push(h('li', inline(item[1]))); i++;
          }
          children.push(h(ordered ? 'ol' : 'ul', items));
          continue;
        }
        if (line.includes('|') && i + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1])) {
          const cells = (value: string) => value.trim().replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim());
          const headers = cells(line); i += 2;
          const rows: VNodeChild[] = [];
          while (i < lines.length && lines[i].includes('|') && lines[i].trim()) rows.push(h('tr', cells(lines[i++]).map((cell) => h('td', inline(cell)))));
          children.push(h('div', { class: 'answer-table' }, h('table', [h('thead', h('tr', headers.map((cell) => h('th', inline(cell))))), h('tbody', rows)])));
          continue;
        }
        const paragraph = [line]; i++;
        while (i < lines.length && lines[i].trim() && !/^\s*(#{1,6}\s|```|[-*+]\s|\d+[.)、]\s)/.test(lines[i]) && !lines[i].includes('|')) paragraph.push(lines[i++]);
        children.push(h('p', inline(paragraph.join('\n'))));
      }
      return h('div', { class: 'chat-answer' }, children);
    };
  },
});
</script>

<style scoped>
.chat-answer { line-height: 1.9; overflow-wrap: anywhere; }
.chat-answer p { margin: 0 0 16px; white-space: pre-wrap; }
.chat-answer h3 { margin: 23px 0 10px; font-size: 17px; font-weight: 600; }
.chat-answer h3:first-child { margin-top: 0; }
.chat-answer ul, .chat-answer ol { padding-left: 25px; margin: 12px 0 18px; }
.chat-answer li { margin-bottom: 8px; }
.chat-answer strong { font-weight: 600; }
.chat-answer pre { overflow-x: auto; padding: 15px; background: #f5f7fa; border-radius: 10px; margin: 15px 0; white-space: pre; }
.chat-answer code { font-family: Consolas, monospace; font-size: 13px; background: #f2f5f8; padding: 2px 5px; border-radius: 4px; }
.answer-citation { color: #477db6; background: #f0f5fb; border-radius: 5px; padding: 2px 6px; font-size: 11px; }
.answer-table { overflow-x: auto; margin: 15px 0; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { border-bottom: 1px solid #e5ebf3; padding: 10px 12px; text-align: left; }
th { background: #f5f8fc; font-weight: 600; }
</style>
