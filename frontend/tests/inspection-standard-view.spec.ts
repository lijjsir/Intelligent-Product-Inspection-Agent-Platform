import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const source = readFileSync(resolve(__dirname, "../src/views/admin/InspectionStandardLibraryView.vue"), "utf-8");

describe("InspectionStandardLibraryView standard-library fields", () => {
  it("does not expose product category as a standard-library list or form field", () => {
    expect(source).not.toContain('filters.productCategory');
    expect(source).not.toContain('productCategories');
    expect(source).not.toContain('prop="product_category" label="产品类别"');
    expect(source).not.toContain('v-model="form.product_category"');
  });

  it("keeps product category on document-level editing and retrieval filters", () => {
    expect(source).toContain('v-model="docForm.product_category"');
    expect(source).toContain('retrieveForm.productCategory');
  });
});
