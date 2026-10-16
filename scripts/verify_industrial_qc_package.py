"""Verify collected source/data integrity and numeric review fixture without live API writes."""
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

from PIL import Image
from pypdf import PdfReader

ROOT = Path(r"D:\dataset\industrial_qc_20261004").resolve()


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    assets = load("asset_manifest.json")
    for item in assets:
        if item["download_status"] != "complete":
            continue
        assert digest(item["local_path"]) == item["sha256"], item["id"]
    cases = load("case_manifest.json")
    assert len(cases) == len({case["case_id"] for case in cases}) == 19
    checks = []
    for case in cases:
        request = json.loads(Path(case["input"]).read_text(encoding="utf-8"))
        truth = json.loads(Path(case["expected"]).read_text(encoding="utf-8"))
        for file in request.get("image_files", request.get("input_files", [])):
            assert Path(file).exists(), file
            if Path(file).suffix.lower() in {".png", ".jpg", ".jpeg"}:
                with Image.open(file) as image:
                    image.verify()
        if case["type"] == "image_auxiliary_inspection":
            assert "visible_anomaly" not in request and "dataset_defect_label" not in request
            source = truth.get("source_image", truth.get("image"))
            assert digest(request["image_files"][0]) == digest(source), case["case_id"]
        elif case["type"] == "measurement_data_analysis":
            for file in request["input_files"]:
                with Path(file).open(encoding="utf-8-sig", newline="") as f:
                    rows = list(csv.DictReader(f))
                assert rows, file
                for row in rows:
                    for key in ["relative_seconds", "voltage_V", "current_A", "temperature_C", "capacity_Ah"]:
                        if key in row:
                            assert math.isfinite(float(row[key])), (file, key)
            assert truth["is_ebike_battery_pack_gb_test"] is False
        checks.append(case["case_id"])

    case_id = "REPORT_EBIKE_JG2128520085"
    candidate_path = ROOT / f"05_cases/{case_id}/reference/criterion_candidates.json"
    candidates = json.loads(candidate_path.read_text(encoding="utf-8"))
    measurement_path = ROOT / f"05_cases/{case_id}/input/actual_measurements.csv"
    with measurement_path.open(encoding="utf-8-sig", newline="") as f:
        readings = {row["indicator_ref"]: row for row in csv.DictReader(f)}
    expected = {row["indicator_ref"]: row for row in load(f"06_expected/{case_id}/truth.json")["verified_numeric_checks"]}
    results = []
    for rule in candidates:
        row = readings[rule["indicator_ref"]]
        assert row["unit"] == rule["unit"]
        assert rule["standard_no"] == "GB 17761-2018" and rule["state"] == "candidate_not_published"
        value, limit = float(row["measured_value"]), rule["limit"]
        passed = value <= limit if rule["operator"] == "lte" else value >= limit if rule["operator"] == "gte" else limit[0] <= value <= limit[1]
        assert passed == expected[rule["indicator_ref"]]["matches_report_requirement"]
        results.append({"indicator_ref": rule["indicator_ref"], "value": value, "unit": row["unit"],
                        "matches_transcribed_report_requirement": passed, "source_pdf_page": int(row["source_pdf_page"])})
    failed = [x["indicator_ref"] for x in results if not x["matches_transcribed_report_requirement"]]
    assert failed == ["highest_speed", "horn_sound"]
    report_file = ROOT / f"05_cases/{case_id}/input/inspection_report_5pages.pdf"
    uploaded=PdfReader(report_file)
    original=PdfReader(ROOT/'04_reports/ebike_actual_inspection_report_JG2128520085_2021.pdf')
    assert len(uploaded.pages) == 5
    for rule in candidates:
        row=readings[rule['indicator_ref']];page=int(row['source_pdf_page']);raw_page=int(row['source_original_pdf_page'])
        assert 1<=page<=5 and page==rule['source_report_page'] and raw_page==page+1
        assert hashlib.sha256(uploaded.pages[page-1].images[0].data).digest()==hashlib.sha256(original.pages[raw_page-1].images[0].data).digest()
    report = {"validated_cases": len(checks), "source_hashes_verified": True, "numeric_checks": results,
              "failed_numeric_items": failed, "review_status": "awaiting_expert_review", "published": False,
              "scope": "historical report fixture verification, not new regulatory inspection",
              "platform_mutations": 0, "download_failures": [x["id"] for x in assets if x["download_status"] != "complete"]}
    out = ROOT / "07_results"
    out.mkdir(exist_ok=True)
    (out / "package_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"validated_cases": len(checks), "numeric_checks": len(results), "failed_numeric_items": failed,
                      "source_hashes_verified": True, "platform_mutations": 0, "review_status": report["review_status"]}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
