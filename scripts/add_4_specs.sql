-- 瓶子、电缆、胶囊、地毯 检测标准
SET NAMES utf8mb4;
SET @now = NOW();

-- ==============================================
-- 1. 瓶子 (BOTTLE-RAG-BASE-V1)
-- ==============================================
INSERT INTO inspection_specs (id, org_id, spec_code, name, version, product_id, product_family, applicable_skus, required_views, required_image_count, ai_gate_confidence_threshold, ai_gate_evidence_threshold, ai_gate_traceability_threshold, aggregation_rules, ai_gate_rules, manual_review_policies, auto_pass_enabled, is_active, created_at, updated_at)
VALUES (UUID_TO_BIN(UUID()), NULL, 'BOTTLE-RAG-BASE-V1',
  0xE793B6E5AD90E6A380E6B58BE59FBAE7BABF, '2026.1',
  'bottle', 0xE793B6E7BD90E5AEB9E599A8,
  '["bottle"]', '["exterior", "label", "opening", "bottom"]', 3, 0.72, 0.50, 0.50,
  '{"overall": "fail_if_any_critical_else_manual_when_unmapped", "max_minor_count": 2}',
  '{"evidence": 0.5, "confidence": 0.72, "faithfulness": 0.85, "traceability": 0.5, "physical_hallucination": 0.2}',
  '{"low_evidence": "manual_required", "unmapped_defect": "manual_required", "missing_required_views": "manual_required"}',
  0, 1, @now, @now);

SET @bottle_id = (SELECT id FROM inspection_specs WHERE spec_code = 'BOTTLE-RAG-BASE-V1');

INSERT INTO inspection_spec_items (id, spec_row_id, defect_type, severity, disposition, confidence_threshold, zone_name, description, created_at, updated_at) VALUES
(UUID_TO_BIN(UUID()), @bottle_id, 'bottle.exterior.crack', 'critical', 'fail', 0.55, 'exterior', 0xE793B6E8BAABE8A382E7BC9DEFBC8CE79BB4E68EA5E588A4E5AE9AE4B88DE59088E6A0BCE38082, @now, @now),
(UUID_TO_BIN(UUID()), @bottle_id, 'bottle.exterior.scratch', 'minor', 'manual_review', 0.55, 'exterior', 0xE793B6E8BAABE58892E79795EFBC8CE99C80E4BABAE5B7A5E5A48DE6A0B8E38082, @now, @now),
(UUID_TO_BIN(UUID()), @bottle_id, 'bottle.opening.deformation', 'major', 'fail', 0.55, 'opening', 0xE793B6E58FA3E58F98E5BDA2EFBC8CE5BDB1E5938DE5AF86E5B081E680A7E38082, @now, @now),
(UUID_TO_BIN(UUID()), @bottle_id, 'bottle.opening.thread_damage', 'major', 'fail', 0.55, 'opening', 0xE793B6E58FA3E89EBAE7BAB9E68D9FE4BCA4EFBC8CE697A0E6B395E6ADA3E5B8B8E69BB4E79B96E38082, @now, @now),
(UUID_TO_BIN(UUID()), @bottle_id, 'bottle.label.missing', 'major', 'fail', 0.55, 'label', 0xE6A087E7ADBEE7BCBAE5A4B1E68896E884B1E890BDE38082, @now, @now),
(UUID_TO_BIN(UUID()), @bottle_id, 'bottle.label.print_blur', 'minor', 'manual_review', 0.55, 'label', 0xE6A087E7ADBEE58DB0E588B7E6A8A1E7B38AEFBC8CE4BFA1E681AFE4B88DE58FAFE8AFBBE38082, @now, @now),
(UUID_TO_BIN(UUID()), @bottle_id, 'bottle.bottom.sediment', 'major', 'fail', 0.55, 'bottom', 0xE793B6E5BA95E6B289E6B780E68896E5BC82E789A9E38082, @now, @now),
(UUID_TO_BIN(UUID()), @bottle_id, 'bottle.bottom.deformation', 'major', 'fail', 0.55, 'bottom', 0xE793B6E5BA95E58F98E5BDA2EFBC8CE697A0E6B395E7A8B3E5AE9AE7AB8BE694BEE38082, @now, @now);

