"""In-memory store of merge records for the conflict/diff view (FR-MERGE-2)."""
from __future__ import annotations

import uuid

_MERGES: dict[str, dict] = {}


def create(target_slug: str, before: str, after: str,
           conflicts: list[str], sources: list[str], relation: str = "",
           policy: str = "", status: str = "pending") -> str:
    mid = uuid.uuid4().hex[:8]
    _MERGES[mid] = {
        "id": mid, "target_slug": target_slug,
        "before": before, "after": after,
        "conflicts": conflicts, "sources": sources,
        "relation": relation, "policy": policy, "status": status,
    }
    return mid


def get(mid: str) -> dict | None:
    return _MERGES.get(mid)


def list_all() -> list[dict]:
    return [{"id": m["id"], "target_slug": m["target_slug"],
             "status": m["status"], "conflicts": len(m["conflicts"]),
             "relation": m.get("relation", ""), "policy": m.get("policy", "")}
            for m in _MERGES.values()]


def set_status(mid: str, status: str) -> bool:
    if mid in _MERGES:
        _MERGES[mid]["status"] = status
        return True
    return False
