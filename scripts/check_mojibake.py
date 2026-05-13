from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".vue",
    ".json",
    ".md",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".css",
    ".scss",
    ".html",
    ".ps1",
}
IGNORE_PARTS = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__"}
SUSPICIOUS_TOKENS = [
    "浣犳",
    "妫€",
    "鏂颁細",
    "纭",
    "鍒涘缓",
    "璇",
    "锛",
    "銆",
]


def should_scan(path: Path) -> bool:
    if path == Path(__file__).resolve():
        return False
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    return not any(part in IGNORE_PARTS for part in path.parts)


def main() -> int:
    findings: list[tuple[str, int, str]] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or not should_scan(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append((str(path.relative_to(ROOT)), 0, "file is not valid UTF-8"))
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for token in SUSPICIOUS_TOKENS:
                if token in line:
                    findings.append((str(path.relative_to(ROOT)), lineno, line.strip()))
                    break

    if not findings:
        print("No obvious mojibake findings.")
        return 0

    print("Possible mojibake findings:")
    for file_name, lineno, line in findings:
        location = f"{file_name}:{lineno}" if lineno else file_name
        print(f"- {location} -> {line[:160]}")
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.exit(main())
