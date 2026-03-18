import { ref } from "vue";

export function usePagination(options: { defaultSize?: number } = {}) {
  const page = ref(1);
  const pageSize = ref(options.defaultSize || 20);
  const total = ref(0);

  function onPageChange(newPage: number) {
    page.value = newPage;
  }

  function onSizeChange(newSize: number) {
    pageSize.value = newSize;
    page.value = 1; // Reset to first page
  }

  function resetPage() {
    page.value = 1;
  }

  return { page, pageSize, total, onPageChange, onSizeChange, resetPage };
}
