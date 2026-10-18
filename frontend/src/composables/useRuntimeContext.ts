import { ref } from "vue";
import { http } from "@/api/http";

export interface RuntimeContext {
  execution_mode: "business" | "demo";
  label: string;
  notice: string | null;
  organization_slug: string | null;
  case_code: string | null;
}

const context = ref<RuntimeContext | null>(null);
const unavailable = ref(false);
let pending: Promise<void> | null = null;

async function load() {
  if (context.value) return;
  if (pending) return pending;
  pending = (async () => {
    try {
      const response = await http.get<RuntimeContext>("/v1/runtime-context", {
        suppressErrorToast: true,
      });
      const value = response.data.data;
      if (!["business", "demo"].includes(value?.execution_mode))
        throw new Error("Invalid runtime identity");
      context.value = value;
      unavailable.value = false;
    } catch {
      unavailable.value = true;
    } finally {
      pending = null;
    }
  })();
  return pending;
}

export function useRuntimeContext() {
  return { context, unavailable, load };
}
