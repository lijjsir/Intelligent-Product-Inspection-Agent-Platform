"""Install the pinned Linux Ollama runtime as the current user's service.

Run on the deployment host. Model weights and runtime are permanent data;
the verified installer archive is temporary and removed after extraction.
No sudo, driver changes, global Python packages, or system curl are needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import time
import urllib.request


VERSION = "0.40.13"
ARCHIVE_SHA256 = "c9490e0f520be21271d969e6703f012268b1d39f8b70dd58854e5bfef7a75bb6"
ARCHIVE_URL = f"https://github.com/ollama/ollama/releases/download/v{VERSION}/ollama-linux-amd64.tar.zst"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def service_text(home: Path, bind: str, context: int) -> str:
    if not re.fullmatch(r"(?:127\.0\.0\.1|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}):11434", bind):
        raise ValueError("Use a loopback or Docker private bridge address on port 11434")
    runtime = (home / ".local/lib/piap-ollama" / VERSION).as_posix()
    home_text = home.as_posix()
    return f"""[Unit]
Description=PIAP local model inference (Ollama {VERSION})
After=network.target

[Service]
ExecStart={runtime}/bin/ollama serve
WorkingDirectory={home_text}
Environment=OLLAMA_HOST={bind}
Environment=OLLAMA_MODELS={home_text}/ai_models/ollama
Environment=CUDA_VISIBLE_DEVICES=0,1
Environment=OLLAMA_CONTEXT_LENGTH={context}
Environment=OLLAMA_NUM_PARALLEL=1
Environment=OLLAMA_MAX_LOADED_MODELS=1
Environment=OLLAMA_SCHED_SPREAD=true
Environment=OLLAMA_KEEP_ALIVE=30m
Environment=OLLAMA_LOAD_TIMEOUT=10m
Environment=OLLAMA_NO_CLOUD=1
Environment=LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu
Restart=on-failure
RestartSec=5
KillMode=control-group
TimeoutStopSec=60

[Install]
WantedBy=default.target
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="172.17.0.1:11434")
    parser.add_argument("--context", type=int, default=16384)
    parser.add_argument("--archive", type=Path, help="Pre-downloaded archive with the pinned SHA256")
    args = parser.parse_args()
    if os.name != "posix" or os.uname().machine != "x86_64":
        raise SystemExit("This installer is for Linux x86_64")
    home = Path.home().resolve()
    unit = service_text(home, args.bind, args.context)
    runtime = home / ".local/lib/piap-ollama" / VERSION
    model_dir = home / "ai_models/ollama"
    model_dir.mkdir(parents=True, exist_ok=True)
    runtime.parent.mkdir(parents=True, exist_ok=True)
    if not (runtime / "bin/ollama").is_file():
        with tempfile.TemporaryDirectory(prefix="piap-ollama-install-", dir=runtime.parent) as temp:
            temp_path = Path(temp)
            archive = args.archive.resolve() if args.archive else temp_path / "ollama.tar.zst"
            if args.archive is None:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                print(f"Downloading pinned Ollama {VERSION}", flush=True)
                with opener.open(ARCHIVE_URL, timeout=60) as response, archive.open("wb") as target:
                    total = 0
                    last_report = time.monotonic()
                    while block := response.read(4 * 1024 * 1024):
                        target.write(block)
                        total += len(block)
                        if time.monotonic() - last_report > 20:
                            print(f"Runtime archive: {total // (1024 * 1024)} MiB", flush=True)
                            last_report = time.monotonic()
            if sha256(archive) != ARCHIVE_SHA256:
                raise RuntimeError("Ollama installer checksum mismatch")
            print("Runtime checksum verified; extracting", flush=True)
            # Inspect every member with Python before extracting the official archive.
            tar_stream = subprocess.Popen(["zstd", "-dc", str(archive)], stdout=subprocess.PIPE)
            with tarfile.open(fileobj=tar_stream.stdout, mode="r|") as package:
                for member in package:
                    target = (temp_path / "runtime" / member.name).resolve()
                    if not target.is_relative_to(temp_path / "runtime"):
                        raise RuntimeError("Unexpected installer archive path")
                    if member.islnk() or member.issym():
                        link = (target.parent / member.linkname).resolve()
                        if not link.is_relative_to(temp_path / "runtime"):
                            raise RuntimeError("Unexpected installer link")
            if tar_stream.wait() != 0:
                raise RuntimeError("Cannot inspect installer archive")
            stage = temp_path / "runtime"
            stage.mkdir()
            subprocess.run(["tar", "--zstd", "-xf", str(archive), "-C", str(stage)], check=True)
            if not (stage / "bin/ollama").is_file():
                raise RuntimeError("Installer did not contain bin/ollama")
            stage.rename(runtime)
    binary = runtime / "bin/ollama"
    subprocess.run([str(binary), "--version"], check=True)
    unit_path = home / ".config/systemd/user/piap-ollama.service"
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(unit, encoding="utf-8")
    env = {**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"}
    subprocess.run(["systemctl", "--user", "daemon-reload"], env=env, check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "piap-ollama.service"], env=env, check=True)
    linger = subprocess.run(["loginctl", "enable-linger", "--no-ask-password", str(os.getuid())], capture_output=True, text=True)
    print(json.dumps({"runtime": str(runtime), "models": str(model_dir), "service": str(unit_path),
                      "bind": args.bind, "linger_configured": linger.returncode == 0}), flush=True)


if __name__ == "__main__":
    main()
