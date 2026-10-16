import { http } from "./http";
import type { InspectionResult, ResultListItem, ResultListQuery } from "@/types/result.types";
import type { PagedResponse } from "@/types/common.types";

export interface ReviewSubmit {
  verdict: string;
  note?: string | null;
}

export const resultApi = {
  summary:(id:string,selection?:{execution_run_id?:string;legacy_only?:boolean})=>http.get<import('@/types/result.types').TaskResultBundle>(`/v1/results/by-task/${id}/summary`,{params:selection}),
  reportTasks:()=>http.get<import('@/types/task.types').InspectionTask[]>('/v1/results/report-tasks'),
  executionOptions:()=>http.get<any[]>('/v1/results/execution-options'),
  unifiedList:(query:ResultListQuery)=>http.get<PagedResponse<any>>('/v1/results/unified',{params:query}),
  list(query: ResultListQuery) {
    return http.get<PagedResponse<ResultListItem>>("/v1/results", { params: query });
  },
  getByTask(taskId: string) {
    return http.get<InspectionResult>(`/v1/results/by-task/${taskId}`);
  },
  review(resultId: string, payload: ReviewSubmit) {
    return http.patch<InspectionResult>(`/v1/results/${resultId}/review`, payload);
  },
};
