-- ==============================================
-- 修复被终端编码损坏的检测标准中文数据
-- 使用 UTF-8 HEX 直接写入，绕过终端编码问题
-- ==============================================
SET NAMES utf8mb4;

-- ELEC-RAG-BASE-V1: 电子产品结构化检测基线 / 电子产品
UPDATE inspection_specs SET
  name = 0xE794B5E5AD90E4BAA7E59381E7BB93E69E84E58C96E6A380E6B58BE59FBAE7BABF,
  product_family = 0xE794B5E5AD90E4BAA7E59381
WHERE spec_code = 'ELEC-RAG-BASE-V1';

-- FOOD-RAG-BASE-V1: 食品结构化检测基线 / 食品饮料
UPDATE inspection_specs SET
  name = 0xE9A39FE59381E7BB93E69E84E58C96E6A380E6B58BE59FBAE7BABF,
  product_family = 0xE9A39FE59381E9A5AEE69699
WHERE spec_code = 'FOOD-RAG-BASE-V1';

-- GLOBAL-QUALITY-BASE-2026: 通用质检基线 / 通用
UPDATE inspection_specs SET
  name = 0xE9809AE794A8E8B4A8E6A380E59FBAE7BABF,
  product_family = 0xE9809AE794A8
WHERE spec_code = 'GLOBAL-QUALITY-BASE-2026';

-- SCREW-A-2026-V1: 紧固件检测基线 / 紧固件
UPDATE inspection_specs SET
  name = 0xE7B4A7E59BBAE4BBB6E6A380E6B58BE59FBAE7BABF,
  product_family = 0xE7B4A7E59BBAE4BBB6
WHERE spec_code = 'SCREW-A-2026-V1';

-- QS-009-EXAMPLE-2026: QS-009 文档示例基线 / 文档示例
UPDATE inspection_specs SET
  name = 0x51532D30303920E69687E6A1A3E7A4BAE4BE8BE59FBAE7BABF,
  product_family = 0xE69687E6A1A3E7A4BAE4BE8B
WHERE spec_code = 'QS-009-EXAMPLE-2026';

-- 修复 inspection_spec_items 的描述 (受影响的是 UPDATE 过的旧 spec items)
-- GLOBAL items
UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE8A382E7BC9DE4B8BAE887B4E591BDE7BCBAE999B7EFBC8CE79BB4E68EA5E588A4E5AE9AE4B88DE59088E6A0BCE38082
WHERE s.spec_code = 'GLOBAL-QUALITY-BASE-2026' AND i.defect_type = 'crack';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE8BCBBE5BEAEE6B1A1E6B8A4E99C80E4BABAE5B7A5E5A48DE6A0B8E38082
WHERE s.spec_code = 'GLOBAL-QUALITY-BASE-2026' AND i.defect_type = 'stain';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE698BEE89197E8A1A8E99DA2E58892E79795E588A4E5AE9AE4B88DE59088E6A0BCE38082
WHERE s.spec_code = 'GLOBAL-QUALITY-BASE-2026' AND i.defect_type = 'surface_scratch';

-- QS-009 items
UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE8A382E7BC9DE4B8BAE887B4E591BDE7BCBAE999B7EFBC8CE79BB4E68EA5E588A4E5AE9AE4B88DE59088E6A0BCE38082
WHERE s.spec_code = 'QS-009-EXAMPLE-2026' AND i.defect_type = 'crack';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE8BCBBE5BEAEE6B1A1E6B8A4E99C80E4BABAE5B7A5E5A48DE6A0B8E38082
WHERE s.spec_code = 'QS-009-EXAMPLE-2026' AND i.defect_type = 'stain';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE698BEE89197E8A1A8E99DA2E58892E79795E588A4E5AE9AE4B88DE59088E6A0BCE38082
WHERE s.spec_code = 'QS-009-EXAMPLE-2026' AND i.defect_type = 'surface_scratch';

-- FOOD items
UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE9A39FE59381E6B7BBE58AA0E58982E5BF85E9A1BBE4BDBFE794A8E5AE8CE695B4E9809AE794A8E5908DE7A7B0E6A087E6B3A8E38082
WHERE s.spec_code = 'FOOD-RAG-BASE-V1' AND i.defect_type = 'food.label.additive_common_names_complete';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE4B88DE5BE97E6A380E587BAE5A4A7E882A0E88F8CE7BEA4EFBC8CE6A380E587BAE58DB3E588A4E5AE9AE4B88DE59088E6A0BCE38082
WHERE s.spec_code = 'FOOD-RAG-BASE-V1' AND i.defect_type = 'food.microbiology.coliform_present';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE6B299E997A8E6B08FE88F8CE6A380E6B58BE998B3E680A7E79BB4E68EA5E588A4E5AE9AE4B88DE59088E6A0BCE38082
WHERE s.spec_code = 'FOOD-RAG-BASE-V1' AND i.defect_type = 'food.microbiology.salmonella_detected';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE58C85E8A385E6B384E6BC8FE79BB4E68EA5E588A4E5AE9AE4B88DE59088E6A0BCE38082
WHERE s.spec_code = 'FOOD-RAG-BASE-V1' AND i.defect_type = 'food.packaging.leakage';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE58C85E8A385E5AF86E5B081E5AE8CE695B4E680A7E7BCBAE999B7E79BB4E68EA5E588A4E5AE9AE4B88DE59088E6A0BCE38082
WHERE s.spec_code = 'FOOD-RAG-BASE-V1' AND i.defect_type = 'food.packaging.seal_integrity';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE99C80E585B7E5A487E5AE8CE695B4E8BFBDE6BAAFE8BF87E7A88BE8AEB0E5BD95E38082
WHERE s.spec_code = 'FOOD-RAG-BASE-V1' AND i.defect_type = 'food.process.traceability_record';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE99C80E585B7E5A487E58FAFE689ABE68F8FE79A84E8BFBDE6BAAFE4BA8CE7BBB4E7A081E38082
WHERE s.spec_code = 'FOOD-RAG-BASE-V1' AND i.defect_type = 'food.traceability.qr_code_required';

