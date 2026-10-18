"""Local-only demo lifecycle. Does not stop or replace the normal Compose project."""
import argparse
import json
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / ".env.quality-demo"
RUNTIME = ROOT / ".codex_tmp" / "piap_quality_demo"


def setup():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if ENV.exists():
        if not (RUNTIME / "accounts.json").is_file() or not (RUNTIME / "secrets/private.pem").is_file():
            raise RuntimeError("Existing demo configuration is incomplete; restore its matching secrets instead of replacing passwords")
        return
    if (RUNTIME / "accounts.json").exists() or (RUNTIME / "secrets/private.pem").exists():
        raise RuntimeError("Existing demo secrets have no matching environment file; restore it before continuing")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    values = {name: secrets.token_hex(24) for name in (
        "QUALITY_DEMO_MYSQL_ROOT_PASSWORD", "QUALITY_DEMO_DB_PASSWORD", "QUALITY_DEMO_GOVERNANCE_SECRET",
        "QUALITY_DEMO_ADMIN_PASSWORD", "QUALITY_DEMO_ANALYST_PASSWORD", "QUALITY_DEMO_REVIEWER_PASSWORD",
    )}
    secret_dir = RUNTIME / "secrets"
    secret_dir.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (secret_dir / "private.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (secret_dir / "public.pem").write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo))
    ENV.write_text("# Generated local demo secrets. Never commit or copy to the lab server.\n" +
                   "\n".join(f"{name}={value}" for name, value in values.items()) + "\n", encoding="utf-8")
    accounts = {"url": "http://127.0.0.1:15174", "organization": "piap-quality-demo", "execution_mode": "demo",
                "accounts": [{"username": username, "role": role, "password": values[password]} for username, role, password in (
                    ("demo_admin", "admin", "QUALITY_DEMO_ADMIN_PASSWORD"),
                    ("demo_analyst", "expert", "QUALITY_DEMO_ANALYST_PASSWORD"),
                    ("demo_reviewer", "expert", "QUALITY_DEMO_REVIEWER_PASSWORD"))]}
    (RUNTIME / "accounts.json").write_text(json.dumps(accounts, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["setup", "up", "status", "stop", "seed", "seed-market"])
    args = parser.parse_args()
    if args.action in {"setup", "up"}:
        setup()
    elif not ENV.is_file():
        raise RuntimeError("The local demo is not configured; run setup or up first")
    compose = ["docker", "compose", "--env-file", str(ENV), "-f", str(ROOT / "compose.quality-demo.yml")]
    if args.action == "up":
        subprocess.run(compose + ["up", "-d", "--no-build", "--pull", "never"], cwd=ROOT, check=True)
    elif args.action == "status":
        subprocess.run(compose + ["ps"], cwd=ROOT, check=True)
    elif args.action == "stop":
        subprocess.run(compose + ["stop"], cwd=ROOT, check=True)
    elif args.action in {"seed", "seed-market"}:
        subprocess.run(compose + ["exec", "-T", "backend", "python", "scripts/init_quality_demo.py"] +
                       (["--market"] if args.action == "seed-market" else []), cwd=ROOT, check=True)
    print(json.dumps({"url": "http://127.0.0.1:15174", "credentials_file": str(RUNTIME / "accounts.json"),
                      "configuration_file": str(ENV), "project": "piap-quality-demo"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
