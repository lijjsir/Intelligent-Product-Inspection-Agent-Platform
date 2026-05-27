from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.tools.paper_template_storage import (
    DEFAULT_COMMENTED_TEMPLATE_PATH,
    DEFAULT_WRITING_GUIDE_PATH,
    seed_cqupt_graduate_templates,
)
from app.services.object_storage.factory import build_object_storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed paper review templates into object storage.")
    parser.add_argument("--commented-template", type=Path, default=DEFAULT_COMMENTED_TEMPLATE_PATH)
    parser.add_argument("--writing-guide", type=Path, default=DEFAULT_WRITING_GUIDE_PATH)
    args = parser.parse_args()

    result = seed_cqupt_graduate_templates(
        storage=build_object_storage(),
        commented_template_path=args.commented_template,
        writing_guide_path=args.writing_guide,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
