import {onBeforeUnmount,ref,watch,type Ref} from 'vue';
import {http} from '@/api/http';

export function useProtectedMedia(source:Ref<string>){
  const resolved=ref('');let blobUrl='';let generation=0;
  function revoke(){if(blobUrl)URL.revokeObjectURL(blobUrl);blobUrl='';}
  watch(source,async value=>{const current=++generation;revoke();resolved.value='';
    if(!/^\/api\/v1\/(?:quality-data\/attachments\/[^/]+\/download|files\/)/.test(value)){resolved.value=value;return;}
    try{const result=await http.get<Blob>(value.slice(4),{responseType:'blob',suppressErrorToast:true});if(current!==generation)return;blobUrl=URL.createObjectURL(result.data as unknown as Blob);resolved.value=blobUrl;}catch{resolved.value='';}
  },{immediate:true});
  onBeforeUnmount(()=>{generation++;revoke();});return resolved;
}
