import { beforeEach, describe, expect, it, vi } from "vitest";

const httpMock = {
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
};

vi.mock("@/api/http", () => ({ http: httpMock }));

describe("inspectionStandardApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("uses standard library RAG endpoints", async () => {
    const { inspectionStandardApi } = await import("@/api/inspection-standard.api");

    inspectionStandardApi.list({ domain: "日用陶瓷" });
    inspectionStandardApi.scan("lib-1");
    inspectionStandardApi.index("lib-1");
    inspectionStandardApi.reindex("lib-1");
    inspectionStandardApi.listDocuments("lib-1");
    inspectionStandardApi.listChunks("doc-1");
    inspectionStandardApi.retrieve({ query: "陶瓷杯口沿裂纹是否合格", top_k: 8 });

    expect(httpMock.get).toHaveBeenCalledWith("/v1/standard-libraries", { params: { domain: "日用陶瓷" } });
    expect(httpMock.post).toHaveBeenCalledWith("/v1/standard-libraries/lib-1/scan");
    expect(httpMock.post).toHaveBeenCalledWith("/v1/standard-libraries/lib-1/index");
    expect(httpMock.post).toHaveBeenCalledWith("/v1/standard-libraries/lib-1/reindex");
    expect(httpMock.get).toHaveBeenCalledWith("/v1/standard-libraries/lib-1/documents");
    expect(httpMock.get).toHaveBeenCalledWith("/v1/standard-documents/doc-1/chunks");
    expect(httpMock.post).toHaveBeenCalledWith("/v1/standards/retrieve", {
      query: "陶瓷杯口沿裂纹是否合格",
      top_k: 8,
    });
  });
});