-- ==============================================
-- 2. 电缆 (CABLE-RAG-BASE-V1)
-- ==============================================
INSERT INTO inspection_specs (id, org_id, spec_code, name, version, product_id, product_family, applicable_skus, required_views, required_image_count, ai_gate_confidence_threshold, ai_gate_evidence_threshold, ai_gate_traceability_threshold, aggregation_rules, ai_gate_rules, manual_review_policies, auto_pass_enabled, is_active, created_at, updated_at)
VALUES (UUID_TO_BIN(UUID()), NULL, 'CABLE-RAG-BASE-V1',
  0xE794B5E7BC86E6A380E6B58BE59FBAE7BABF, '2026.1',
  'cable', 0xE794B5E7BABFE794B5E7BC86,
  '["cable"]', '["exterior", "cross_section", "marking", "connector"]', 3, 0.72, 0.50, 0.50,
  '{"overall": "fail_if_any_critical_else_manual_when_unmapped", "max_minor_count": 2}',
  '{"evidence": 0.5, "confidence": 0.72, "faithfulness": 0.85, "traceability": 0.5, "physical_hallucination": 0.2}',
  '{"low_evidence": "manual_required", "unmapped_defect": "manual_required", "missing_required_views": "manual_required"}',
  0, 1, @now, @now);

SET @cable_id = (SELECT id FROM inspection_specs WHERE spec_code = 'CABLE-RAG-BASE-V1');

INSERT INTO inspection_spec_items (id, spec_row_id, defect_type, severity, disposition, confidence_threshold, zone_name, description, created_at, updated_at) VALUES
(UUID_TO_BIN(UUID()), @cable_id, 'cable.exterior.insulation_damage', 'critical', 'fail', 0.55, 'exterior', 0xE7BB9DE7BC98E5B182E7A0B4E68D9FEFBC8CE5AFBCE4BD93E8A3B8E99CB2EFBC8CE79BB4E68EA5E588A4E5AE9AE4B88DE59088E6A0BCE38082, @now, @now),
(UUID_TO_BIN(UUID()), @cable_id, 'cable.exterior.scratch', 'minor', 'manual_review', 0.55, 'exterior', 0xE5A496E68AA4E5B182E8A1A8E99DA2E58892E79795EFBC8CE99C80E4BABAE5B7A5E5A48DE6A0B8E38082, @now, @now),
(UUID_TO_BIN(UUID()), @cable_id, 'cable.cross_section.diameter_deviation', 'major', 'fail', 0.55, 'cross_section', 0xE7BABFE5BE84E5818FE5B7AEE8B685E587BAE58581E8AEB8E88C83E59BB4E38082, @now, @now),
(UUID_TO_BIN(UUID()), @cable_id, 'cable.cross_section.conductor_eccentricity', 'major', 'fail', 0.55, 'cross_section', 0xE5AFBCE4BD93E5818FE5BF83EFBC8CE7BB9DE7BC98E58E9AE5BAA6E4B88DE59D87E58C80E38082, @now, @now),
(UUID_TO_BIN(UUID()), @cable_id, 'cable.marking.illegible', 'major', 'fail', 0.55, 'marking', 0xE794B5E7BC86E6A087E8AF86E4B88DE6B885E699B0E68896E7BCBAE5A4B1E38082, @now, @now),
(UUID_TO_BIN(UUID()), @cable_id, 'cable.connector.loose', 'critical', 'fail', 0.55, 'connector', 0xE68EA5E5A4B4E69DBEE58AA8E68896E68EA5E8A7A6E4B88DE889AFE38082, @now, @now),
(UUID_TO_BIN(UUID()), @cable_id, 'cable.connector.corrosion', 'major', 'fail', 0.55, 'connector', 0xE68EA5E5A4B4E8A7A6E782B9E88590E89A80E68896E6B0A7E58C96E38082, @now, @now),
(UUID_TO_BIN(UUID()), @cable_id, 'cable.safety.flame_retardant', 'critical', 'fail', 0.55, 'exterior', 0xE998BBE78783E7AD89E7BAA7E4B88DE7ACA6E59088E8A681E6B182E38082, @now, @now);

