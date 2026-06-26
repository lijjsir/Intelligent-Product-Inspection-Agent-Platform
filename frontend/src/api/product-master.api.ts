import { http } from "./http";
import type {
  ProductBatch,
  ProductBatchPayload,
  ProductLine,
  ProductLinePayload,
  ProductMasterCatalog,
  ProductSku,
  ProductSkuPayload,
} from "@/types/governance.types";

export const productMasterApi = {
  catalog(includeInactive = true) {
    return http.get<ProductMasterCatalog>("/v1/product-master/catalog", {
      params: { include_inactive: includeInactive },
    });
  },
  createLine(payload: ProductLinePayload) {
    return http.post<ProductLine>("/v1/product-master/lines", payload);
  },
  updateLine(id: string, payload: Partial<ProductLinePayload>) {
    return http.patch<ProductLine>(`/v1/product-master/lines/${id}`, payload);
  },
  deleteLine(id: string) {
    return http.delete<{ success: boolean }>(`/v1/product-master/lines/${id}`);
  },
  createSku(payload: ProductSkuPayload) {
    return http.post<ProductSku>("/v1/product-master/skus", payload);
  },
  updateSku(id: string, payload: Partial<ProductSkuPayload>) {
    return http.patch<ProductSku>(`/v1/product-master/skus/${id}`, payload);
  },
  deleteSku(id: string) {
    return http.delete<{ success: boolean }>(`/v1/product-master/skus/${id}`);
  },
  createBatch(payload: ProductBatchPayload) {
    return http.post<ProductBatch>("/v1/product-master/batches", payload);
  },
  updateBatch(id: string, payload: Partial<ProductBatchPayload>) {
    return http.patch<ProductBatch>(`/v1/product-master/batches/${id}`, payload);
  },
  deleteBatch(id: string) {
    return http.delete<{ success: boolean }>(`/v1/product-master/batches/${id}`);
  },
};
