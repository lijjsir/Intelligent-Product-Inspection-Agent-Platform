import { describe, expect, it } from "vitest";
import { normalizeAiResponseText } from "./ai-response";

describe("normalizeAiResponseText", () => {
  it("uses answer from answer-summary JSON", () => {
    const result = normalizeAiResponseText('{"answer":"可以检查论文。","summary":"功能确认"}');

    expect(result.content).toBe("可以检查论文。");
    expect(result.summary).toBe("功能确认");
  });

  it("extracts JSON from markdown blocks", () => {
    const result = normalizeAiResponseText('```json\n{"answer":"已处理","summary":"ok"}\n```');

    expect(result.content).toBe("已处理");
  });

  it("extracts answer from loose answer-summary text with raw newlines", () => {
    const result = normalizeAiResponseText(`{
      "answer": "第一段

第二段",
      "summary": "内部摘要"
    }`);

    expect(result.content).toBe("第一段\n\n第二段");
    expect(result.summary).toBe("内部摘要");
  });

  it("extracts answer from unquoted loose answer-summary objects", () => {
    const result = normalizeAiResponseText('{answer: "给用户看的内容", summary: "内部摘要"}');

    expect(result.content).toBe("给用户看的内容");
    expect(result.summary).toBe("内部摘要");
  });

  it("extracts answer from bare answer-summary text", () => {
    const result = normalizeAiResponseText("answer: 给用户看的内容\nsummary: 内部摘要");

    expect(result.content).toBe("给用户看的内容");
    expect(result.summary).toBe("内部摘要");
  });

  it("keeps plain text unchanged", () => {
    expect(normalizeAiResponseText("普通回复").content).toBe("普通回复");
  });
});
