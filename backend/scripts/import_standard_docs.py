from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from agent.rag.knowledge_indexer import KnowledgeIndexer


def load_jsonl(path: Path) -> list[dict]:
    docs: list[dict] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            docs.append(json.loads(line))
    return docs


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import standard docs into Qdrant")
    parser.add_argument(
        "--input",
        default="backend/scripts/standard_docs.seed.jsonl",
        help="Path to JSONL documents with fields: id(optional), title, text, source(optional)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    docs = load_jsonl(input_path)
    # 使用全局模型配置（org_id=None）或从环境变量读取指定组织
    import os
    org_id = os.environ.get("PIAP_IMPORT_ORG_ID") or None
    result = await KnowledgeIndexer(org_id=org_id).index(docs)
    output = {"input_docs": len(docs), **result}
    print(json.dumps(output, ensure_ascii=False))
    if output.get("input_docs", 0) > 0 and output.get("accepted", 0) == 0:
        raise SystemExit(
            "Import failed: all embedding requests returned empty vectors. "
            "Check PIAP_VOLCENGINE_API_KEY / PIAP_VOLCENGINE_EMBED_MODEL and endpoint access."
        )


if __name__ == "__main__":
    asyncio.run(main())
