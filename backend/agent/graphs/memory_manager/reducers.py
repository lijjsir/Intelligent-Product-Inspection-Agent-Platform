"""Custom reducers for memory governance state fields.

Reducers do more than append — they perform structured commits:
- New memories without memory_id get one assigned by the service layer.
- Revisions preserve version_parent_id.
- Deletions set status=deleted instead of removing state entries.
- All write/read/rollback actions produce memory_events.
"""
from __future__ import annotations

from typing import Any


def memory_reducer(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge structured_memory lists by memory_id.

    - Items without memory_id are always appended.
    - Items with the same memory_id have their fields merged (newer wins).
    - Items with status=deleted/isolated are kept (not physically removed from state).
    """
    combined = list(left or [])
    existing_ids = {item["memory_id"]: idx for idx, item in enumerate(combined) if item.get("memory_id")}
    for item in right or []:
        mid = item.get("memory_id")
        if mid and mid in existing_ids:
            idx = existing_ids[mid]
            combined[idx] = {**combined[idx], **item}
        else:
            combined.append(item)
    return combined


def event_reducer(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append-only reducer for memory events. Each event has a unique event_id."""
    combined = list(left or [])
    existing_ids = {item["event_id"] for item in combined if item.get("event_id")}
    for item in right or []:
        eid = item.get("event_id")
        if eid and eid not in existing_ids:
            combined.append(item)
            existing_ids.add(eid)
        elif not eid:
            combined.append(item)
    return combined


def dependency_edge_reducer(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate dependency edges by (source_memory_id, target_memory_id, edge_type)."""
    combined = list(left or [])
    seen = {
        (e.get("source_memory_id"), e.get("target_memory_id"), e.get("edge_type"))
        for e in combined
    }
    for item in right or []:
        key = (item.get("source_memory_id"), item.get("target_memory_id"), item.get("edge_type"))
        if key not in seen:
            combined.append(item)
            seen.add(key)
    return combined
