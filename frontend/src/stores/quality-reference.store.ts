import { defineStore } from "pinia";
import { ref } from "vue";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { useAuthStore } from "@/stores/auth.store";
import type { ProductCategoryV4, QualityDataSource, QualityProduct } from "@/types/quality-risk.types";

const TTL_MS = 5 * 60 * 1000;

export const useQualityReferenceStore = defineStore("quality-reference", () => {
  const auth = useAuthStore();
  const categories = ref<ProductCategoryV4[]>([]);
  const products = ref<QualityProduct[]>([]);
  const sources = ref<QualityDataSource[]>([]);
  const loadedAt = ref<Record<string, number>>({});
  let cacheIdentity = "";

  function ensureIdentity() {
    const next = `${auth.orgId}:${auth.primaryRole}`;
    if (next !== cacheIdentity) {
      cacheIdentity = next;
      categories.value = [];
      products.value = [];
      sources.value = [];
      loadedAt.value = {};
    }
  }

  function fresh(key: string) {
    return Date.now() - (loadedAt.value[key] || 0) < TTL_MS;
  }

  async function loadProducts(force = false) {
    ensureIdentity();
    if (!force && fresh("products")) return;
    const response = await qualityRiskApi.productCatalog(false);
    categories.value = response.data.data.categories;
    products.value = response.data.data.products;
    loadedAt.value.products = Date.now();
  }

  async function loadSources(force = false) {
    ensureIdentity();
    if (!force && fresh("sources")) return;
    sources.value = (await qualityRiskApi.sources()).data.data;
    loadedAt.value.sources = Date.now();
  }

  function invalidate(key?: "products" | "sources") {
    if (key) loadedAt.value[key] = 0;
    else loadedAt.value = {};
  }

  return { categories, products, sources, loadProducts, loadSources, invalidate };
});
