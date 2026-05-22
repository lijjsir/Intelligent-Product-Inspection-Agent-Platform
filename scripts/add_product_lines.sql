-- ==============================================
-- 新增 5 条产品线检测标准及缺陷项
-- ==============================================

SET @now = NOW();

-- ==============================================
-- 1. 汽车零部件 (AUTO-RAG-BASE-V1)
-- ==============================================
INSERT INTO inspection_specs (id, org_id, spec_code, name, version, product_id, product_family, applicable_skus, required_views, required_image_count, ai_gate_confidence_threshold, ai_gate_evidence_threshold, ai_gate_traceability_threshold, aggregation_rules, ai_gate_rules, manual_review_policies, auto_pass_enabled, is_active, created_at, updated_at)
VALUES (UUID_TO_BIN(UUID()), NULL, 'AUTO-RAG-BASE-V1', '汽车零部件检测基线', '2026.1', 'auto-parts', '汽车零部件',
        '["auto-parts"]', '["exterior", "interior", "safety", "documents"]', 3, 0.72, 0.50, 0.50,
        '{"overall": "fail_if_any_critical_else_manual_when_unmapped", "max_minor_count": 2}',
        '{"evidence": 0.5, "confidence": 0.72, "faithfulness": 0.85, "traceability": 0.5, "physical_hallucination": 0.2}',
        '{"low_evidence": "manual_required", "unmapped_defect": "manual_required", "missing_required_views": "manual_required"}',
        0, 1, @now, @now);

SET @auto_id = (SELECT id FROM inspection_specs WHERE spec_code = 'AUTO-RAG-BASE-V1');

INSERT INTO inspection_spec_items (id, spec_row_id, defect_type, severity, disposition, confidence_threshold, zone_name, description, created_at, updated_at) VALUES
(UUID_TO_BIN(UUID()), @auto_id, 'auto.exterior.paint_defect', 'minor', 'manual_review', 0.55, 'exterior', '漆面缺陷需人工复核。', @now, @now),
(UUID_TO_BIN(UUID()), @auto_id, 'auto.exterior.panel_gap_mm', 'major', 'fail', 0.55, 'exterior', '面板间隙超出公差范围。', @now, @now),
(UUID_TO_BIN(UUID()), @auto_id, 'auto.exterior.weld_quality', 'critical', 'fail', 0.55, 'exterior', '焊点质量缺陷直接判定不合格。', @now, @now),
(UUID_TO_BIN(UUID()), @auto_id, 'auto.interior.material_flame', 'critical', 'fail', 0.55, 'interior', '内饰材料阻燃等级不达标。', @now, @now),
(UUID_TO_BIN(UUID()), @auto_id, 'auto.safety.airbag_marking', 'critical', 'fail', 0.55, 'safety', '安全气囊标识缺失。', @now, @now),
(UUID_TO_BIN(UUID()), @auto_id, 'auto.safety.belt_anchor', 'critical', 'fail', 0.55, 'safety', '安全带固定点强度不足。', @now, @now),
(UUID_TO_BIN(UUID()), @auto_id, 'auto.documents.coc_certificate', 'major', 'fail', 0.55, 'documents', '需提供合格证(CoC)。', @now, @now),
(UUID_TO_BIN(UUID()), @auto_id, 'auto.documents.traceability_code', 'major', 'fail', 0.55, 'documents', '追溯码缺失。', @now, @now);

-- ==============================================
-- 2. 医疗器械 (MED-DEVICE-BASE-V1)
-- ==============================================
INSERT INTO inspection_specs (id, org_id, spec_code, name, version, product_id, product_family, applicable_skus, required_views, required_image_count, ai_gate_confidence_threshold, ai_gate_evidence_threshold, ai_gate_traceability_threshold, aggregation_rules, ai_gate_rules, manual_review_policies, auto_pass_enabled, is_active, created_at, updated_at)
VALUES (UUID_TO_BIN(UUID()), NULL, 'MED-DEVICE-BASE-V1', '医疗器械检测基线', '2026.1', 'medical-device', '医疗器械',
        '["medical-device"]', '["label", "packaging", "sterility", "documents"]', 3, 0.72, 0.50, 0.50,
        '{"overall": "fail_if_any_critical_else_manual_when_unmapped", "max_minor_count": 2}',
        '{"evidence": 0.5, "confidence": 0.72, "faithfulness": 0.85, "traceability": 0.5, "physical_hallucination": 0.2}',
        '{"low_evidence": "manual_required", "unmapped_defect": "manual_required", "missing_required_views": "manual_required"}',
        0, 1, @now, @now);

SET @med_id = (SELECT id FROM inspection_specs WHERE spec_code = 'MED-DEVICE-BASE-V1');

