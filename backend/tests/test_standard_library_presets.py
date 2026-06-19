from pathlib import Path

from app.services.standard_meta_registry import STANDARD_META_REGISTRY


def test_standard_library_presets_cover_six_domains_and_seventeen_unique_pdfs():
    from app.services.standard_library_presets import STANDARD_LIBRARY_PRESETS

    assert [preset.domain for preset in STANDARD_LIBRARY_PRESETS] == [
        "日用陶瓷",
        "包装印刷",
        "包装材料",
        "纺织服装",
        "家具木制品",
        "通用质检",
    ]

    files = [file_name for preset in STANDARD_LIBRARY_PRESETS for file_name in preset.file_names]

    assert len(files) == 17
    assert len(set(files)) == 17
    assert all(file_name in STANDARD_META_REGISTRY for file_name in files)


def test_standard_library_presets_keep_document_domain_and_product_category_metadata():
    from app.services.standard_library_presets import STANDARD_LIBRARY_PRESETS

    for preset in STANDARD_LIBRARY_PRESETS:
        assert preset.library_name == f"{preset.domain}标准库"
        assert preset.rag_space_name == f"{preset.domain}标准库空间"
        assert preset.product_family
        assert preset.product_category is None

        for file_name in preset.file_names:
            meta = STANDARD_META_REGISTRY[file_name]
            assert meta["domain"] == preset.domain
            assert meta["product_category"]


def test_standard_library_presets_resolve_paths_under_base_root():
    from app.services.standard_library_presets import STANDARD_LIBRARY_PRESETS, resolve_preset_file_paths

    base_root = Path("/app/backend/standard/current")
    paths = resolve_preset_file_paths(STANDARD_LIBRARY_PRESETS, base_root=base_root)

    assert paths["日用陶瓷"] == [
        base_root / "ceramic" / "GB-T-3298-2022.pdf",
        base_root / "ceramic" / "GB-T-3301-2023.pdf",
        base_root / "ceramic" / "GB-T-3532-2022.pdf",
        base_root / "ceramic" / "GB-T-5003-2023.pdf",
    ]
    assert paths["家具木制品"] == [
        base_root / "furniture-wood" / "GB-T-10357.5-2023.pdf",
        base_root / "furniture-wood" / "GB-T-4822-2023.pdf",
        base_root / "furniture-wood" / "GB-T-4893.4-2023.pdf",
    ]
