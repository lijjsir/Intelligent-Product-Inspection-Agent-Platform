from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StandardLibraryPreset:
    domain: str
    product_family: str
    directory: str
    file_names: tuple[str, ...]
    product_category: str | None = None

    @property
    def library_name(self) -> str:
        return f"{self.domain}标准库"

    @property
    def rag_space_name(self) -> str:
        return f"{self.domain}标准库空间"


STANDARD_LIBRARY_PRESETS: tuple[StandardLibraryPreset, ...] = (
    StandardLibraryPreset(
        domain="日用陶瓷",
        product_family="ceramic",
        directory="ceramic",
        file_names=(
            "GB-T-3298-2022.pdf",
            "GB-T-3301-2023.pdf",
            "GB-T-3532-2022.pdf",
            "GB-T-5003-2023.pdf",
        ),
    ),
    StandardLibraryPreset(
        domain="包装印刷",
        product_family="printing",
        directory="printing",
        file_names=(
            "GB-T-7705-2008.pdf",
            "GB-T-7706-2008.pdf",
            "GB-T-7707-2008.pdf",
        ),
    ),
    StandardLibraryPreset(
        domain="包装材料",
        product_family="packaging",
        directory="packaging",
        file_names=("GB-T-6544-2008.pdf",),
    ),
    StandardLibraryPreset(
        domain="纺织服装",
        product_family="textile",
        directory="textile",
        file_names=(
            "GB-18401-2010.pdf",
            "GB-T-22848-2022.pdf",
            "GB-T-22849-2024.pdf",
            "GB-T-2660-2017.pdf",
            "GB-T-29862-2013.pdf",
        ),
    ),
    StandardLibraryPreset(
        domain="家具木制品",
        product_family="furniture_wood",
        directory="furniture-wood",
        file_names=(
            "GB-T-10357.5-2023.pdf",
            "GB-T-4822-2023.pdf",
            "GB-T-4893.4-2023.pdf",
        ),
    ),
    StandardLibraryPreset(
        domain="通用质检",
        product_family="common_quality",
        directory="common",
        file_names=("GB-T-8170-2008.pdf",),
    ),
)


def resolve_preset_file_paths(
    presets: tuple[StandardLibraryPreset, ...] = STANDARD_LIBRARY_PRESETS,
    *,
    base_root: str | Path,
) -> dict[str, list[Path]]:
    root = Path(base_root)
    return {preset.domain: [root / preset.directory / file_name for file_name in preset.file_names] for preset in presets}
