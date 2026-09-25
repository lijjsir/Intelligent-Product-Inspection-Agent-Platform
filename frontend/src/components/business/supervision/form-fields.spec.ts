import { describe, expect, it } from "vitest";
import { clearInvalidDependencies, fieldOptions, fields, type FieldOption } from "./form-fields";

const batches: FieldOption[] = [
  { value: "batch-a", label: "UNSPECIFIED", product_sku_id: "sku-a" },
  { value: "batch-b", label: "UNSPECIFIED", product_sku_id: "sku-b" },
];

describe("supervision product/batch dependencies", () => {
  it("filters duplicate batch labels by the selected product", () => {
    const batchField = fields["risk-cases"].find((field) => field.key === "batch_id");
    expect(batchField).toBeDefined();
    expect(fieldOptions(batchField!, { product_sku_id: "sku-b" }, { batches })).toEqual([
      batches[1],
    ]);
    expect(fieldOptions(batchField!, {}, { batches })).toEqual([]);
  });

  it("clears a batch when the product changes", () => {
    const riskCaseFields = fields["risk-cases"];
    const next = clearInvalidDependencies(
      { product_sku_id: "sku-b", batch_id: "batch-a" },
      "product_sku_id",
      riskCaseFields,
      { batches },
    );
    expect(next.batch_id).toBeUndefined();
  });

  it("keeps a batch that belongs to the selected product", () => {
    const riskCaseFields = fields["risk-cases"];
    const next = clearInvalidDependencies(
      { product_sku_id: "sku-a", batch_id: "batch-a" },
      "product_sku_id",
      riskCaseFields,
      { batches },
    );
    expect(next.batch_id).toBe("batch-a");
  });
});
