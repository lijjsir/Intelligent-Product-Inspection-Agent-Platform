import { describe, expect, it } from "vitest";
import { extractApiErrorDetail, extractApiErrorMessage } from "@/api/http";

function axiosError(data: unknown, message = "Request failed") {
  return {
    isAxiosError: true,
    message,
    response: { data },
  };
}

describe("http error detail extraction", () => {
  it("extracts fail-fast error envelopes", () => {
    const detail = extractApiErrorDetail(
      axiosError({
        success: false,
        error: {
          code: "MEMORY_QDRANT_SEARCH_FAILED",
          message: "共享记忆向量检索失败",
          detail: "connection refused",
          module: "memory_vector",
          trace_id: "trace-1",
          suggestion: "检查 Qdrant",
        },
      }),
    );

    expect(detail).toEqual({
      code: "MEMORY_QDRANT_SEARCH_FAILED",
      message: "共享记忆向量检索失败",
      detail: "connection refused",
      module: "memory_vector",
      trace_id: "trace-1",
      suggestion: "检查 Qdrant",
    });
    expect(extractApiErrorMessage(axiosError({ success: false, error: detail }))).toBe("共享记忆向量检索失败");
  });

  it("extracts FastAPI detail objects", () => {
    const detail = extractApiErrorDetail(
      axiosError({
        detail: {
          error_code: "SHARED_MEMORY_INVALID_REQUEST",
          message: "missing trace_id",
          trace_id: "trace-2",
        },
      }),
    );

    expect(detail.code).toBe("SHARED_MEMORY_INVALID_REQUEST");
    expect(detail.message).toBe("missing trace_id");
    expect(detail.trace_id).toBe("trace-2");
  });

  it("falls back to axios message", () => {
    expect(extractApiErrorDetail(axiosError({}, "Network Error"))).toEqual({
      code: "UNKNOWN_ERROR",
      message: "Network Error",
    });
  });
});
