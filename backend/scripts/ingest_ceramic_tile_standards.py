"""
将 standard/ 目录下的陶瓷产品国标 PDF 接入系统 RAG。

流程：
1. 创建 RAG Space（陶瓷产品标准库）
2. 上传 PDF → 对象存储（local/MinIO）→ 分块 → Qdrant 向量化
3. 创建 InspectionStandardLibrary 绑定 ceramic_tile → 该 RAG Space

用法：
  cd backend
  python scripts/ingest_ceramic_tile_standards.py

可选参数：
  --org-id         指定组织 ID（默认使用 UUID 全零占位）
  --user-id        指定用户 ID（默认使用 UUID 全零占位）
  --pdf-dir        PDF 所在目录（默认 ../standard）
  --product-family 产品族名称（默认 ceramic_tile）
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from starlette.datastructures import MutableHeaders, UploadFile


def _resolve_pdf_dir(raw: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute():
        # 相对于 backend 目录
        repo_root = Path(__file__).resolve().parents[1]
        candidate = (repo_root / raw).resolve()
    if not candidate.is_dir():
        raise SystemExit(f"PDF 目录不存在: {candidate}")
    return candidate


def _collect_pdfs(pdf_dir: Path) -> list[Path]:
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"{pdf_dir} 中没有找到 PDF 文件")
    print(f"发现 {len(pdfs)} 个 PDF:")
    for p in pdfs:
        print(f"  - {p.name} ({p.stat().st_size:,} bytes)")
    return pdfs


async def _main() -> None:
    parser = argparse.ArgumentParser(description="将 standard/ PDF 接入系统 RAG")
    parser.add_argument(
        "--org-id",
        default="00000000-0000-0000-0000-000000000001",
        help="组织 ID",
    )
    parser.add_argument(
        "--user-id",
        default="00000000-0000-0000-0000-000000000002",
        help="用户 ID",
    )
    parser.add_argument(
        "--pdf-dir",
        default="../standard",
        help="PDF 所在目录",
    )
    parser.add_argument(
        "--product-family",
        default="ceramic_tile",
        help="产品族名称",
    )
    parser.add_argument(
        "--space-name",
        default="陶瓷产品标准库",
        help="RAG Space 名称",
    )
    args = parser.parse_args()

    pdf_dir = _resolve_pdf_dir(args.pdf_dir)
    pdfs = _collect_pdfs(pdf_dir)
    org_id = args.org_id
    user_id = args.user_id
    product_family = args.product_family

    # 确保 backend 在 path 中
    backend_root = Path(__file__).resolve().parents[0]   # scripts/
    backend_root = backend_root.parent                   # backend/
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from app.services.rag_space_service import RagSpaceService
    from app.services.inspection_standard_library_service import InspectionStandardLibraryService
    from infra.database.session import get_session
    from app.services.object_storage.factory import build_object_storage

    async with get_session() as session:
        # ── 1. 检查是否已存在同名 RAG Space ──
        rag_service = RagSpaceService(
            session=session,
            org_id=org_id,
            user_id=user_id,
        )
        existing_spaces = await rag_service.list_spaces()
        matching = [s for s in existing_spaces if s.name == args.space_name]
        if matching:
            space = matching[0]
            print(f"复用已存在的 RAG Space: {space.name} (id={space.id})")
        else:
            space = await rag_service.create_space(
                name=args.space_name,
                description=f"陶瓷产品 ({product_family}) 国标标准文档 — 由 ingest_ceramic_tile_standards.py 自动创建",
            )
            await session.commit()
            print(f"创建 RAG Space: {space.name} (id={space.id})")

        # ── 2. 上传 PDF ──
        upload_files: list[UploadFile] = []
        for pdf_path in pdfs:
            file_obj = open(pdf_path, "rb")
            headers = MutableHeaders({"content-type": "application/pdf"})
            upload = UploadFile(
                filename=pdf_path.name,
                file=file_obj,
                headers=headers,
            )
            upload_files.append(upload)

        try:
            storage_backend = build_object_storage()
            backend_info = f"{getattr(storage_backend, 'backend_name', type(storage_backend).__name__)}"
            print(f"\n对象存储后端: {backend_info}")
            print(f"开始上传 {len(upload_files)} 个文件...")

            saved = await rag_service.upload_documents(
                rag_space_id=str(space.id),
                files=upload_files,
                parent_node_id=None,
            )
            await session.commit()

            print(f"上传完成, 共 {len(saved)} 个文档:")
            for node_resp in saved:
                print(f"  [OK] {node_resp.name} (node_id={node_resp.id})")
        finally:
            for upload in upload_files:
                if upload.file and not getattr(upload.file, 'closed', False):
                    upload.file.close()

        # ── 3. 创建 InspectionStandardLibrary 绑定 ──
        lib_service = InspectionStandardLibraryService(
            session=session,
            org_id=org_id,
        )
        # 检查是否已存在同 product_family 的绑定
        from app.models.inspection_standard_library import InspectionStandardLibrary
        from sqlalchemy import select

        stmt = select(InspectionStandardLibrary).where(
            InspectionStandardLibrary.org_id == org_id,
            InspectionStandardLibrary.product_family == product_family,
            InspectionStandardLibrary.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        existing_lib = result.scalars().first()

        if existing_lib:
            # 更新 rag_space_ids（追加不重复的）
            current_ids = list(existing_lib.rag_space_ids or [])
            if str(space.id) not in current_ids:
                current_ids.append(str(space.id))
                existing_lib.rag_space_ids = current_ids
                await session.commit()
                print(f"\n更新标准库绑定: product_family={product_family}, rag_space_ids={current_ids}")
            else:
                print(f"\n标准库绑定已存在: product_family={product_family} (无需更新)")
        else:
            payload = {
                "name": f"陶瓷产品国标库 - {product_family}",
                "product_family": product_family,
                "description": f"自动创建的陶瓷产品系统标准库, 关联 RAG Space: {args.space_name}",
                "rag_space_ids": [str(space.id)],
                "is_active": True,
            }
            await lib_service.create_item(payload)
            await session.commit()
            print(f"\n创建标准库绑定: product_family={product_family} → RAG Space {space.id}")

    print("\n[OK] 完成 - PDF 已存入对象存储, 向量已写入 Qdrant, 标准库绑定已就绪")


if __name__ == "__main__":
    asyncio.run(_main())
