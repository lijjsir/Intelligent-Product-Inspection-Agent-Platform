"""Create a minimal deployment archive from the current working tree.

Tracked source files are read from disk, so uncommitted code edits are included.
Local secrets, test data, models, caches, and generated files are not selected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PREFIXES = (
    "backend/app/",
    "backend/agent/",
    "backend/infra/",
    "backend/migrations/",
    "backend/requirements/",
    "backend/worker/",
    "frontend/src/",
)
SOURCE_FILES = {
    ".dockerignore",
    "backend/Dockerfile",
    "backend/Dockerfile.dockerignore",
    "backend/alembic.ini",
    "backend/main.py",
    "backend/requirements.txt",
    "backend/sitecustomize.py",
    "frontend/index.html",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/postcss.config.js",
    "frontend/tailwind.config.js",
    "frontend/tsconfig.json",
    "frontend/vite.config.ts",
    "frontend/auto-imports.d.ts",
    "frontend/components.d.ts",
    "frontend/public/piap-icon-192.png",
    "frontend/public/piap-icon-512.png",
    "frontend/public/piap-icon.svg",
    "backend/scripts/init_memory_qdrant.py",
    "backend/scripts/verify_local_quality_release.py",
    "compose.lab.yml",
    "deploy/lab/Dockerfile.frontend",
    "deploy/lab/Dockerfile.backend-hotfix",
    "deploy/lab/nginx.conf",
    "deploy/lab/init-secrets.sh",
    "deploy/lab/install-docker-ubuntu.sh",
    "deploy/lab/README.md",
}
DENIED_PARTS = {
    "tests",
    "__pycache__",
    "vendor_models",
    "paper_templates",
    "runtime",
    "runtime_uploads",
    "node_modules",
}
DENIED_NAMES = {".env", ".env.lab", "jwt_private.pem", "jwt_public.pem"}


def selected_files() -> list[str]:
    paths = set(SOURCE_FILES)
    for prefix in SOURCE_PREFIXES:
        base = ROOT / prefix
        if not base.exists():
            continue
        for source in base.rglob("*"):
            if source.is_file():
                paths.add(source.relative_to(ROOT).as_posix())
    selected: list[str] = []
    for path in sorted(paths):
        if not path:
            continue
        if path not in SOURCE_FILES and not path.startswith(SOURCE_PREFIXES):
            continue
        parts = Path(path).parts
        if any(part in DENIED_PARTS for part in parts):
            continue
        if Path(path).name in DENIED_NAMES or Path(path).name.startswith('.env') or Path(path).suffix.lower() in {'.pem','.key','.p12','.pfx'}:
            continue
        if Path(path).name.startswith('test_') or Path(path).name.endswith(('.spec.ts','.test.ts','.spec.tsx','.test.tsx')):
            continue
        source = ROOT / path
        if not source.is_file() or source.is_symlink():
            raise RuntimeError(f"Required source file is missing or is a symlink: {path}")
        if source.stat().st_size > 20 * 1024 * 1024:
            raise RuntimeError(f"Unexpected large deployment file: {path}")
        selected.append(path)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    paths = selected_files()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.output, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for path in paths:
            archive.add(ROOT / path, arcname=path, recursive=False)
    manifest={'schema':'piap-source-release-v1','archive_sha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),
        'source_kind':'current working-tree snapshot; includes uncommitted source changes',
        'contains_database':False,'contains_original_materials':False,
        'files':{path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in paths}}
    try:
        manifest['git_base']=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError,OSError):manifest['git_base']=None
    args.output.with_name(args.output.name+'.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    source_bytes = sum((ROOT / path).stat().st_size for path in paths)
    print(f"Files: {len(paths)}")
    print(f"Source size: {source_bytes / (1024 * 1024):.1f} MiB")
    print(f"Archive size: {args.output.stat().st_size / (1024 * 1024):.1f} MiB")
    print(f"Archive: {args.output}")


if __name__ == "__main__":
    main()
