"""Patch macro_correct for transformers 5.x AdamW compatibility.

This script patches macro_correct source files that import `AdamW`
from `transformers` — a class removed in transformers 5.x. The fix
injects a shim that sets `transformers.AdamW = torch.optim.AdamW`
before the affected import statements.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


FILES_TO_PATCH = [
    "macro_correct/pytorch_textcorrection/tcOffice.py",
    "macro_correct/pytorch_sequencelabeling/slOffice.py",
]

OLD_IMPORT = "from transformers import AdamW, get_linear_schedule_with_warmup, get_scheduler"
NEW_IMPORT = (
    "import torch.optim as _patch_optim\n"
    "import transformers as _patch_tf\n"
    "if not hasattr(_patch_tf, \"AdamW\"):\n"
    "    _patch_tf.AdamW = _patch_optim.AdamW\n"
    "from transformers import get_linear_schedule_with_warmup, get_scheduler"
)


def main() -> int:
    site_packages = _find_site_packages()
    if not site_packages:
        print("ERROR: could not locate site-packages", file=sys.stderr)
        return 1

    patched = 0
    for rel in FILES_TO_PATCH:
        target = site_packages / rel
        if not target.exists():
            print(f"SKIP (not found): {target}")
            continue
        content = target.read_text(encoding="utf-8")
        if OLD_IMPORT not in content:
            print(f"SKIP (no match): {target}")
            continue
        if NEW_IMPORT in content:
            print(f"SKIP (already patched): {target}")
            continue
        target.write_text(content.replace(OLD_IMPORT, NEW_IMPORT), encoding="utf-8")
        print(f"PATCHED: {target}")
        patched += 1

    if patched == 0:
        print("No files needed patching (all targets already up-to-date)")
    return 0


def _find_site_packages() -> Path | None:
    for p in sys.path:
        candidate = Path(p)
        if candidate.name == "site-packages" and candidate.is_dir():
            return candidate
    return None


if __name__ == "__main__":
    raise SystemExit(main())
