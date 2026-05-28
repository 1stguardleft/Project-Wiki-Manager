"""Persisted store of merge records (FR-MERGE-2).

Records survive process restarts so the KPI page can aggregate coverage and
auto-resolve ratios across sessions. The file lives under `wiki/graph/` so
`/api/wiki/reset` clears it together with the rest of the generated wiki
artifacts (via `reset()` below).
"""
from __future__ import annotations

import json
import uuid

from app import config


def _load() -> dict[str, dict]:
    try:
        return json.loads(config.MERGES_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _persist() -> None:
    config.MERGES_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.MERGES_FILE.write_text(
        json.dumps(_MERGES, ensure_ascii=False, indent=2), encoding="utf-8")


_MERGES: dict[str, dict] = _load()


def create(target_slug: str, before: str, after: str,
           conflicts: list[str], sources: list[str], relation: str = "",
           policy: str = "", status: str = "pending",
           rationale: str = "", confidence: float | None = None) -> str:
    mid = uuid.uuid4().hex[:8]
    _MERGES[mid] = {
        "id": mid, "target_slug": target_slug,
        "before": before, "after": after,
        "conflicts": conflicts, "sources": sources,
        "relation": relation, "policy": policy, "status": status,
        "rationale": rationale, "confidence": confidence,
        "coverage": None, "omissions": [],
    }
    _persist()
    return mid


def update(mid: str, **fields) -> bool:
    """Patch fields on an existing record (e.g. after a coverage re-merge)."""
    if mid not in _MERGES:
        return False
    _MERGES[mid].update(fields)
    _persist()
    return True


def get(mid: str) -> dict | None:
    return _MERGES.get(mid)


def list_all() -> list[dict]:
    return [{"id": m["id"], "target_slug": m["target_slug"],
             "status": m["status"], "conflicts": len(m["conflicts"]),
             "relation": m.get("relation", ""), "policy": m.get("policy", ""),
             "confidence": m.get("confidence"), "coverage": m.get("coverage"),
             "omissions": len(m.get("omissions") or [])}
            for m in _MERGES.values()]


def list_records() -> list[dict]:
    """Full records (used by KPI aggregation)."""
    return list(_MERGES.values())


def set_status(mid: str, status: str) -> bool:
    if mid in _MERGES:
        _MERGES[mid]["status"] = status
        _persist()
        return True
    return False


def reset() -> None:
    _MERGES.clear()
    try:
        config.MERGES_FILE.unlink()
    except FileNotFoundError:
        pass
