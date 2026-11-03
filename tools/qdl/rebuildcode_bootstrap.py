"""Locate the shared rebuildcode package in local and Kaggle layouts."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_rebuildcode() -> None:
    here = Path(__file__).resolve().parent
    candidates = [
        here,
        here.parent,
        Path("/kaggle/input/datasets/lijc888"),
        Path.cwd(),
    ]
    for root in candidates:
        if (root / "rebuildcode").is_dir():
            value = str(root)
            if value not in sys.path:
                sys.path.insert(0, value)
            return
    raise ModuleNotFoundError(
        "无法定位 rebuildcode。请将 rebuildcode 目录与脚本一起上传，或设置 PYTHONPATH。"
    )


__all__ = ["ensure_rebuildcode"]
