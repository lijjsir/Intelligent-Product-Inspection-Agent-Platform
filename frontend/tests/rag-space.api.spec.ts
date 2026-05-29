import { beforeEach, describe, expect, it, vi } from "vitest";

const postMock = vi.fn();

vi.mock("@/api/http", () => ({
  http: {
    post: postMock,
  },
}));

describe("rag space api", () => {
  beforeEach(() => {
    postMock.mockReset();
  });

  it("uses extended timeout when uploading documents to a space", async () => {
    const { ragSpaceApi } = await import("@/api/rag-space.api");
    await ragSpaceApi.uploadDocuments("space-1", [new File(["demo"], "demo.docx")]);

    expect(postMock).toHaveBeenCalledWith(
      "/v1/rag-spaces/space-1/documents",
      expect.any(FormData),
      expect.objectContaining({ timeout: 180000 }),
    );
  });

  it("uses extended timeout when uploading documents to a node", async () => {
    const { ragSpaceApi } = await import("@/api/rag-space.api");
    await ragSpaceApi.uploadDocumentsToNode("space-1", "node-1", [new File(["demo"], "demo.docx")]);

    expect(postMock).toHaveBeenCalledWith(
      "/v1/rag-spaces/space-1/nodes/node-1/documents",
      expect.any(FormData),
      expect.objectContaining({ timeout: 180000 }),
    );
  });
});