-- ELEC items
UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE5BF85E9A1BBE68F90E4BE9B434343E8AEA4E8AF81E69687E4BBB6E38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.documents.ccc_file';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE5BF85E9A1BBE68F90E4BE9BE59088E6A0BCE8AF81E4B9A6E69687E4BBB6E38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.documents.certificate_file';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE5BF85E9A1BBE68F90E4BE9BE6A380E6B58BE68AA5E5918AE38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.documents.inspection_report';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE5BF85E9A1BBE6A087E6B3A8E58FAFE8BFBDE6BAAFE7BC96E7A081E38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.documents.traceability_code';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE4BCA0E5AFBCE58F91E5B084E9A1BBE7ACA6E59088E99990E580BCE8A681E6B182E38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.emc.conducted_emission';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE794B5E5BFABE9809FE79EACE58F98E88489E586B2E7BEA4E68A97E689B0E5BAA6E9A1BBE9809AE8BF87E38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.emc.eft_immunity';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE99D99E794B5E694BEE794B5E68A97E689B0E5BAA6E9A1BBE9809AE8BF87EFBC8CE4B88DE5BE97E587BAE78EB0E58A9FE883BDE4B8A7E5A4B1E38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.emc.esd_immunity';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE8BE90E5B084E58F91E5B084E9A1BBE7ACA6E59088E99990E580BCE8A681E6B182E38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.emc.radiated_emission';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE6B5AAE6B6AEE68A97E689B0E5BAA6E9A1BBE9809AE8BF87E38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.emc.surge_immunity';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0x555342E8BE93E587BAE794B5E58E8BE9A1BBE59CA8E59FBAE58786E88C83E59BB4E58685E38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.functional.usb_output_voltage_v';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE9A1BBE6A087E6B3A8E588B6E980A0E59586E59CB0E59D80E38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.marking.manufacturer_address_marked';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE9A1BBE6A087E6B3A8E9A29DE5AE9AE8BE93E587BAE58F82E695B0E38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.marking.rated_output_marked';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE9A1BBE6A087E6B3A8E5AE89E585A8E8ADA6E7A4BAE4BFA1E681AFE38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.marking.warning_marked';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE794B5E6B094E997B4E99A99E4BD8EE4BA8EE59FBAE58786E8A681E6B182E38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.safety.clearance_mm';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE788ACE794B5E8B79DE7A6BBE4BD8EE4BA8EE59FBAE58786E8A681E6B182E38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.safety.creepage_distance_mm';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE794B5E6B094E5BCBAE5BAA6E9A1BBE8BEBEE588B0E59FBAE58786E88090E58E8BE8A681E6B182E38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.safety.electric_strength_kv';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE68EA5E59CB0E8BF9EE7BBADE680A7E794B5E998BBE8B685E587BAE58581E8AEB8E99888E580BCE38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.safety.ground_continuity_ohm';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE6B8A9E58D87E8B685E587BAE58581E8AEB8E59FBAE58786E580BCE38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.safety.temperature_rise_max_c';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE998B2E781ABE5A496E5A3B3E69D90E69699E7AD89E7BAA7E9A1BBE8BEBEE588B0E59FBAE58786E8A681E6B182E38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.structure.fire_enclosure_material_grade';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE5A496E5A3B3E9948BE588A9E8BEB9E7BC98E79BB4E68EA5E588A4E5AE9AE4B88DE59088E6A0BCE38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.structure.sharp_edge';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE68F92E5BAA7E4BF9DE68AA4E997A8E4B8BAE5BCBAE588B6E680A7E8A681E6B182E38082
WHERE s.spec_code = 'ELEC-RAG-BASE-V1' AND i.defect_type = 'electronics.structure.socket_shutter_present';

-- SCREW items
UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE6B682E5B182E7BCBAE999B7E99C80E4BABAE5B7A5E5A48DE6A0B8E38082
WHERE s.spec_code = 'SCREW-A-2026-V1' AND i.defect_type = 'coating_defect';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE8A382E7BC9DE4B8BAE887B4E591BDE7BCBAE999B7EFBC8CE79BB4E68EA5E588A4E5AE9AE4B88DE59088E6A0BCE38082
WHERE s.spec_code = 'SCREW-A-2026-V1' AND i.defect_type = 'crack';

UPDATE inspection_spec_items i JOIN inspection_specs s ON i.spec_row_id = s.id
SET i.description = 0xE8A1A8E99DA2E58892E79795E8B685E587BAE58581E8AEB8E88C83E59BB4EFBC8CE588A4E5AE9AE4B88DE59088E6A0BCE38082
WHERE s.spec_code = 'SCREW-A-2026-V1' AND i.defect_type = 'surface_scratch';

SELECT 'OK: All encoding fixes applied' AS result;