-- ==============================================
-- 3. 胶囊 (CAPSULE-RAG-BASE-V1)
-- ==============================================
INSERT INTO inspection_specs (id, org_id, spec_code, name, version, product_id, product_family, applicable_skus, required_views, required_image_count, ai_gate_confidence_threshold, ai_gate_evidence_threshold, ai_gate_traceability_threshold, aggregation_rules, ai_gate_rules, manual_review_policies, auto_pass_enabled, is_active, created_at, updated_at)
VALUES (UUID_TO_BIN(UUID()), NULL, 'CAPSULE-RAG-BASE-V1',
  0xE883B6E59B8AE6A380E6B58BE59FBAE7BABF, '2026.1',
  'capsule', 0xE58CBBE88DAFE883B6E59B8A,
  '["capsule"]', '["exterior", "seal", "marking", "fill"]', 3, 0.72, 0.50, 0.50,
  '{"overall": "fail_if_any_critical_else_manual_when_unmapped", "max_minor_count": 2}',
  '{"evidence": 0.5, "confidence": 0.72, "faithfulness": 0.85, "traceability": 0.5, "physical_hallucination": 0.2}',
  '{"low_evidence": "manual_required", "unmapped_defect": "manual_required", "missing_required_views": "manual_required"}',
  0, 1, @now, @now);

SET @capsule_id = (SELECT id FROM inspection_specs WHERE spec_code = 'CAPSULE-RAG-BASE-V1');

INSERT INTO inspection_spec_items (id, spec_row_id, defect_type, severity, disposition, confidence_threshold, zone_name, description, created_at, updated_at) VALUES
(UUID_TO_BIN(UUID()), @capsule_id, 'capsule.exterior.crack', 'critical', 'fail', 0.55, 'exterior', 0xE883B6E59B8AE5A3B3E7A0B4E8A382EFBC8CE58685E5AEB9E789A9E6B384E6BC8FEFBC8CE79BB4E68EA5E588A4E5AE9AE4B88DE59088E6A0BCE38082, @now, @now),
(UUID_TO_BIN(UUID()), @capsule_id, 'capsule.exterior.deformation', 'major', 'fail', 0.55, 'exterior', 0xE883B6E59B8AE58F98E5BDA2E68896E5A1A9E999B7EFBC8CE5BDB1E5938DE5A496E8A782E8B4A8E9878FE38082, @now, @now),
(UUID_TO_BIN(UUID()), @capsule_id, 'capsule.exterior.color_spot', 'minor', 'manual_review', 0.55, 'exterior', 0xE883B6E59B8AE5A3B3E8A1A8E99DA2E889B2E69691E68896E882BEE782B9E38082, @now, @now),
(UUID_TO_BIN(UUID()), @capsule_id, 'capsule.seal.leak', 'critical', 'fail', 0.55, 'seal', 0xE883B6E59B8AE5B081E58FA3E4B88DE4B8A5EFBC8CE58685E5AEB9E789A9E6B384E6BC8FE38082, @now, @now),
(UUID_TO_BIN(UUID()), @capsule_id, 'capsule.seal.gap', 'major', 'fail', 0.55, 'seal', 0xE883B6E59B8AE5B081E58FA3E997B4E99A99E8B685E6A087E38082, @now, @now),
(UUID_TO_BIN(UUID()), @capsule_id, 'capsule.fill.underfill', 'critical', 'fail', 0.55, 'fill', 0xE883B6E59B8AE5A1ABE58585E9878FE4B88DE8B6B3EFBC8CE4BD8EE4BA8EE6A087E7A7B0E8A385E9878FE38082, @now, @now),
(UUID_TO_BIN(UUID()), @capsule_id, 'capsule.marking.print_defect', 'major', 'fail', 0.55, 'marking', 0xE883B6E59B8AE5A3B3E58DB0E88AB1E4B88DE6B885E38081E7BCBAE68D9FE68896E99499E4BD8DE38082, @now, @now),
(UUID_TO_BIN(UUID()), @capsule_id, 'capsule.exterior.foreign_body', 'critical', 'fail', 0.55, 'exterior', 0xE883B6E59B8AE5A496E8A782E5A4B9E69D82E5BC82E789A9E68896E6B1A1E69F93E38082, @now, @now);

