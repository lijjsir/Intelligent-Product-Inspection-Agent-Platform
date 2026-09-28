import { http } from "./http";
import type { PagedResponse } from "@/types/common.types";
import type {
  ProductCategoryV4,
  QualityAttachment,
  QualityDataSource,
  QualityProduct,
  QualitySourceRecord,
  RiskAssessmentV4,
  RiskCaseV4,
} from "@/types/quality-risk.types";

export const qualityRiskApi = {
  productCatalog: (includeInactive = false) =>
    http.get<{ categories: ProductCategoryV4[]; products: QualityProduct[] }>(
      "/v1/quality-products/catalog",
      { params: { include_inactive: includeInactive } },
    ),
  createCategory: (payload: Record<string, unknown>) =>
    http.post<ProductCategoryV4>("/v1/quality-products/categories", payload),
  updateCategory: (id: string, payload: Record<string, unknown>) =>
    http.patch<ProductCategoryV4>(`/v1/quality-products/categories/${id}`, payload),
  createProduct: (payload: Record<string, unknown>) =>
    http.post<QualityProduct>("/v1/quality-products", payload),
  updateProduct: (id: string, payload: Record<string, unknown>) =>
    http.patch<QualityProduct>(`/v1/quality-products/${id}`, payload),
  sources: () => http.get<QualityDataSource[]>("/v1/quality-data/sources"),
  createSource: (payload: Record<string, unknown>) =>
    http.post<QualityDataSource>("/v1/quality-data/sources", payload),
  updateSource: (id: string, payload: Record<string, unknown>) =>
    http.patch<QualityDataSource>(`/v1/quality-data/sources/${id}`, payload),
  records: (params: Record<string, unknown> = {}) =>
    http.get<PagedResponse<QualitySourceRecord>>("/v1/quality-data/records", { params }),
  record: (id: string) => http.get<QualitySourceRecord>(`/v1/quality-data/records/${id}`),
  evidence: (id: string) => http.get<any[]>(`/v1/quality-data/records/${id}/evidence`),
  createEvent: (payload: Record<string, unknown>) =>
    http.post<QualitySourceRecord>("/v1/quality-data/events", payload),
  uploadAttachments: (files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return http.post<QualityAttachment[]>("/v1/quality-data/attachments", form);
  },
  previewImport: (sourceId: string, requestKey: string, file: File, mapping = {}) => {
    const form = new FormData();
    form.append("source_id", sourceId);
    form.append("request_key", requestKey);
    form.append("mapping", JSON.stringify(mapping));
    form.append("file", file);
    return http.post<any>("/v1/quality-data/imports", form);
  },
  importTemplate: () =>
    http.get<Blob>("/v1/quality-data/import-template", { responseType: "blob" }),
  confirmImport: (id: string) => http.post(`/v1/quality-data/imports/${id}/confirm`, {}),
  cancelImport: (id: string) => http.post(`/v1/quality-data/imports/${id}/cancel`, {}),
  riskCases: (params: Record<string, unknown> = {}) =>
    http.get<PagedResponse<RiskCaseV4>>("/v1/risk-cases", { params }),
  createRiskCase: (payload: Record<string, unknown>) =>
    http.post<RiskCaseV4>("/v1/risk-cases", payload),
  analyzeRisk: (id: string, policyId?: string) =>
    http.post<RiskAssessmentV4>(`/v1/risk-cases/${id}/analyze`, {
      policy_id: policyId || null,
    }),
  reviewRisk: (
    id: string,
    decision: string,
    comment: string,
    fields: Record<string, unknown> = {},
  ) =>
    http.post<RiskAssessmentV4>(`/v1/risk-cases/${id}/reviews`, {
      decision,
      comment,
      ...fields,
    }),
  assessment: (id: string) => http.get<RiskAssessmentV4>(`/v1/risk-assessments/${id}`),
  policies: () => http.get<any[]>("/v1/risk-policies"),
  createPolicy: (payload: Record<string, unknown>) => http.post("/v1/risk-policies", payload),
  publishPolicy: (id: string) => http.post(`/v1/risk-policies/${id}/publish`, {}),
  standardRules: () => http.get<any[]>("/v1/standard-execution-rules"),
  createStandardRule: (payload: Record<string, unknown>) =>
    http.post("/v1/standard-execution-rules", payload),
  publishStandardRule: (id: string) =>
    http.post(`/v1/standard-execution-rules/${id}/publish`, {}),
};
