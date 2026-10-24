import { createApp, defineComponent, h, nextTick, shallowRef, type App } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import QualityRecordOriginalPanel from "@/components/business/quality-risk/QualityRecordOriginalPanel.vue";
import { qualityRiskApi } from "@/api/quality-risk.api";
import type { QualityAttachment, QualitySourceRecord } from "@/types/quality-risk.types";

vi.mock("@/api/quality-risk.api", () => ({ qualityRiskApi: { downloadAttachment: vi.fn(), previewAttachmentPage: vi.fn() } }));
vi.mock("@/api/http", () => ({ extractApiErrorMessage: (error: Error, fallback: string) => error.message || fallback }));
const attachment = (id = 'pdf'): QualityAttachment => ({ id, file_name: '原始报告.pdf', mime_type: 'application/pdf', size_bytes: 100, sha256: 'hash', download_url: '' });
const record = (id = 'source'): QualitySourceRecord => ({ id, provenance: { source_url: 'https://example.gov.cn/source' } } as QualitySourceRecord);
let app: App | undefined;
let root: HTMLDivElement;
let objectId = 0;
async function flush() { for (let i = 0; i < 12; i++) await Promise.resolve(); await nextTick(); }
async function mount(files = [attachment()]) {
  const source = shallowRef(record()), attachments = shallowRef(files);
  app = createApp(defineComponent({ setup: () => () => h(QualityRecordOriginalPanel, { record: source.value, attachments: attachments.value }) }));
  app.component('ElButton', defineComponent({ setup: (_, { slots, attrs }) => () => h('button', attrs, slots.default?.()) }));
  app.component('ElSkeleton', defineComponent({ setup: () => () => h('div', '加载中') }));
  app.component('ElSelect', defineComponent({ setup: (_, { slots }) => () => h('div', slots.default?.()) }));
  app.component('ElOption', defineComponent({ setup: () => () => h('div') }));
  app.component('ElInputNumber', defineComponent({ props:['size'], setup: () => () => h('input') }));
  app.directive('loading', {});
  app.mount(root); await flush(); return { source, attachments };
}
beforeEach(() => {
  vi.resetAllMocks(); objectId = 0;
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => `blob:original-${++objectId}`), revokeObjectURL: vi.fn() }));
  vi.mocked(qualityRiskApi.downloadAttachment).mockResolvedValue({ data: new Blob(['%PDF-1.7']) } as never);
  vi.mocked(qualityRiskApi.previewAttachmentPage).mockResolvedValue({ data: new Blob(['PNG']), headers: {'x-pdf-page-count':'8'} } as never);
  root = document.createElement('div'); document.body.append(root);
});
afterEach(() => { app?.unmount(); app = undefined; root.remove(); vi.unstubAllGlobals(); });

describe('quality source original viewing', () => {
  it('loads the authenticated PDF for comparison and releases its object URL on unmount', async () => {
    await mount();
    expect(qualityRiskApi.downloadAttachment).toHaveBeenCalledWith('pdf');
    expect(qualityRiskApi.previewAttachmentPage).not.toHaveBeenCalled();
    expect(root.querySelector('iframe')?.getAttribute('src')).toBe('blob:original-1#view=FitH&navpanes=0');
    expect(root.textContent).toContain('整份 PDF 连续滚动');
    app?.unmount(); app = undefined;
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:original-1');
  });
  it('does not fabricate a PDF for a webpage-only source', async () => {
    await mount([]);
    expect(root.textContent).toContain('网页资料不一定有 PDF');
    expect(root.querySelector('iframe')).toBeNull();
    expect(qualityRiskApi.downloadAttachment).not.toHaveBeenCalled();
    expect(root.querySelector('a')?.href).toBe('https://example.gov.cn/source');
  });
  it('ignores a late file response after changing the selected record', async () => {
    let finish!: (value: never) => void;
    vi.mocked(qualityRiskApi.downloadAttachment).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const { source, attachments } = await mount();
    source.value = record('new-record'); attachments.value = [];
    await flush();
    finish({ data: new Blob(['%PDF-1.7']) } as never); await flush();
    expect(root.querySelector('iframe')).toBeNull();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
  it('retains errors and permits a retry instead of displaying the previous source', async () => {
    vi.mocked(qualityRiskApi.downloadAttachment).mockRejectedValueOnce(new Error('附件已不可用'));
    await mount();
    expect(root.textContent).toContain('附件已不可用');
    root.querySelector('button')?.click(); // download event does not load the preview
    const retry = Array.from(root.querySelectorAll('button')).find(button => button.textContent === '重试原件');
    retry?.click(); await flush();
    expect(root.querySelector('iframe')).not.toBeNull();
  });
  it('renders a text attachment as literal text and rejects executable source URLs', async () => {
    const literal = '<script>not executable</script>';
    const blob = Object.assign(new Blob([literal]), {text:async()=>literal});
    vi.mocked(qualityRiskApi.downloadAttachment).mockResolvedValue({ data: blob } as never);
    const { source } = await mount([{ ...attachment('text'), file_name: '来源文字.txt', mime_type: 'text/plain' }]);
    expect(root.querySelector('.original-text')?.textContent).toBe('<script>not executable</script>');
    expect(root.querySelector('script')).toBeNull();
    const original = Array.from(root.querySelectorAll('a')).find(link=>link.textContent==='新窗口查看原件');
    expect(original?.getAttribute('href')).toBe('blob:original-1');
    expect(original?.target).toBe('_blank');
    expect(root.querySelector('.original-image')).toBeNull();
    expect(root.querySelector('.original-page-controls')).toBeNull();
    source.value = { ...record(), provenance: { source_url: 'javascript:alert(1)' } };
    await flush(); expect(root.querySelector('.original-source')).toBeNull();
  });
  it('releases the text original link when closing the comparison', async()=>{
    const blob = Object.assign(new Blob(['原始文字副本']),{text:async()=>'原始文字副本'});
    vi.mocked(qualityRiskApi.downloadAttachment).mockResolvedValue({data:blob} as never);
    await mount([{...attachment('text'),file_name:'原始附件.txt',mime_type:'text/plain'}]);
    expect(root.textContent).toContain('新窗口查看原件');
    app?.unmount();app=undefined;
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:original-1');
  });
});
