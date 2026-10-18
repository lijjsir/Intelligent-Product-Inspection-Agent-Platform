import { http } from "./http";
import type { PagedResponse } from "@/types/common.types";
import type {
  ProductCategoryV4,
  QualityAttachment,
  QualityDataSource,
  QualityProduct,
  QualityProductCandidate,
  QualityProductionBatch,
  QualityProductLinks,
  QualitySourceRecord,
  RiskAssessmentV4,
  RiskCaseV4,
  RiskWorkspace,
  DemoRiskContent,
  IntakeReferenceOptions,
  QualityRecordContext,
} from "@/types/quality-risk.types";

export const qualityRiskApi = {
  productOptions: () =>
    http.get<{
      categories: Pick<ProductCategoryV4, "id" | "org_id" | "code" | "name" | "is_active">[];
      products: Pick<
        QualityProduct,
        "id" | "org_id" | "category_id" | "name" | "model" | "brand" | "is_active"
      >[];
    }>("/v1/quality-products/options"),
  productBatchOptions: (productId: string) =>
    http.get<QualityProductionBatch[]>(`/v1/quality-products/${productId}/batch-options`),
  previewCategoryImport: (file: File, commonBasis: string) => {
    const form = new FormData();
    form.append("file", file);
    if (commonBasis.trim()) form.append("common_basis", commonBasis.trim());
    return http.post<{
      rows: Array<{ name: string; classification_basis: string | null }>;
      errors: Array<{ row: number; message: string }>;
      valid_count: number;
      can_confirm: boolean;
    }>("/v1/quality-products/categories/imports/preview", form);
  },
  confirmCategoryImport: (rows: Array<{ name: string; classification_basis: string | null }>) =>
    http.post<{ created_count: number; reused_count: number }>(
      "/v1/quality-products/categories/imports/confirm",
      { rows },
    ),
  productCatalog: (includeInactive = false) =>
    http.get<{ categories: ProductCategoryV4[]; products: QualityProduct[] }>(
      "/v1/quality-products/catalog",
      { params: { include_inactive: includeInactive } },
    ),
  createCategory: (payload: Record<string, unknown>) =>
    http.post<ProductCategoryV4>("/v1/quality-products/categories", payload),
  updateCategory: (id: string, payload: Record<string, unknown>) =>
    http.patch<ProductCategoryV4>(`/v1/quality-products/categories/${id}`, payload),
  deleteCategory: (id: string) =>
    http.delete<{ deleted: boolean }>(`/v1/quality-products/categories/${id}`),
  createProduct: (payload: Record<string, unknown>) =>
    http.post<QualityProduct>("/v1/quality-products", payload),
  productCandidates: (params: Record<string, unknown>) =>
    http.get<QualityProductCandidate[]>("/v1/quality-products/duplicate-candidates", { params }),
  updateProduct: (id: string, payload: Record<string, unknown>) =>
    http.patch<QualityProduct>(`/v1/quality-products/${id}`, payload),
  deleteProduct: (id: string) => http.delete<{ deleted: boolean }>(`/v1/quality-products/${id}`),
  deleteEnterprise: (id: string) => http.delete<{ deleted: boolean }>(`/v1/enterprises/${id}`),
  deleteProductionBatch: (productId: string, batchId: string) =>
    http.delete<{ deleted: boolean }>(`/v1/quality-products/${productId}/batches/${batchId}`),
  productBatches: (productId: string) =>
    http.get<QualityProductionBatch[]>(`/v1/quality-products/${productId}/batches`),
  createProductionBatch: (productId: string, payload: Record<string, unknown>) =>
    http.post<QualityProductionBatch>(`/v1/quality-products/${productId}/batches`, payload),
  updateProductionBatch: (productId: string, batchId: string, payload: Record<string, unknown>) =>
    http.patch<QualityProductionBatch>(
      `/v1/quality-products/${productId}/batches/${batchId}`,
      payload,
    ),
  productLinks: (productId: string, batchId?: string) =>
    http.get<QualityProductLinks>(`/v1/quality-products/${productId}/links`, {
      params: { batch_id: batchId || undefined },
    }),
  sources: () => http.get<QualityDataSource[]>("/v1/quality-data/sources"),
  createSource: (payload: Record<string, unknown>) =>
    http.post<QualityDataSource>("/v1/quality-data/sources", payload),
  updateSource: (id: string, payload: Record<string, unknown>) =>
    http.patch<QualityDataSource>(`/v1/quality-data/sources/${id}`, payload),
  records: (params: Record<string, unknown> = {}) =>
    http.get<PagedResponse<QualitySourceRecord>>("/v1/quality-data/records", {
      params,
      paramsSerializer: { indexes: null },
    }),
  reverseGeocode: (latitude: number, longitude: number) =>
    http.get<{
      formatted_address: string;
      province: string;
      city: string;
      district: string;
      provider: string;
    }>("/v1/quality-data/locations/reverse-geocode", {
      params: { latitude, longitude },
      suppressErrorToast: true,
    }),
  record: (id: string) => http.get<QualitySourceRecord>(`/v1/quality-data/records/${id}`),
  recordContext: (id: string) =>
    http.get<QualityRecordContext>(`/v1/quality-data/records/${id}/context`),
  updateRecordObjects: (
    id: string,
    payload: {
      enterprise_id: string | null;
      product_id: string | null;
      category_id: string | null;
      expected_version: number;
      reason: string;
    },
  ) => http.patch<QualitySourceRecord>(`/v1/quality-data/records/${id}/objects`, payload),
  intakeReferences: (keyword = "") =>
    http.get<IntakeReferenceOptions>("/v1/quality-data/reference-options", { params: { keyword } }),
  evidence: (id: string) => http.get<any[]>(`/v1/quality-data/records/${id}/evidence`),
  createEvent: (payload: Record<string, unknown>) =>
    http.post<QualitySourceRecord>("/v1/quality-data/events", payload),
  uploadAttachments: (files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return http.post<QualityAttachment[]>("/v1/quality-data/attachments", form);
  },
  attachment: (id: string) => http.get<QualityAttachment>(`/v1/quality-data/attachments/${id}`),
  downloadAttachment: (id: string) =>
    http.get<Blob>(`/v1/quality-data/attachments/${id}/download`, { responseType: "blob" }),
  previewImport: (
    sourceId: string | null,
    requestKey: string,
    file: File,
    mapping = {},
    originLabel: string | null = null,
    recordType?: string,
  ) => {
    const form = new FormData();
    if (sourceId) form.append("source_id", sourceId);
    if (originLabel) form.append("origin_label", originLabel);
    if (recordType) form.append("record_type", recordType);
    form.append("request_key", requestKey);
    form.append("mapping", JSON.stringify(mapping));
    form.append("file", file);
    return http.post<any>("/v1/quality-data/imports", form);
  },
  importTemplate: () =>
    http.get<Blob>("/v1/quality-data/import-template", { responseType: "blob" }),
  confirmImport: (id: string) => http.post<any>(`/v1/quality-data/imports/${id}/confirm`, {}),
  cancelImport: (id: string) => http.post(`/v1/quality-data/imports/${id}/cancel`, {}),
  riskCases: (params: Record<string, unknown> = {}) =>
    http.get<PagedResponse<RiskCaseV4>>("/v1/risk-cases", { params }),
  createRiskCase: (payload: Record<string, unknown>) =>
    http.post<RiskCaseV4>("/v1/risk-cases", payload),
  riskWorkspace: (id: string) => http.get<RiskWorkspace>(`/v1/risk-cases/${id}/workspace`),
  createDemoDraft: (
    id: string,
    payload: {
      base_assessment_id: string | null;
      expected_basis_hash: string;
      request_key: string;
    },
  ) =>
    http.post<RiskAssessmentV4>(`/v1/risk-cases/${id}/demo-drafts`, payload, {
      suppressErrorToast: true,
    }),
  saveDemoDraft: (id: string, assessmentId: string, revision: number, content: DemoRiskContent) =>
    http.patch<RiskAssessmentV4>(
      `/v1/risk-cases/${id}/demo-drafts/${assessmentId}`,
      { expected_revision: revision, content },
      { suppressErrorToast: true },
    ),
  submitDemoDraft: (id: string, assessmentId: string, revision: number) =>
    http.post<RiskAssessmentV4>(
      `/v1/risk-cases/${id}/demo-drafts/${assessmentId}/submit`,
      { expected_revision: revision },
      { suppressErrorToast: true },
    ),
  reviewDemoDraft: (
    id: string,
    assessmentId: string,
    revision: number,
    decision: "approve" | "revise" | "request_evidence",
    comment: string,
  ) =>
    http.post<RiskAssessmentV4>(
      `/v1/risk-cases/${id}/demo-drafts/${assessmentId}/review`,
      { expected_revision: revision, decision, comment },
      { suppressErrorToast: true },
    ),
  appendRiskSources: (id: string, sourceRecordIds: string[]) =>
    http.post<RiskCaseV4>(`/v1/risk-cases/${id}/sources`, { source_record_ids: sourceRecordIds }),
  analyzeRisk: (id: string, policyId?: string, inspectionExecutionRunId?: string) =>
    http.post<RiskAssessmentV4>(`/v1/risk-cases/${id}/analyze`, {
      policy_id: policyId || null,
      inspection_execution_run_id: inspectionExecutionRunId || null,
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
  publishStandardRule: (id: string) => http.post(`/v1/standard-execution-rules/${id}/publish`, {}),
};