-- ==============================================
-- 4. 地毯 (CARPET-RAG-BASE-V1)
-- ==============================================
INSERT INTO inspection_specs (id, org_id, spec_code, name, version, product_id, product_family, applicable_skus, required_views, required_image_count, ai_gate_confidence_threshold, ai_gate_evidence_threshold, ai_gate_traceability_threshold, aggregation_rules, ai_gate_rules, manual_review_policies, auto_pass_enabled, is_active, created_at, updated_at)
VALUES (UUID_TO_BIN(UUID()), NULL, 'CARPET-RAG-BASE-V1',
  0xE59CB0E6AFAFE6A380E6B58BE59FBAE7BABF, '2026.1',
  'carpet', 0xE7BB87E7BB87E59CB0E6AFAF,
  '["carpet"]', '["front", "back", "edge", "label"]', 3, 0.72, 0.50, 0.50,
  '{"overall": "fail_if_any_critical_else_manual_when_unmapped", "max_minor_count": 2}',
  '{"evidence": 0.5, "confidence": 0.72, "faithfulness": 0.85, "traceability": 0.5, "physical_hallucination": 0.2}',
  '{"low_evidence": "manual_required", "unmapped_defect": "manual_required", "missing_required_views": "manual_required"}',
  0, 1, @now, @now);

SET @carpet_id = (SELECT id FROM inspection_specs WHERE spec_code = 'CARPET-RAG-BASE-V1');

INSERT INTO inspection_spec_items (id, spec_row_id, defect_type, severity, disposition, confidence_threshold, zone_name, description, created_at, updated_at) VALUES
(UUID_TO_BIN(UUID()), @carpet_id, 'carpet.front.color_deviation', 'minor', 'manual_review', 0.55, 'front', 0xE59CB0E6AFAFE6ADA3E99DA2E889B2E5B7AEE8B685E587BAE5AEB9E5B7AEE88C83E59BB4E38082, @now, @now),
(UUID_TO_BIN(UUID()), @carpet_id, 'carpet.front.pilling', 'minor', 'manual_review', 0.55, 'front', 0xE59CB0E6AFAFE8A1A8E99DA2E8B5B7E79083E68896E68E89E6AF9BE38082, @now, @now),
(UUID_TO_BIN(UUID()), @carpet_id, 'carpet.front.stain', 'major', 'fail', 0.55, 'front', 0xE59CB0E6AFAFE6ADA3E99DA2E6B1A1E6B8A4E68896E889B2E69691E38082, @now, @now),
(UUID_TO_BIN(UUID()), @carpet_id, 'carpet.edge.fraying', 'major', 'fail', 0.55, 'edge', 0xE59CB0E6AFAFE8BEB9E7BC98E884B1E7BABFE68896E695A3E5BC80E38082, @now, @now),
(UUID_TO_BIN(UUID()), @carpet_id, 'carpet.edge.unsewn', 'critical', 'fail', 0.55, 'edge', 0xE59CB0E6AFAFE8BEB9E7BC98E69CAAE8A3ABE8BEB9E68896E99481E8BEB9E884B1E890BDE38082, @now, @now),
(UUID_TO_BIN(UUID()), @carpet_id, 'carpet.back.non_slip_detach', 'major', 'fail', 0.55, 'back', 0xE59CB0E6AFAFE8838CE99DA2E998B2E6BB91E5B182E884B1E890BDE68896E7BCBAE5A4B1E38082, @now, @now),
(UUID_TO_BIN(UUID()), @carpet_id, 'carpet.back.thickness_uneven', 'major', 'fail', 0.55, 'back', 0xE59CB0E6AFAFE58E9AE5BAA6E4B88DE59D87E58C80EFBC8CE5BDB1E5938DE993BAE8AEBEE58AA0E5B7A5E38082, @now, @now),
(UUID_TO_BIN(UUID()), @carpet_id, 'carpet.label.care_missing', 'major', 'fail', 0.55, 'label', 0xE59CB0E6AFAFE68AA4E79086E6A087E7ADBEE7BCBAE5A4B1E68896E4BFA1E681AFE4B88DE585A8E38082, @now, @now);

SELECT CONCAT('OK: 4 specs added, total: ', (SELECT COUNT(*) FROM inspection_specs)) AS result;
