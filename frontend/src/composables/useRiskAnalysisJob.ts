import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue';
import { qualityRiskApi } from '@/api/quality-risk.api';
import { extractApiErrorMessage } from '@/api/http';
import type { RiskAnalysisJob } from '@/types/quality-risk.types';

export function useRiskAnalysisJob(caseId:Ref<string>,finished:()=>Promise<void>) {
  const job=ref<RiskAnalysisJob|null>(null),connectionError=ref(''),submitting=ref(false),cancelling=ref(false);
  const active=computed(()=>!!job.value && ['queued','running'].includes(job.value.status));
  let epoch=0,timer:ReturnType<typeof setTimeout>|undefined,alive=true;
  function schedule() { clearTimeout(timer);if(alive && active.value)timer=setTimeout(()=>void poll(),connectionError.value?10000:2500); }
  async function poll() {
    const id=caseId.value,current=job.value,key=epoch;
    if(!current || !active.value || !id)return;
    try {
      const value=(await qualityRiskApi.analysisJob(id,current.id)).data.data;
      if(!alive || key!==epoch || id!==caseId.value)return;
      job.value=value;connectionError.value='';
      if(!['queued','running'].includes(value.status))await finished();
    } catch(error) { if(key===epoch)connectionError.value=extractApiErrorMessage(error,'暂时无法获取进度，后台请求保留，请稍后刷新。'); }
    finally { if(key===epoch)schedule(); }
  }
  async function loadLatest() {
    const id=caseId.value,key=++epoch,wasActive=active.value;clearTimeout(timer);
    if(!id){job.value=null;connectionError.value='';return;}
    try {
      const value=(await qualityRiskApi.latestAnalysisJob(id)).data.data;
      if(!alive || key!==epoch || id!==caseId.value)return;
      job.value=value?.id ? value : null;connectionError.value='';
      if(wasActive && job.value && !active.value)await finished();
      schedule();
    } catch(error){if(key===epoch)connectionError.value=extractApiErrorMessage(error,'任务进度暂不可用，可以刷新重试。');}
  }
  async function submit(baseId:string|null,policy?:string,execution?:string) {
    if(submitting.value || active.value || !caseId.value)return;
    const id=caseId.value,key=++epoch,storageKey=`risk-analysis-request:${id}`;clearTimeout(timer);
    const options=JSON.stringify([baseId,policy||null,execution||null]);
    let request={key:crypto.randomUUID(),options};
    try {const prior=JSON.parse(sessionStorage.getItem(storageKey)||'null');if(prior?.options===options && typeof prior.key==='string')request=prior;sessionStorage.setItem(storageKey,JSON.stringify(request));}catch{ /* storage may be unavailable */ }
    submitting.value=true;
    try {
      const value=(await qualityRiskApi.analyzeRisk(id,request.key,baseId,policy,execution)).data.data;
      try{sessionStorage.removeItem(storageKey);}catch{ /* best effort */ }
      if(!alive || key!==epoch || id!==caseId.value)return;
      job.value=value;connectionError.value='';
      if(active.value)schedule();else await finished();
      return value;
    } finally{submitting.value=false;}
  }
  watch(caseId,()=>{job.value=null;connectionError.value='';void loadLatest();},{immediate:true});
  async function cancel() {
    if(!job.value || job.value.status!=='queued' || cancelling.value)return;
    const id=caseId.value,key=++epoch,current=job.value.id;clearTimeout(timer);cancelling.value=true;
    try {const value=(await qualityRiskApi.cancelAnalysisJob(id,current)).data.data;if(alive && key===epoch && id===caseId.value)job.value=value;}
    catch(error) {if(key===epoch)connectionError.value=extractApiErrorMessage(error,'取消未完成，请刷新任务进度核对当前状态。');}
    finally {cancelling.value=false;if(key===epoch)schedule();}
  }
  onBeforeUnmount(()=>{alive=false;++epoch;clearTimeout(timer);});
  return {job,active,submitting,cancelling,connectionError,submit,loadLatest,cancel};
}
