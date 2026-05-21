import { computed, ref } from "vue";
import type { Ref } from "vue";

import type { AlgoListQuery } from "@/types/algo-workspace.types";

export interface ResourceFactoryOptions<TItem, TCreatePayload, TUpdatePayload> {
  list: (query: AlgoListQuery) => Promise<any>;
  get: (id: string) => Promise<any>;
  create: (payload: TCreatePayload) => Promise<any>;
  update?: (id: string, payload: TUpdatePayload) => Promise<any>;
  remove: (id: string) => Promise<any>;
  launch?: (id: string) => Promise<any>;
  cancel?: (id: string) => Promise<any>;
  detailPath?: (id: string) => string;
}

export function createAlgoResourceStore<TItem extends { id: string; status?: string }, TCreatePayload, TUpdatePayload>(
  options: ResourceFactoryOptions<TItem, TCreatePayload, TUpdatePayload>,
) {
  const items = ref<TItem[]>([]) as Ref<TItem[]>;
  const current = ref<TItem | null>(null) as Ref<TItem | null>;
  const total = ref(0);
  const loading = ref(false);
  const count = computed(() => items.value.length);
  const detailPath = options.detailPath;

  async function fetchList(query: AlgoListQuery) {
    loading.value = true;
    try {
      const { data } = await options.list(query);
      items.value = data.data.items;
      total.value = data.data.total;
      return data.data;
    } finally {
      loading.value = false;
    }
  }

  async function fetchOne(id: string) {
    loading.value = true;
    try {
      const { data } = await options.get(id);
      current.value = data.data;
      return data.data;
    } finally {
      loading.value = false;
    }
  }

  async function createOne(payload: TCreatePayload) {
    const { data } = await options.create(payload);
    items.value.unshift(data.data);
    total.value += 1;
    return data.data as TItem;
  }

  async function updateOne(id: string, payload: TUpdatePayload) {
    if (!options.update) throw new Error("update not supported");
    const { data } = await options.update(id, payload);
    const index = items.value.findIndex((item) => item.id === id);
    if (index !== -1) {
      items.value[index] = data.data;
    }
    if (current.value?.id === id) {
      current.value = data.data;
    }
    return data.data as TItem;
  }

  async function removeOne(id: string) {
    await options.remove(id);
    items.value = items.value.filter((item) => item.id !== id);
    total.value = Math.max(0, total.value - 1);
    if (current.value?.id === id) {
      current.value = null;
    }
  }

  async function launchOne(id: string) {
    if (!options.launch) throw new Error("launch not supported");
    await options.launch(id);
    return fetchOne(id);
  }

  async function cancelOne(id: string) {
    if (!options.cancel) throw new Error("cancel not supported");
    await options.cancel(id);
    return fetchOne(id);
  }

  function $reset() {
    items.value = [];
    current.value = null;
    total.value = 0;
  }

  return {
    items,
    current,
    total,
    loading,
    count,
    fetchList,
    fetchOne,
    createOne,
    updateOne,
    removeOne,
    launchOne,
    cancelOne,
    detailPath,
    $reset,
  };
}