INSERT INTO inspection_spec_items (id, spec_row_id, defect_type, severity, disposition, confidence_threshold, zone_name, description, created_at, updated_at) VALUES
(UUID_TO_BIN(UUID()), @med_id, 'med.label.udi_code', 'major', 'fail', 0.55, 'label', 'UDI唯一器械标识缺失。', @now, @now),
(UUID_TO_BIN(UUID()), @med_id, 'med.label.sterilization_indicator', 'critical', 'fail', 0.55, 'label', '灭菌指示标识缺失。', @now, @now),
(UUID_TO_BIN(UUID()), @med_id, 'med.packaging.seal_integrity', 'critical', 'fail', 0.55, 'packaging', '无菌包装密封完整性缺陷。', @now, @now),
(UUID_TO_BIN(UUID()), @med_id, 'med.packaging.sterile_barrier', 'critical', 'fail', 0.55, 'packaging', '无菌屏障破损。', @now, @now),
(UUID_TO_BIN(UUID()), @med_id, 'med.sterility.bioburden', 'critical', 'fail', 0.55, 'sterility', '生物负载超标。', @now, @now),
(UUID_TO_BIN(UUID()), @med_id, 'med.sterility.endotoxin', 'critical', 'fail', 0.55, 'sterility', '内毒素检测超标。', @now, @now),
(UUID_TO_BIN(UUID()), @med_id, 'med.documents.ifu_complete', 'major', 'fail', 0.55, 'documents', '使用说明书(IFU)不完整。', @now, @now),
(UUID_TO_BIN(UUID()), @med_id, 'med.documents.registration_cert', 'major', 'fail', 0.55, 'documents', '医疗器械注册证缺失。', @now, @now);

-- ==============================================
-- 3. 纺织品 (TEXTILE-BASE-V1)
-- ==============================================
INSERT INTO inspection_specs (id, org_id, spec_code, name, version, product_id, product_family, applicable_skus, required_views, required_image_count, ai_gate_confidence_threshold, ai_gate_evidence_threshold, ai_gate_traceability_threshold, aggregation_rules, ai_gate_rules, manual_review_policies, auto_pass_enabled, is_active, created_at, updated_at)
VALUES (UUID_TO_BIN(UUID()), NULL, 'TEXTILE-BASE-V1', '纺织品检测基线', '2026.1', 'textile', '纺织品',
        '["textile"]', '["fabric", "label", "stitching"]', 3, 0.72, 0.50, 0.50,
        '{"overall": "fail_if_any_critical_else_manual_when_unmapped", "max_minor_count": 2}',
        '{"evidence": 0.5, "confidence": 0.72, "faithfulness": 0.85, "traceability": 0.5, "physical_hallucination": 0.2}',
        '{"low_evidence": "manual_required", "unmapped_defect": "manual_required", "missing_required_views": "manual_required"}',
        0, 1, @now, @now);

SET @textile_id = (SELECT id FROM inspection_specs WHERE spec_code = 'TEXTILE-BASE-V1');

INSERT INTO inspection_spec_items (id, spec_row_id, defect_type, severity, disposition, confidence_threshold, zone_name, description, created_at, updated_at) VALUES
(UUID_TO_BIN(UUID()), @textile_id, 'textile.fabric.color_fastness', 'major', 'fail', 0.55, 'fabric', '色牢度不达标。', @now, @now),
(UUID_TO_BIN(UUID()), @textile_id, 'textile.fabric.fiber_content', 'major', 'fail', 0.55, 'fabric', '纤维成分与标识不符。', @now, @now),
(UUID_TO_BIN(UUID()), @textile_id, 'textile.fabric.pilling', 'minor', 'manual_review', 0.55, 'fabric', '起球等级超标。', @now, @now),
(UUID_TO_BIN(UUID()), @textile_id, 'textile.label.care_instructions', 'major', 'fail', 0.55, 'label', '洗涤护理标识缺失。', @now, @now),
(UUID_TO_BIN(UUID()), @textile_id, 'textile.label.fiber_composition', 'major', 'fail', 0.55, 'label', '纤维成分标识缺失。', @now, @now),
(UUID_TO_BIN(UUID()), @textile_id, 'textile.stitching.seam_strength', 'critical', 'fail', 0.55, 'stitching', '接缝强度不达标。', @now, @now),
(UUID_TO_BIN(UUID()), @textile_id, 'textile.stitching.stitch_density', 'major', 'fail', 0.55, 'stitching', '针距密度不达标。', @now, @now);

-- ==============================================
-- 4. 家电产品 (HOME-APPLIANCE-BASE-V1)
-- ==============================================
INSERT INTO inspection_specs (id, org_id, spec_code, name, version, product_id, product_family, applicable_skus, required_views, required_image_count, ai_gate_confidence_threshold, ai_gate_evidence_threshold, ai_gate_traceability_threshold, aggregation_rules, ai_gate_rules, manual_review_policies, auto_pass_enabled, is_active, created_at, updated_at)
VALUES (UUID_TO_BIN(UUID()), NULL, 'HOME-APPLIANCE-BASE-V1', '家电产品检测基线', '2026.1', 'home-appliance', '家电产品',
        '["home-appliance"]', '["marking", "safety", "functional"]', 3, 0.72, 0.50, 0.50,
        '{"overall": "fail_if_any_critical_else_manual_when_unmapped", "max_minor_count": 2}',
        '{"evidence": 0.5, "confidence": 0.72, "faithfulness": 0.85, "traceability": 0.5, "physical_hallucination": 0.2}',
        '{"low_evidence": "manual_required", "unmapped_defect": "manual_required", "missing_required_views": "manual_required"}',
        0, 1, @now, @now);

