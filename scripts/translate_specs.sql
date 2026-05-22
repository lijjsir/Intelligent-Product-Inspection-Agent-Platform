-- ==============================================
-- 翻译检测标准名称、产品线和缺陷描述为中文
-- ==============================================

-- GLOBAL-QUALITY-BASE-2026 (通用质检基线)
UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '裂缝为致命缺陷，直接判定不合格。'
WHERE s.spec_code = 'GLOBAL-QUALITY-BASE-2026' AND i.defect_type = 'crack';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '轻微污渍需人工复核。'
WHERE s.spec_code = 'GLOBAL-QUALITY-BASE-2026' AND i.defect_type = 'stain';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '显著表面划痕判定不合格。'
WHERE s.spec_code = 'GLOBAL-QUALITY-BASE-2026' AND i.defect_type = 'surface_scratch';

-- QS-009-EXAMPLE-2026 (QS-009 文档示例基线)
UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '裂缝为致命缺陷，直接判定不合格。'
WHERE s.spec_code = 'QS-009-EXAMPLE-2026' AND i.defect_type = 'crack';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '轻微污渍需人工复核。'
WHERE s.spec_code = 'QS-009-EXAMPLE-2026' AND i.defect_type = 'stain';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '显著表面划痕判定不合格。'
WHERE s.spec_code = 'QS-009-EXAMPLE-2026' AND i.defect_type = 'surface_scratch';

-- FOOD-RAG-BASE-V1 (食品结构化检测基线)
UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '食品添加剂必须使用完整通用名称标注。'
WHERE s.spec_code = 'FOOD-RAG-BASE-V1' AND i.defect_type = 'food.label.additive_common_names_complete';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '不得检出大肠菌群，检出即判定不合格。'
WHERE s.spec_code = 'FOOD-RAG-BASE-V1' AND i.defect_type = 'food.microbiology.coliform_present';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '沙门氏菌检测阳性直接判定不合格。'
WHERE s.spec_code = 'FOOD-RAG-BASE-V1' AND i.defect_type = 'food.microbiology.salmonella_detected';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '包装泄漏直接判定不合格。'
WHERE s.spec_code = 'FOOD-RAG-BASE-V1' AND i.defect_type = 'food.packaging.leakage';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '包装密封完整性缺陷直接判定不合格。'
WHERE s.spec_code = 'FOOD-RAG-BASE-V1' AND i.defect_type = 'food.packaging.seal_integrity';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '需具备完整追溯过程记录。'
WHERE s.spec_code = 'FOOD-RAG-BASE-V1' AND i.defect_type = 'food.process.traceability_record';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '需具备可扫描的追溯二维码。'
WHERE s.spec_code = 'FOOD-RAG-BASE-V1' AND i.defect_type = 'food.traceability.qr_code_required';

-- ELEC-RAG-BASE-V1 (电子产品结构化检测基线)
UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '必须提供CCC认证文件。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.documents.ccc_file';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '必须提供合格证书文件。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.documents.certificate_file';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '必须提供检测报告。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.documents.inspection_report';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '必须标注可追溯编码。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.documents.traceability_code';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '传导发射须符合限值要求。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.emc.conducted_emission';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '电快速瞬变脉冲群抗扰度须通过。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.emc.eft_immunity';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '静电放电抗扰度须通过，不得出现功能丧失。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.emc.esd_immunity';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '辐射发射须符合限值要求。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.emc.radiated_emission';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '浪涌抗扰度须通过。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.emc.surge_immunity';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 'USB输出电压须在基准范围内。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.functional.usb_output_voltage_v';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '须标注制造商地址。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.marking.manufacturer_address_marked';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '须标注额定输出参数。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.marking.rated_output_marked';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '须标注安全警示信息。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.marking.warning_marked';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '电气间隙低于基准要求。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.safety.clearance_mm';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '爬电距离低于基准要求。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.safety.creepage_distance_mm';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '电气强度须达到基准耐压要求。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.safety.electric_strength_kv';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '接地连续性电阻超出允许阈值。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.safety.ground_continuity_ohm';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '温升超出允许基准值。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.safety.temperature_rise_max_c';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '防火外壳材料等级须达到基准要求。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.structure.fire_enclosure_material_grade';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '外壳锋利边缘直接判定不合格。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.structure.sharp_edge';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '插座保护门为强制性要求。'
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.structure.socket_shutter_present';

-- SCREW-A-2026-V1 (紧固件检测基线)
UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '涂层缺陷需人工复核。'
WHERE s.spec_code = 'SCREW-A-2026-V1' AND i.defect_type = 'coating_defect';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '裂缝为致命缺陷，直接判定不合格。'
WHERE s.spec_code = 'SCREW-A-2026-V1' AND i.defect_type = 'crack';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = '表面划痕超出允许范围，判定不合格。'
WHERE s.spec_code = 'SCREW-A-2026-V1' AND i.defect_type = 'surface_scratch';

SELECT 'OK: spec items translated' AS result;
