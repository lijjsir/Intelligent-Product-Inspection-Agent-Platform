import { afterEach,beforeEach,describe,it,expect,vi } from 'vitest';
import { createApp,h,ref } from 'vue';
import { useRiskAnalysisJob } from './useRiskAnalysisJob';
const api=vi.hoisted(()=>({latestAnalysisJob:vi.fn(),analysisJob:vi.fn(),analyzeRisk:vi.fn()}));
vi.mock('@/api/quality-risk.api',()=>({qualityRiskApi:api}));
vi.mock('@/api/http',()=>({extractApiErrorMessage:(_e:unknown,fallback:string)=>fallback}));
const envelope=(data:unknown)=>({data:{data}});
const row=(status='queued')=>({id:'job',case_id:'a',status,message:'Saved request',assessment_id:status==='succeeded'?'result':null});
const cleanup:Array<()=>void>=[];
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
function mount(){const id=ref('a'),finished=vi.fn().mockResolvedValue(undefined);let state!:ReturnType<typeof useRiskAnalysisJob>;
 const app=createApp({setup(){state=useRiskAnalysisJob(id,finished);return()=>h('div');}});const el=document.createElement('div');document.body.append(el);app.mount(el);cleanup.push(()=>{app.unmount();el.remove();});return {id,finished,get state(){return state;}};}
beforeEach(()=>{vi.useFakeTimers();sessionStorage.clear();vi.resetAllMocks();api.latestAnalysisJob.mockResolvedValue(envelope(null));});
afterEach(()=>{cleanup.splice(0).forEach(fn=>fn());vi.useRealTimers();});
describe('durable risk analysis',()=>{
 it('restores queued analysis and polls to a saved draft without another POST',async()=>{
  api.latestAnalysisJob.mockResolvedValue(envelope(row()));api.analysisJob.mockResolvedValueOnce(envelope(row('running'))).mockResolvedValueOnce(envelope(row('succeeded')));
  const run=mount();await flush();expect(run.state.active.value).toBe(true);
  await vi.advanceTimersByTimeAsync(5000);expect(run.state.job.value?.status).toBe('succeeded');expect(run.finished).toHaveBeenCalledTimes(1);expect(api.analyzeRisk).not.toHaveBeenCalled();
 });
 it('preserves one request key after a lost submission response',async()=>{
  const run=mount();await flush();api.analyzeRisk.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(envelope(row()));
  await expect(run.state.submit(null)).rejects.toThrow('offline');await run.state.submit(null);
  expect(api.analyzeRisk.mock.calls[0][1]).toBe(api.analyzeRisk.mock.calls[1][1]);expect(run.state.active.value).toBe(true);
  await run.state.submit(null);expect(api.analyzeRisk).toHaveBeenCalledTimes(2);
 });
 it('keeps the task after polling fails and manual refresh loads its result',async()=>{
  api.latestAnalysisJob.mockResolvedValue(envelope(row('running')));api.analysisJob.mockRejectedValue(new Error('offline'));
  const run=mount();await flush();await vi.advanceTimersByTimeAsync(2500);
  expect(run.state.active.value).toBe(true);expect(run.state.connectionError.value).toBeTruthy();
  api.latestAnalysisJob.mockResolvedValue(envelope(row('succeeded')));await run.state.loadLatest();
  expect(run.finished).toHaveBeenCalledTimes(1);expect(api.analyzeRisk).not.toHaveBeenCalled();
 });
 it('discards a late response after switching cases',async()=>{
  let release!:(value:unknown)=>void;api.latestAnalysisJob.mockReturnValueOnce(new Promise(resolve=>release=resolve)).mockResolvedValueOnce(envelope({...row(),id:'b-job',case_id:'b'}));
  const run=mount();run.id.value='b';await flush();release(envelope(row()));await flush();expect(run.state.job.value?.id).toBe('b-job');
 });
});
