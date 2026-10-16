"""Collect public source assets into the user's dataset folder, without platform imports."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile

import httpx
from pypdf import PdfReader

ROOT = Path(r"D:\dataset\industrial_qc_20261004")
ASSETS = [
    {"id": "gb17761_2024", "relative_path": "01_standards/ebike/GB-17761-2024.pdf", "kind": "standard",
     "url": "https://www.jiangmen.gov.cn/attachment/0/357/357636/3235747.pdf",
     "source_page": "https://www.jiangmen.gov.cn/bmpd/jmsgyhxxhj/gxxx/zcwj/content/post_3235747.html",
     "title": "GB 17761-2024 电动自行车安全技术规范", "status_note": "官方标准平台核验为现行，2025-09-01实施"},
    {"id": "gb43854_2024", "relative_path": "01_standards/battery/GB-43854-2024.pdf", "kind": "standard",
     "url": "https://scjgj.xinjiang.gov.cn/xjaic/myzcwj/202410/d838724431184e06a886cafcc89da73f/files/%E3%80%8A%E7%94%B5%E5%8A%A8%E8%87%AA%E8%A1%8C%E8%BD%A6%E8%BD%A6%E7%94%A8%E7%A6%BB%E5%AD%90%E8%93%84%E7%94%B5%E6%B1%A0%E5%AE%89%E5%85%A8%E6%8A%80%E6%9C%AF%E8%A7%84%E8%8C%83%E3%80%8B.pdf",
     "source_page": "https://std.samr.gov.cn/gb/search/gbDetailed?id=17489E630C565995E06397BE0A0ABE8E",
     "title": "GB 43854-2024 电动自行车用锂离子蓄电池安全技术规范", "status_note": "官方标准平台核验为现行，2024-11-01实施"},
    {"id": "gb17761_2018", "relative_path": "01_standards/ebike/historical/GB-17761-2018.pdf", "kind": "historical_standard",
     "url": "https://gxj.suzhou.gov.cn/szdoc/szeic/uploadfile/ebdd5559-828c-4313-9de0-af70763bd60242d9f310-b794-4c48-adbf-bc158ad52c61.pdf",
     "source_page": "https://gxj.suzhou.gov.cn/szeic/qyfw/201806/b906ae65bd664785927c9af376c78c8e.shtml",
     "title": "GB 17761-2018 电动自行车安全技术规范", "status_note": "被2024版替代；仅供历史条件、版本比较与适用性测试"},
    {"id": "gb4351_2023", "relative_path": "01_standards/fire/GB-4351-2023.pdf", "kind": "standard",
     "url": "https://www.qhzlbz.cn/Upload/site27/ueditor/file/20260310/1773112158303984.pdf",
     "source_page": "https://www.qhzlbz.cn/article-1267-14894.html",
     "title": "GB 4351-2023 手提式灭火器", "status_note": "版本和封面需要下载后再次核对"},
    {"id": "ebike_sampling_rules_2025", "relative_path": "04_reports/2025_zhaosu_ebike_sampling_rules.pdf", "kind": "inspection_procedure",
     "url": "https://www.zhaosu.gov.cn/zsx/c113814/202509/0951d2e98c0b4a099be4eaa676c8da1c/files/2025%E5%B9%B4%E6%98%AD%E8%8B%8F%E5%8E%BF%E7%94%B5%E5%8A%A8%E8%87%AA%E8%A1%8C%E8%BD%A6%E4%BA%A7%E5%93%81%E8%B4%A8%E9%87%8F%E7%9B%91%E7%9D%A3%E6%8A%BD%E6%9F%A5%E5%AE%9E%E6%96%BD%E7%BB%86%E5%88%99.pdf",
     "source_page": "https://www.zhaosu.gov.cn/", "title": "2025年昭苏县电动自行车产品质量监督抽查实施细则",
     "status_note": "监管抽查程序资料；不冒充产品标准或原始实测报告"},
    {"id": "hunan_qc_2025", "relative_path": "04_reports/2025_hunan_industrial_nonconforming_results.pdf", "kind": "public_inspection_results",
     "url": "https://amr.hunan.gov.cn/amr/zwx/xxgkmlx/tzggx/202601/33900718/files/fac39e4f49f0411498fb5bb535b3b86a.pdf",
     "source_page": "https://amr.hunan.gov.cn/", "title": "湖南省重点工业产品质量省级监督抽查不合格产品及企业名单（2025年第5期）",
     "status_note": "官方公开抽检结果；不是原始仪器读数，不能伪造缺失数值"},
    {"id": "nasa_battery", "relative_path": "00_sources/NASA_Battery_Data_Set.zip", "kind": "measurement_dataset",
     "url": "https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip",
     "source_page": "https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/",
     "title": "NASA PCoE Battery Data Set", "status_note": "真实实验电芯时序；不等同电动自行车电池组的完整国标试验"},
    {"id": "kolektor_sdd", "relative_path": "00_sources/KolektorSDD.zip", "kind": "image_dataset",
     "url": "https://go.vicos.si/kolektorsdd",
     "source_page": "https://www.vicos.si/resources/kolektorsdd/", "title": "KolektorSDD工业表面缺陷数据集",
     "status_note": "原作者真实工业图片与分割真值；CC BY-NC-SA 4.0，科研非商业使用"},
]


def checked_path(relative: str) -> Path:
    root = ROOT.resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError("Asset path escaped the intended dataset directory")
    return target


def metadata(path: Path, spec: dict) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    result = {**spec, "local_path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest(), "download_status": "complete"}
    if path.suffix == ".pdf":
        if path.read_bytes()[:5] != b"%PDF-":
            raise ValueError("Expected PDF, received another response")
        reader = PdfReader(path)
        result["pdf_pages"] = len(reader.pages)
        result["first_page_text"] = (reader.pages[0].extract_text() or "")[:1500]
    elif not zipfile.is_zipfile(path):
        raise ValueError("Expected a ZIP archive")
    return result


def collect(spec: dict) -> dict:
    path = checked_path(spec["relative_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            result = metadata(path, spec)
            print(json.dumps({"asset": spec["id"], "status": "reused", "bytes": result["bytes"]}), flush=True)
            return result
        except Exception:
            return {**spec, "download_status": "existing_file_invalid", "local_path": str(path)}
    partial = path.with_suffix(path.suffix + ".part")
    try:
        with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(45, connect=20)) as client:
            with client.stream("GET", spec["url"]) as response:
                response.raise_for_status()
                expected = int(response.headers.get("content-length") or 0)
                count = 0
                next_notice = 32 * 1024 * 1024
                with partial.open("wb") as f:
                    for chunk in response.iter_bytes(1024 * 1024):
                        f.write(chunk)
                        count += len(chunk)
                        if count >= next_notice:
                            print(json.dumps({"asset": spec["id"], "downloaded_mb": round(count / 1024 ** 2, 1)}), flush=True)
                            next_notice += 32 * 1024 * 1024
                if expected and count != expected:
                    raise ValueError("Incomplete download")
        result = metadata(partial, spec) if path.suffix != ".pdf" else None
        # Validate actual bytes using the intended format before installing the file.
        if path.suffix == ".pdf":
            if partial.read_bytes()[:5] != b"%PDF-":
                raise ValueError("Expected PDF, received HTML or another response")
            reader = PdfReader(partial)
            if not reader.pages:
                raise ValueError("Empty PDF")
        else:
            if not zipfile.is_zipfile(partial):
                raise ValueError("Invalid ZIP archive")
        partial.replace(path)
        result = metadata(path, spec)
        print(json.dumps({"asset": spec["id"], "status": "complete", "bytes": result["bytes"], "pages": result.get("pdf_pages")}), flush=True)
        return result
    except Exception as exc:
        print(json.dumps({"asset": spec["id"], "status": "failed", "error_type": type(exc).__name__}), flush=True)
        return {**spec, "download_status": "failed", "error_type": type(exc).__name__, "local_path": str(path)}


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(collect, item): item for item in ASSETS}
        for job in as_completed(jobs):
            results.append(job.result())
            checked_path("asset_manifest.json").write_text(json.dumps(sorted(results, key=lambda x: x["id"]), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"complete": sum(x["download_status"] == "complete" for x in results), "total": len(results), "root": str(ROOT)}), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
