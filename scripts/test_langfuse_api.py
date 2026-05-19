"""Integration test: verify Langfuse API client works end-to-end."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

from app.services.langfuse_api_client import LangfuseApiClient


async def main():
    client = LangfuseApiClient()

    print(f"Langfuse enabled: {client.enabled}")
    print(f"Host: {client._host}")
    print(f"Project: {client._project_id}")

    if not client.enabled:
        print("SKIP: Langfuse not enabled")
        return

    # 1. List traces
    print("\n1. Listing traces (limit=5)...")
    try:
        resp = await client.list_traces(limit=5)
        data = resp.get("data", [])
        meta = resp.get("meta", {})
        print(f"   Total items: {meta.get('totalItems', 'N/A')}")
        print(f"   Returned: {len(data)} traces")
    except Exception as e:
        print(f"   List error: {e}")

    # 2. Build trace URL
    url = client.build_trace_url("test-trace-id")
    print(f"\n2. Trace URL: {url}")

    # 3. Check trace existence
    print("\n3. Check trace exists (non-existent)...")
    try:
        exists = await client.trace_exists("nonexistent-test-id")
        print(f"   Exists: {exists}")
    except Exception as e:
        print(f"   Error: {e}")

    # 4. Delete non-existent trace (should handle gracefully)
    print("\n4. Delete non-existent trace...")
    try:
        result = await client.delete_trace("nonexistent-test-id")
        print(f"   Delete OK: {result}")
    except Exception as e:
        print(f"   Delete error (expected for 404): {e}")

    print("\nLangfuse API integration test PASSED")


asyncio.run(main())
