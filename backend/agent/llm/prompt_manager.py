from pathlib import Path


class PromptManager:
    def __init__(self, base_dir: Path):
        self._base_dir = base_dir

    def load(self, name: str) -> str:
        return (self._base_dir / name).read_text(encoding="utf-8")