SET @appl_id = (SELECT id FROM inspection_specs WHERE spec_code = 'HOME-APPLIANCE-BASE-V1');

INSERT INTO inspection_spec_items (id, spec_row_id, defect_type, severity, disposition, confidence_threshold, zone_name, description, created_at, updated_at) VALUES
(UUID_TO_BIN(UUID()), @appl_id, 'appliance.marking.energy_label', 'major', 'fail', 0.55, 'marking', '能效标识缺失。', @now, @now),
(UUID_TO_BIN(UUID()), @appl_id, 'appliance.marking.rated_power_marked', 'major', 'fail', 0.55, 'marking', '额定功率标识缺失。', @now, @now),
(UUID_TO_BIN(UUID()), @appl_id, 'appliance.safety.ground_resistance', 'critical', 'fail', 0.55, 'safety', '接地电阻超标。', @now, @now),
(UUID_TO_BIN(UUID()), @appl_id, 'appliance.safety.leakage_current', 'critical', 'fail', 0.55, 'safety', '泄漏电流超标。', @now, @now),
(UUID_TO_BIN(UUID()), @appl_id, 'appliance.safety.insulation_resistance', 'critical', 'fail', 0.55, 'safety', '绝缘电阻不达标。', @now, @now),
(UUID_TO_BIN(UUID()), @appl_id, 'appliance.functional.power_consumption', 'major', 'fail', 0.55, 'functional', '功率偏差超标。', @now, @now),
(UUID_TO_BIN(UUID()), @appl_id, 'appliance.functional.noise_level', 'major', 'fail', 0.55, 'functional', '噪音超标。', @now, @now);

-- ==============================================
-- 5. 包装材料 (PACKAGING-BASE-V1)
-- ==============================================
INSERT INTO inspection_specs (id, org_id, spec_code, name, version, product_id, product_family, applicable_skus, required_views, required_image_count, ai_gate_confidence_threshold, ai_gate_evidence_threshold, ai_gate_traceability_threshold, aggregation_rules, ai_gate_rules, manual_review_policies, auto_pass_enabled, is_active, created_at, updated_at)
VALUES (UUID_TO_BIN(UUID()), NULL, 'PACKAGING-BASE-V1', '包装材料检测基线', '2026.1', 'packaging', '包装材料',
        '["packaging"]', '["printing", "structure", "material"]', 3, 0.72, 0.50, 0.50,
        '{"overall": "fail_if_any_critical_else_manual_when_unmapped", "max_minor_count": 2}',
        '{"evidence": 0.5, "confidence": 0.72, "faithfulness": 0.85, "traceability": 0.5, "physical_hallucination": 0.2}',
        '{"low_evidence": "manual_required", "unmapped_defect": "manual_required", "missing_required_views": "manual_required"}',
        0, 1, @now, @now);

SET @pkg_id = (SELECT id FROM inspection_specs WHERE spec_code = 'PACKAGING-BASE-V1');

INSERT INTO inspection_spec_items (id, spec_row_id, defect_type, severity, disposition, confidence_threshold, zone_name, description, created_at, updated_at) VALUES
(UUID_TO_BIN(UUID()), @pkg_id, 'packaging.printing.barcode_quality', 'major', 'fail', 0.55, 'printing', '条码印刷质量不达标。', @now, @now),
(UUID_TO_BIN(UUID()), @pkg_id, 'packaging.printing.label_legibility', 'major', 'fail', 0.55, 'printing', '标签文字可辨识度不足。', @now, @now),
(UUID_TO_BIN(UUID()), @pkg_id, 'packaging.printing.color_accuracy', 'minor', 'manual_review', 0.55, 'printing', '色差超出容差范围。', @now, @now),
(UUID_TO_BIN(UUID()), @pkg_id, 'packaging.structure.drop_test', 'critical', 'fail', 0.55, 'structure', '跌落测试破损。', @now, @now),
(UUID_TO_BIN(UUID()), @pkg_id, 'packaging.structure.compression_strength', 'critical', 'fail', 0.55, 'structure', '抗压强度不达标。', @now, @now),
(UUID_TO_BIN(UUID()), @pkg_id, 'packaging.material.thickness', 'major', 'fail', 0.55, 'material', '材料厚度偏差超标。', @now, @now),
(UUID_TO_BIN(UUID()), @pkg_id, 'packaging.material.recycled_content', 'minor', 'manual_review', 0.55, 'material', '再生材料含量标识缺失。', @now, @now);

SELECT 'OK: 5 new product lines added' AS result;
