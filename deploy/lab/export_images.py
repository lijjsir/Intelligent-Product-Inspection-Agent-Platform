"""Export only the images used by the lab deployment to a gzip archive."""

from __future__ import annotations

import argparse
import gzip
import subprocess
from pathlib import Path


IMAGES = [
    "piap-lab-backend:current",
    "piap-lab-web:current",
    "mysql:8.0",
    "redis:7",
    "minio/minio:latest",
    "qdrant/qdrant:latest",
    "neo4j:5-community",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(["docker", "save", *IMAGES], stdout=subprocess.PIPE)
    assert process.stdout is not None
    with gzip.open(args.output, "wb", compresslevel=1) as archive:
        while chunk := process.stdout.read(1024 * 1024):
            archive.write(chunk)
    if process.wait() != 0:
        args.output.unlink(missing_ok=True)
        raise SystemExit("docker save failed")
    print(f"Images: {', '.join(IMAGES)}")
    print(f"Archive: {args.output} ({args.output.stat().st_size / (1024**3):.2f} GiB)")


if __name__ == "__main__":
    main()
