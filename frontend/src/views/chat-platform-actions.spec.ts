import { describe, expect, it } from 'vitest';
import { offersTaskCreation, platformTaskLinks } from './chat-platform-actions';
import type { ChatMessage } from '@/types/chat.types';

const message = (payload: ChatMessage['payload']): ChatMessage => ({ id:'a', session_id:'s', seq_no:2, role:'assistant', message_type:'assistant_text', content:'回答', payload });

describe('platform actions from actual artifacts', () => {
  it('offers reports only when a task has an actual result', () => {
    const value = message({ artifacts: [{ artifact_id:'x', type:'task_status', source_agent:'quality_analysis', content:{ tasks:[{task_id:'own-1',product_id:'产品',status:'done',result_found:true},{task_id:'own-2',status:'queued',result_found:false}] } }] });
    expect(platformTaskLinks(value).map((item)=>[item.id,item.hasResult])).toEqual([['own-1',true],['own-2',false]]);
  });
  it('does not turn invented identifiers in answer text into task actions', () => {
    const value = message({}); value.content = '查看任务 fake-task 并导出报告';
    expect(platformTaskLinks(value)).toEqual([]);
  });
  it('offers a confirmation handoff for blocked creation requests', () => {
    expect(offersTaskCreation(message({route_decision:{sub_route:'action_blocked'}}))).toBe(true);
    expect(offersTaskCreation(message({}))).toBe(false);
  });
});
