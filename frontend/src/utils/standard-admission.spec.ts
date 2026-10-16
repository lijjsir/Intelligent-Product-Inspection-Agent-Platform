import {describe,expect,it} from "vitest";
import {admissionLabel,metadataDifferences} from "./standard-admission";
describe("标准准入呈现",()=>{
  it("解析完成和正式发布显示不同状态",()=>{expect(admissionLabel("parsed")).toBe("解析完成");expect(admissionLabel("unpublished")).toBe("未发布");});
  it("区分历史修订的范围变化",()=>{expect(metadataDifferences({standard_status:"现行",production_to:null},{standard_status:"被代替",production_to:"2025-08-31"}).map(i=>i.key)).toEqual(["standard_status","production_to"]);});
});
