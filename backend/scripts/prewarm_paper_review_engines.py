from __future__ import annotations

import argparse
import shutil
import subprocess
import sys

from agent.tools.paper_review_macro_correct import diagnose_macro_correct
from agent.tools.paper_review_pycorrector import diagnose_pycorrector


def main() -> int:
    parser = argparse.ArgumentParser(description="Prewarm local paper review engines.")
    parser.add_argument("--vale-bin", default="vale")
    args = parser.parse_args()

    failures: list[str] = []

    pycorrector_status = diagnose_pycorrector()
    if not pycorrector_status.get("ok"):
        failures.append(f"pycorrector: {pycorrector_status.get('detail') or 'unavailable'}")
    else:
        print(f"pycorrector ready: {pycorrector_status.get('detail')}")

    macro_status = diagnose_macro_correct()
    if not macro_status.get("ok"):
        failures.append(f"macro_correct: {macro_status.get('detail') or 'unavailable'}")
    else:
        print(f"macro_correct ready: {macro_status.get('detail')}")

    vale_bin = shutil.which(args.vale_bin) or args.vale_bin
    completed = subprocess.run(
        [vale_bin, "--version"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        failures.append(f"vale: {(completed.stderr or completed.stdout).strip() or 'version check failed'}")
    else:
        print(f"vale ready: {completed.stdout.strip()}")

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
