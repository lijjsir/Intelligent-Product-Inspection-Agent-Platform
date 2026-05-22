export const SEVERITY_LABELS: Record<string, string> = {
  critical: "致命",
  major: "严重",
  minor: "轻微",
};

export const ALERT_SEVERITY_LABELS: Record<string, string> = {
  critical: "严重",
  error: "错误",
  warning: "警告",
  info: "提示",
};

export const SEVERITY_TAG_TYPES: Record<string, string> = {
  critical: "danger",
  major: "warning",
  minor: "info",
};

export const DISPOSITION_LABELS: Record<string, string> = {
  pass: "放行",
  fail: "拒收",
  uncertain: "待定",
  manual_required: "需人工复核",
};

/** 缺陷类型英文代码 → 中文显示名称（74条检测规则全覆盖） */
export const DEFECT_TYPE_LABELS: Record<string, string> = {
  // Global / QS-009
  crack: "裂缝",
  stain: "污渍",
  surface_scratch: "表面划痕",
  coating_defect: "涂层缺陷",

  // 食品饮料
  "food.label.additive_common_names_complete": "食品添加剂通用名称标注",
  "food.microbiology.coliform_present": "大肠菌群检出",
  "food.microbiology.salmonella_detected": "沙门氏菌检出",
  "food.packaging.leakage": "包装泄漏",
  "food.packaging.seal_integrity": "包装密封完整性",
  "food.process.traceability_record": "追溯过程记录",
  "food.traceability.qr_code_required": "追溯二维码",

  // 电子产品
  "electronics.documents.ccc_file": "CCC认证文件",
  "electronics.documents.certificate_file": "合格证书文件",
  "electronics.documents.inspection_report": "检测报告",
  "electronics.documents.traceability_code": "可追溯编码",
  "electronics.emc.conducted_emission": "传导发射",
  "electronics.emc.eft_immunity": "EFT抗扰度",
  "electronics.emc.esd_immunity": "ESD抗扰度",
  "electronics.emc.radiated_emission": "辐射发射",
  "electronics.emc.surge_immunity": "浪涌抗扰度",
  "electronics.functional.usb_output_voltage_v": "USB输出电压",
  "electronics.marking.manufacturer_address_marked": "制造商地址标识",
  "electronics.marking.rated_output_marked": "额定输出标识",
  "electronics.marking.warning_marked": "安全警示标识",
  "electronics.safety.clearance_mm": "电气间隙",
  "electronics.safety.creepage_distance_mm": "爬电距离",
  "electronics.safety.electric_strength_kv": "电气强度",
  "electronics.safety.ground_continuity_ohm": "接地连续性电阻",
  "electronics.safety.temperature_rise_max_c": "温升",
  "electronics.structure.fire_enclosure_material_grade": "防火外壳材料等级",
  "electronics.structure.sharp_edge": "外壳锋利边缘",
  "electronics.structure.socket_shutter_present": "插座保护门",

  // 汽车零部件
  "auto.exterior.paint_defect": "漆面缺陷",
  "auto.exterior.panel_gap_mm": "面板间隙",
  "auto.exterior.weld_quality": "焊点质量",
  "auto.interior.material_flame": "内饰材料阻燃等级",
  "auto.safety.airbag_marking": "安全气囊标识",
  "auto.safety.belt_anchor": "安全带固定点强度",
  "auto.documents.coc_certificate": "合格证(CoC)",
  "auto.documents.traceability_code": "追溯码",

  // 医疗器械
  "med.label.udi_code": "UDI唯一器械标识",
  "med.label.sterilization_indicator": "灭菌指示标识",
  "med.packaging.seal_integrity": "无菌包装密封完整性",
  "med.packaging.sterile_barrier": "无菌屏障",
  "med.sterility.bioburden": "生物负载",
  "med.sterility.endotoxin": "内毒素",
  "med.documents.ifu_complete": "使用说明书(IFU)",
  "med.documents.registration_cert": "医疗器械注册证",

  // 纺织品
  "textile.fabric.color_fastness": "色牢度",
  "textile.fabric.fiber_content": "纤维成分",
  "textile.fabric.pilling": "起球等级",
  "textile.label.care_instructions": "洗涤护理标识",
  "textile.label.fiber_composition": "纤维成分标识",
  "textile.stitching.seam_strength": "接缝强度",
  "textile.stitching.stitch_density": "针距密度",

  // 家电产品
  "appliance.marking.energy_label": "能效标识",
  "appliance.marking.rated_power_marked": "额定功率标识",
  "appliance.safety.ground_resistance": "接地电阻",
  "appliance.safety.leakage_current": "泄漏电流",
  "appliance.safety.insulation_resistance": "绝缘电阻",
  "appliance.functional.power_consumption": "功率偏差",
  "appliance.functional.noise_level": "噪音",

  // 包装材料
  "packaging.printing.barcode_quality": "条码印刷质量",
  "packaging.printing.label_legibility": "标签文字可辨识度",
  "packaging.printing.color_accuracy": "色差",
  "packaging.structure.drop_test": "跌落测试",
  "packaging.structure.compression_strength": "抗压强度",
  "packaging.material.thickness": "材料厚度",
  "packaging.material.recycled_content": "再生材料含量标识",

  // 瓶子
  "bottle.exterior.crack": "瓶身裂缝",
  "bottle.exterior.scratch": "瓶身划痕",
  "bottle.opening.deformation": "瓶口变形",
  "bottle.opening.thread_damage": "瓶口螺纹损伤",
  "bottle.label.missing": "标签缺失",
  "bottle.label.print_blur": "标签印刷模糊",
  "bottle.bottom.sediment": "瓶底沉淀/异物",
  "bottle.bottom.deformation": "瓶底变形",

  // 电缆
  "cable.exterior.insulation_damage": "绝缘层破损",
  "cable.exterior.scratch": "外护层划痕",
  "cable.cross_section.diameter_deviation": "线径偏差",
  "cable.cross_section.conductor_eccentricity": "导体偏心",
  "cable.marking.illegible": "标识不清",
  "cable.connector.loose": "接头松动",
  "cable.connector.corrosion": "接头腐蚀",
  "cable.safety.flame_retardant": "阻燃等级不达标",

  // 胶囊
  "capsule.exterior.crack": "胶囊壳破裂",
  "capsule.exterior.deformation": "胶囊变形",
  "capsule.exterior.color_spot": "胶囊色斑",
  "capsule.seal.leak": "胶囊封口泄漏",
  "capsule.seal.gap": "胶囊封口间隙",
  "capsule.fill.underfill": "胶囊填充不足",
  "capsule.marking.print_defect": "胶囊印花缺陷",
  "capsule.exterior.foreign_body": "胶囊外表异物",

  // 地毯
  "carpet.front.color_deviation": "正面色差",
  "carpet.front.pilling": "正面起球掉毛",
  "carpet.front.stain": "正面污渍",
  "carpet.edge.fraying": "边缘脱线",
  "carpet.edge.unsewn": "边缘未锁边",
  "carpet.back.non_slip_detach": "背面防滑层脱落",
  "carpet.back.thickness_uneven": "厚度不均",
  "carpet.label.care_missing": "护理标签缺失",
};

export function defectTypeLabel(code: string): string {
  return DEFECT_TYPE_LABELS[code] ?? code;
}

export function severityLabel(severity: string): string {
  return SEVERITY_LABELS[severity] ?? severity;
}

export function dispositionLabel(disposition: string): string {
  return DISPOSITION_LABELS[disposition] ?? disposition;
}
