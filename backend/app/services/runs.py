"""Registry of ingest runs awaiting / in execution."""
from __future__ import annotations

import uuid

# run_id -> {source, started}
PENDING: dict[str, dict] = {}


def new_run(source: dict) -> str:
    run_id = uuid.uuid4().hex[:12]
    PENDING[run_id] = {"source": source, "started": False}
    return run_id


def claim(run_id: str) -> dict | None:
    """Return the source and mark started; None if unknown or already started."""
    rec = PENDING.get(run_id)
    if not rec or rec["started"]:
        return None
    rec["started"] = True
    return rec["source"]
