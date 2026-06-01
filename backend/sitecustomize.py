from __future__ import annotations


def _patch_transformers_adamw() -> None:
    try:
        import transformers
    except Exception:
        return

    if hasattr(transformers, "AdamW"):
        return

    try:
        import torch.optim
    except Exception:
        return

    transformers.AdamW = torch.optim.AdamW
    exports = getattr(transformers, "__all__", None)
    if isinstance(exports, list) and "AdamW" not in exports:
        exports.append("AdamW")


_patch_transformers_adamw()
