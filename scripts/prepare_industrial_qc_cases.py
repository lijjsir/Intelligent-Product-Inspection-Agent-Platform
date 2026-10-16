"""Prepare traceable test inputs and separate ground truth; never launches platform jobs."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import sys

TOOLS = Path(__file__).resolve().parents[1] / ".codex_tmp/industrial_data_tools"
sys.path.insert(0, str(TOOLS))

import numpy as np
from PIL import Image
from pypdf import PdfReader, PdfWriter
from scipy.io import loadmat

ROOT = Path(r"D:\dataset\industrial_qc_20261004").resolve()
MVTEC = Path(r"D:\dataset\mvtec_anomaly_detection").resolve()
WORKSPACE = Path(__file__).resolve().parents[1]
EXCLUDED = {"hazelnut", "capsule", "pill"}


def path(relative):
    target = (ROOT / relative).resolve()
    if not target.is_relative_to(ROOT) or target == ROOT:
        raise ValueError("Output escaped dataset root")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def save_json(relative, data):
    path(relative).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def checksum(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_file(source, destination):
    source = Path(source).resolve()
    target = path(destination)
    if target.exists():
        if checksum(target) != checksum(source):
            raise ValueError(f"Existing file differs: {target}")
    else:
        shutil.copy2(source, target)
    return target


def write_csv(relative, rows):
    if not rows:
        raise ValueError("No measurement records")
    with path(relative).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def mvtec_cases():
    stats = []
    cases = []
    for directory in sorted(MVTEC.iterdir()):
        if not directory.is_dir() or directory.name in EXCLUDED:
            continue
        good = list((directory / "test/good").glob("*.png"))
        bad = [p for p in (directory / "test").rglob("*.png") if p.parent.name != "good"]
        missing = [str(p.relative_to(MVTEC)) for p in bad
                   if not (directory / "ground_truth" / p.parent.name / (p.stem + "_mask.png")).exists()]
        stats.append({"category": directory.name, "train": len(list((directory / "train").rglob("*.png"))),
                      "test_good": len(good), "test_abnormal": len(bad), "missing_masks": missing})
    for category in ["cable", "screw", "metal_nut", "tile", "transistor", "bottle"]:
        directory = MVTEC / category
        good = sorted((directory / "test/good").glob("*.png"))[0]
        abnormal = next(p for p in sorted((directory / "test").rglob("*.png"))
                        if p.parent.name != "good" and (directory / "ground_truth" / p.parent.name / (p.stem + "_mask.png")).exists())
        for number, source in enumerate([good, abnormal], 1):
            case_id = f"VIS_{category.upper()}_{number:02}"
            image = copy_file(source, f"05_cases/{case_id}/input/photo.png")
            is_abnormal = source.parent.name != "good"
            mask = None
            if is_abnormal:
                original_mask = directory / "ground_truth" / source.parent.name / (source.stem + "_mask.png")
                mask = copy_file(original_mask, f"06_expected/{case_id}/mask.png")
            request = {"case_id": case_id, "task_type": "image_auxiliary_inspection", "category": category,
                       "image_files": [str(image)], "objective": "检查可见外观异常，定位证据；不凭图像作全面国标合格结论。",
                       "standard_applicability": "not_established_for_this_benchmark_sample",
                       "source": "MVTec AD industrial benchmark"}
            save_json(f"05_cases/{case_id}/task_request.json", request)
            save_json(f"06_expected/{case_id}/truth.json", {
                "visible_anomaly": is_abnormal, "dataset_defect_label": source.parent.name,
                "source_image": str(source), "image_sha256": checksum(source), "mask": str(mask) if mask else None,
                "regulatory_product_conformity": "not_determined", "role": "review_only_do_not_attach_to_detection_input",
            })
            cases.append({"case_id": case_id, "type": request["task_type"], "input": str(path(f"05_cases/{case_id}/task_request.json")),
                          "expected": str(path(f"06_expected/{case_id}/truth.json"))})
    save_json("09_audit/mvtec_active_inventory.json", stats)
    return cases, stats


def kolektor_cases():
    directory = ROOT / "02_images/kolektor_sdd"
    records = []
    for image in sorted(directory.rglob("*.jpg")):
        mask = image.with_name(image.stem + "_label.bmp")
        if not mask.exists():
            continue
        with Image.open(mask) as m:
            defect = bool(np.any(np.asarray(m.convert("L")) > 0))
        records.append({"image": str(image), "mask": str(mask), "visible_anomaly": defect})
    save_json("02_images/kolektor_sdd_inventory.json", records)
    cases = []
    for number, defect in enumerate([False, True], 1):
        record = next(x for x in records if x["visible_anomaly"] == defect)
        case_id = f"VIS_KOLEKTOR_{number:02}"
        image = copy_file(record["image"], f"05_cases/{case_id}/input/photo.jpg")
        mask = copy_file(record["mask"], f"06_expected/{case_id}/mask.bmp")
        save_json(f"05_cases/{case_id}/task_request.json", {
            "case_id": case_id, "task_type": "image_auxiliary_inspection", "category": "industrial_component_surface",
            "image_files": [str(image)], "objective": "定位工业零部件表面可见异常；缺少产品标准时明确限定结论。",
            "source": "KolektorSDD original industrial images", "standard_applicability": "not_established",
        })
        save_json(f"06_expected/{case_id}/truth.json", {**record, "copied_mask": str(mask),
                  "role": "review_only_do_not_attach_to_detection_input", "regulatory_product_conformity": "not_determined"})
        cases.append({"case_id": case_id, "type": "image_auxiliary_inspection", "input": str(path(f"05_cases/{case_id}/task_request.json")),
                      "expected": str(path(f"06_expected/{case_id}/truth.json"))})
    return cases, {"images": len(records), "abnormal": sum(x["visible_anomaly"] for x in records)}


def matlab_clock(values):
    v = np.asarray(values).reshape(-1)
    return datetime(*[int(x) for x in v[:5]], 0) + timedelta(seconds=float(v[5]))


def nasa_cases():
    summaries = []
    cases = []
    for cell in ["B0005", "B0006", "B0007", "B0018"]:
        original = ROOT / f"03_measurements/nasa_raw/group1/{cell}.mat"
        battery = loadmat(original, squeeze_me=True, struct_as_record=False)[cell]
        cycles = np.atleast_1d(battery.cycle)
        capacities = []
        first_discharge = None
        for position, cycle in enumerate(cycles, 1):
            if str(cycle.type) != "discharge":
                continue
            capacity = float(cycle.data.Capacity)
            if not np.isfinite(capacity):
                continue
            capacities.append({"cell_ref": cell, "source_cycle_index": position,
                               "source_clock": matlab_clock(cycle.time).isoformat(),
                               "capacity_Ah": capacity, "ambient_temperature_C": float(cycle.ambient_temperature)})
            if first_discharge is None:
                first_discharge = (position, cycle)
        position, cycle = first_discharge
        d = cycle.data
        rows = []
        for i, (seconds, voltage, current, temperature) in enumerate(zip(
                np.atleast_1d(d.Time), np.atleast_1d(d.Voltage_measured), np.atleast_1d(d.Current_measured),
                np.atleast_1d(d.Temperature_measured))):
            if not np.all(np.isfinite([seconds, voltage, current, temperature])):
                continue
            rows.append({"event_ref": f"NASA-{cell}-cycle{position}-reading{i}", "sample_ref": cell,
                         "source_cycle_index": position, "source_clock_start": matlab_clock(cycle.time).isoformat(),
                         "relative_seconds": float(seconds), "voltage_V": float(voltage), "current_A": float(current),
                         "temperature_C": float(temperature), "time_basis": "source_clock_timezone_not_documented"})
        measurements = f"03_measurements/normalized/{cell}_first_discharge.csv"
        capacity_file = f"03_measurements/normalized/{cell}_capacity_history.csv"
        write_csv(measurements, rows)
        write_csv(capacity_file, capacities)
        summary = {"cell_ref": cell, "operations": len(cycles), "discharge_cycles": len(capacities),
                   "first_capacity_Ah": capacities[0]["capacity_Ah"], "last_capacity_Ah": capacities[-1]["capacity_Ah"],
                   "first_discharge_readings": len(rows), "raw_mat_sha256": checksum(original),
                   "experimental_eol_Ah": 1.4, "eol_source": "original NASA README experiment protocol, not a GB limit",
                   "is_ebike_battery_pack_gb_test": False, "calibration_records": "not_provided_in_this_dataset"}
        summaries.append(summary)
        case_id = f"MEAS_NASA_{cell}"
        save_json(f"05_cases/{case_id}/task_request.json", {
            "case_id": case_id, "task_type": "measurement_data_analysis", "sample_ref": cell,
            "input_files": [str(path(measurements)), str(path(capacity_file))],
            "protocol_file": str(ROOT / "03_measurements/nasa_raw/group1/README.txt"),
            "objective": "分析真实实验电芯电压、电流、温度和容量变化，按原实验协议说明衰减，指出缺失校准与场景条件。",
            "do_not_claim": "不能据此确认电动自行车电池组满足GB 43854-2024全部试验",
            "ingestion_note": "内部样品/设备ID由平台建立后分配；source_ref不是已注册平台UUID。可直接用于资料分析。",
        })
        save_json(f"06_expected/{case_id}/truth.json", summary)
        cases.append({"case_id": case_id, "type": "measurement_data_analysis", "input": str(path(f"05_cases/{case_id}/task_request.json")),
                      "expected": str(path(f"06_expected/{case_id}/truth.json"))})
    save_json("03_measurements/normalized/summary.json", summaries)
    return cases, summaries


def report_case():
    case_id = "REPORT_EBIKE_JG2128520085"
    original = ROOT / "04_reports/ebike_actual_inspection_report_JG2128520085_2021.pdf"
    reader = PdfReader(original)
    writer = PdfWriter()
    for index in range(1, 6):
        writer.add_page(reader.pages[index])
    report = path(f"05_cases/{case_id}/input/inspection_report_5pages.pdf")
    with report.open("wb") as f:
        writer.write(f)
    # Keep the full scanned photo page, with its original report locator.
    photo = reader.pages[5].images[0]
    suffix = Path(photo.name).suffix
    photo_file = path(f"05_cases/{case_id}/input/sample_photo_page{suffix}")
    photo_file.write_bytes(photo.data)
    schema = [
        ("highest_speed", "最高车速", 30.8, "km/h", "lte", 24.0, "6.1.1", 3,
         "电驱动；不得超过标称最高设计车速24km/h，且不得超过25km/h"),
        ("braking_both", "干态制动距离（两闸）", 3.8, "m", "lte", 7.0, "6.1.2", 3, "试验速度25km/h，同时使用两个车闸"),
        ("braking_rear", "干态制动距离（后闸）", 5.9, "m", "lte", 15.0, "6.1.2", 3, "试验速度25km/h，单用后闸"),
        ("whole_mass", "整车质量", 51.4, "kg", "lte", 55.0, "6.1.3", 3, "2018版；含蓄电池及说明书明示配件，不含非车载充电器"),
        ("pedal_left", "脚蹬到前轮间隙（左）", 365.0, "mm", "gte", 89.0, "6.1.6.1", 3, "按报告对应的结构项目"),
        ("pedal_right", "脚蹬到前轮间隙（右）", 370.0, "mm", "gte", 89.0, "6.1.6.1", 3, "按报告对应的结构项目"),
        ("alarm_sound", "车速提示音声压级", 60.0, "dB(A)", "range", [55.0, 62.0], "6.1.7", 4, "声压级子项；不把实测报警触发速度14.2误当必须等于15"),
        ("insulation_frame", "淋水涉水后绝缘电阻（车架）", 397.0, "MΩ", "gte", 1.0, "6.1.8", 4, "先完成报告所列淋水/涉水条件"),
        ("insulation_handle", "淋水涉水后绝缘电阻（车把）", 420.0, "MΩ", "gte", 1.0, "6.1.8", 4, "先完成报告所列淋水/涉水条件"),
        ("insulation_motor", "淋水涉水后绝缘电阻（电机外壳）", 432.0, "MΩ", "gte", 1.0, "6.1.8", 4, "先完成报告所列淋水/涉水条件"),
        ("battery_output", "蓄电池最大输出电压", 53.0, "V", "lte", 60.0, "6.3.4.2", 4, "最大输出电压，不是标称电压，不能与48V标称限制混淆"),
        ("horn_sound", "鸣号装置声压级", 73.0, "dB(A)", "range", [75.0, 100.0], "6.2.3.3", 5, "按报告声压级子项"),
    ]
    measurements = []
    candidates = []
    expected = []
    for key, title, value, unit, op, limit, clause, page, conditions in schema:
        measurements.append({"indicator_ref": key, "indicator": title, "measured_value": value, "unit": unit,
                             "report_no": "JG2128520085", "source_pdf_page": page-1,
                             "source_original_pdf_page":page,"report_printed_page":page-1})
        candidates.append({"indicator_ref": key, "indicator": title, "operator": op, "limit": limit, "unit": unit,
                           "standard_no": "GB 17761-2018", "clause": clause, "conditions": conditions,
                           "source_report_page": page-1,"source_original_pdf_page":page,
                           "page_reference":"uploaded_report_pdf", "state": "candidate_not_published",
                           "origin": "manual transcription verified against original scanned report; not claimed as automatic extraction",
                           "method_note": "报告未单列全部方法章条款，正式发布前从标准方法章匹配核对"})
        passed = value <= limit if op == "lte" else value >= limit if op == "gte" else limit[0] <= value <= limit[1]
        expected.append({"indicator_ref": key, "value": value, "matches_report_requirement": passed})
    write_csv(f"05_cases/{case_id}/input/actual_measurements.csv", measurements)
    save_json(f"05_cases/{case_id}/reference/criterion_candidates.json", candidates)
    save_json(f"05_cases/{case_id}/task_request.json", {
        "case_id": case_id, "task_type": "historical_inspection_report_review", "report_no": "JG2128520085",
        "product": {"name": "电动自行车", "brand": "速珂", "model": "TDR009Z-2Z", "production_date": "2019-08-01"},
        "inspection_date": "2021-09-03", "source_publication_year": 2021,
        "input_files": [str(report), str(photo_file), str(path(f"05_cases/{case_id}/input/actual_measurements.csv"))],
        "reference_standard": str(ROOT / "01_standards/ebike/historical/GB-17761-2018.pdf"),
        "criterion_candidates": str(path(f"05_cases/{case_id}/reference/criterion_candidates.json")),
        "objective": "以真实历史报告和对应标准核对所列项目，验证数值、单位、条件及结论；输出复核说明与缺项。",
        "limits": ["这是历史报告核对，不是对当前在售同型号新样品重新检验。", "原图照片只能支持可见信息，不能替代速度、制动和声压实测。", "候选条件需专家确认后方可发布为正式平台规则。"],
    })
    save_json(f"06_expected/{case_id}/truth.json", {
        "source_report": str(original), "source_sha256": checksum(original),
        "source_page": "https://www.qzlc.gov.cn/zwgk/qzbm/qscjdglj/zljg/202110/P020211028350036974001.pdf",
        "reported_result": "不合格", "reported_nonconforming_items": ["车速限值", "反射器、照明和鸣号装置（鸣号装置）"],
        "verified_numeric_checks": expected, "note": "数值与要求由原图人工核对；不得冒充平台已发布或新实验签发结果。",
    })
    ocr_source = WORKSPACE / "backend/runtime/industrial_data_audit/report_ocr"
    if ocr_source.exists():
        combined = []
        for page in range(2, 7):
            p = ocr_source / f"page_{page:02}.txt"
            if p.exists():
                text = p.read_text(encoding="utf-8")
                combined.append(f"\n原始PDF第{page}页 / 报告第{page-1}页\n{text}")
        path(f"05_cases/{case_id}/input/report_ocr_sidecar.txt").write_text("".join(combined), encoding="utf-8")
    return {"case_id": case_id, "type": "historical_inspection_report_review", "input": str(path(f"05_cases/{case_id}/task_request.json")),
            "expected": str(path(f"06_expected/{case_id}/truth.json"))}


def existing_standards():
    records = []
    product_files = {"GB-T-3532-2022.pdf", "GB-T-6544-2008.pdf", "GB-T-7705-2008.pdf", "GB-T-7706-2008.pdf",
                     "GB-T-7707-2008.pdf", "GB-18401-2010.pdf", "GB-T-22848-2022.pdf", "GB-T-22849-2024.pdf", "GB-T-2660-2017.pdf"}
    source = WORKSPACE / "backend/standard/current"
    for original in sorted(source.rglob("*.pdf")):
        copied = copy_file(original, "01_standards/existing_industrial/" + original.relative_to(source).as_posix())
        reader = PdfReader(original)
        texts = [(p.extract_text() or "") for p in reader.pages]
        records.append({"file": original.name, "local_copy": str(copied), "pages": len(reader.pages),
                        "sha256": checksum(original), "has_pdf_body_pages": len(reader.pages) > 2,
                        "text_layer_needs_ocr": any("/G21" in t or "/G22" in t for t in texts),
                        "role": "product_or_safety_requirements" if original.name in product_files else "method_labeling_or_general_rules",
                        "platform_executable_rules": "not_automatically_created_by_existing_indexing",
                        "effectivity": "verify per official catalogue and task date, not inferred from file name"})
    save_json("09_audit/existing_17_standard_files.json", records)
    return records


def main():
    image_cases, mvtec = mvtec_cases()
    other_cases, kolektor = kolektor_cases()
    measurement_cases, battery = nasa_cases()
    actual_report = report_case()
    standards = existing_standards()
    all_cases = [actual_report, *image_cases, *other_cases, *measurement_cases]
    save_json("case_manifest.json", all_cases)
    summary = {"root": str(ROOT), "test_cases": len(all_cases), "image_cases": len(image_cases) + len(other_cases),
               "measurement_cases": len(measurement_cases), "matched_real_report_cases": 1,
               "active_mvtec_categories": len(mvtec), "excluded_categories": sorted(EXCLUDED),
               "kolektor": kolektor, "nasa_cells": len(battery), "existing_industrial_standards": len(standards),
               "platform_tasks_launched": False, "notes": ["No measured numbers generated or replaced with synthetic values.",
                   "Truth files are separate from model input; image labels do not certify regulatory conformity.",
                   "PDF copies and archive preserve original sources and checksums."]}
    save_json("package_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
