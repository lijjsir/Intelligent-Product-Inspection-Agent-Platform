import { createApp, defineComponent, h, nextTick, shallowRef, type App } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import RecordReviewActions from "@/components/business/supervision/RecordReviewActions.vue";
import { supervisionApi } from "@/api/supervision.api";
import { ElMessageBox } from "element-plus";
import type { RecordReview, SupervisionRecord } from "@/types/supervision.types";

vi.mock("@/api/supervision.api", () => ({ supervisionApi: { recordReviews: vi.fn(), decide: vi.fn() } }));
vi.mock("element-plus", () => ({ ElMessage: { success: vi.fn(), error: vi.fn() }, ElMessageBox: { prompt: vi.fn() } }));

const record = (id = "record-1"): SupervisionRecord => ({ id, org_id: 'org-1', kind: 'sampling-plans', code: 'P1', name: '抽查方案', status: 'awaiting_review', version: 1, created_by: 'author', data: {}, created_at: '', updated_at: '' });
const review = (overrides: Partial<RecordReview> = {}): RecordReview => ({ id: 'review-1', record_id: 'record-1', version: 1, operation: 'sampling.approve', status: 'pending', requester_id: 'author', can_decide: true, ...overrides });
const envelope = (items: RecordReview[]) => ({ data: { data: items } });
let app: App | undefined, root: HTMLDivElement;
const changed = vi.fn();
async function flush() { for (let i = 0; i < 8; i++) await Promise.resolve(); await nextTick(); }
async function mount(initial = record()) {
  const selected = shallowRef(initial);
  app = createApp(defineComponent({ setup: () => () => h(RecordReviewActions, { record: selected.value, onChanged: changed }) }));
  app.component('ElButton', defineComponent({ props: ['disabled'], setup: (props, { slots, attrs }) => () => h('button', { ...attrs, disabled: props.disabled }, slots.default?.()) }));
  app.mount(root); await flush();
  return selected;
}
function button(text: string) { return Array.from(root.querySelectorAll('button')).find(el => el.textContent === text)!; }

beforeEach(() => {
  vi.resetAllMocks(); root = document.createElement('div'); document.body.append(root);
  vi.mocked(supervisionApi.recordReviews).mockResolvedValue(envelope([review()]) as never);
  vi.mocked(supervisionApi.decide).mockResolvedValue({} as never);
});
afterEach(() => { app?.unmount(); app = undefined; root.remove(); });

describe('review actions within a business record', () => {
  it('approves the selected record and refreshes it after collecting an opinion', async () => {
    await mount();
    expect(supervisionApi.recordReviews).toHaveBeenCalledWith('sampling-plans', 'record-1');
    vi.mocked(ElMessageBox.prompt).mockResolvedValue({ value: '  依据核对完成  ', action: 'confirm' });
    button('批准抽查方案').click(); await flush();
    expect(supervisionApi.decide).toHaveBeenCalledWith('review-1', 'accept', '依据核对完成');
    expect(changed).toHaveBeenCalledTimes(1);
    expect(root.textContent).not.toContain('待我处理');
  });

  it('shows a waiting state without approval buttons for a non-independent reviewer', async () => {
    vi.mocked(supervisionApi.recordReviews).mockResolvedValue(envelope([review({ can_decide: false })]) as never);
    await mount();
    expect(root.textContent).toContain('等待其他专家独立复核');
    expect(button('批准抽查方案')).toBeUndefined();
  });

  it('keeps result review and formal confirmation as separate actions', async () => {
    vi.mocked(supervisionApi.recordReviews).mockResolvedValue(envelope([review({ operation: 'result.signoff' })]) as never);
    await mount({ ...record(), kind: 'inspection-sessions' });
    expect(button('确认正式结果')).toBeDefined();
    expect(button('通过结果复核')).toBeUndefined();
  });

  it('does not submit a decision when the opinion dialog is canceled', async () => {
    await mount();
    vi.mocked(ElMessageBox.prompt).mockRejectedValue('cancel');
    button('退回补证').click(); await flush();
    expect(supervisionApi.decide).not.toHaveBeenCalled();
    expect(button('批准抽查方案').disabled).toBe(false);
  });

  it('ignores a late response for a previously selected record', async () => {
    let resolveOld!: (value: never) => void;
    vi.mocked(supervisionApi.recordReviews).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }));
    const selected = await mount();
    vi.mocked(supervisionApi.recordReviews).mockResolvedValue(envelope([]) as never);
    selected.value = record('record-2'); await flush();
    resolveOld(envelope([review()]) as never); await flush();
    expect(button('批准抽查方案')).toBeUndefined();
  });

  it('keeps a failed state visible and allows retry', async () => {
    vi.mocked(supervisionApi.recordReviews).mockRejectedValueOnce(new Error('读取失败'));
    await mount();
    expect(root.textContent).toContain('读取失败');
    button('重试').click(); await flush();
    expect(button('批准抽查方案')).toBeDefined();
  });
});
