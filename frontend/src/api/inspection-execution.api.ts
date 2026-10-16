import {http, type ApiRequestConfig} from './http';
import type {ExecutionRun} from '@/types/inspection-execution.types';
export const inspectionExecutionApi={
  caseWorkflow:(taskId:string,config?:ApiRequestConfig)=>http.get<import('@/types/inspection-execution.types').InspectionCaseWorkflow|null>(`/v1/inspection-execution/tasks/${taskId}/case-workflow`,config),
  context:(taskId:string,config?:ApiRequestConfig)=>http.get<import('@/types/inspection-execution.types').ExecutionTaskContext>(`/v1/inspection-execution/tasks/${taskId}/context`,config),
  taskReport:(taskId:string,id:string)=>http.get<Blob>(`/v1/inspection-execution/tasks/${taskId}/reports/${id}`,{responseType:'blob'}),
  reportCandidates:(taskId:string,config?:ApiRequestConfig)=>http.get<any[]>(`/v1/inspection-execution/tasks/${taskId}/report-candidates`,config),
  linkReport:(taskId:string,body:Record<string,unknown>)=>http.post<import('@/types/inspection-execution.types').ExecutionTaskContext>(`/v1/inspection-execution/tasks/${taskId}/report-links`,body),
  requirements:(taskId:string,config?:ApiRequestConfig)=>http.get<any[]>('/v1/inspection-execution/requirements',{...config,params:{task_id:taskId}}),
  policies:(config?:ApiRequestConfig)=>http.get<any[]>('/v1/inspection-execution/policies',config),
  publishPolicy:(id:string,body:Record<string,unknown>,config?:ApiRequestConfig)=>http.post<any>(`/v1/inspection-execution/policies/${id}/publish`,body,config),
  withdrawPolicy:(id:string,body:Record<string,unknown>)=>http.post<any>(`/v1/inspection-execution/policies/${id}/withdraw`,body),
  list:(taskId:string,config?:ApiRequestConfig)=>http.get<ExecutionRun[]>('/v1/inspection-execution/runs',{...config,params:{task_id:taskId}}),
  create:(body:Record<string,unknown>,config?:ApiRequestConfig)=>http.post<ExecutionRun>('/v1/inspection-execution/runs',body,config),
  detail:(id:string,config?:ApiRequestConfig)=>http.get<ExecutionRun>(`/v1/inspection-execution/runs/${id}`,config),
  review:(id:string,body:Record<string,unknown>,config?:ApiRequestConfig)=>http.post<ExecutionRun>(`/v1/inspection-execution/runs/${id}/review`,body,config),
  report:(id:string,attachmentId:string)=>http.get<Blob>(`/v1/inspection-execution/runs/${id}/reports/${attachmentId}`,{responseType:'blob'}),
};
