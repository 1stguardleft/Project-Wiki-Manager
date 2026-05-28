"""Manifest of source files that have already been analyzed (ingested).

A tiny JSON map ``{source_rel_path: {page_slug, at}}`` persisted at
``config.INGESTED_FILE``.  It lets the source picker flag/filter documents that
were already run through the pipeline so they aren't re-analyzed by accident.
We track the *source file* (not its frontmatter) so read-only export folders are
never modified.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app import config


def _read() -> dict:
    try:
        return json.loads(config.INGESTED_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def all() -> dict:
    """Whole manifest: rel-path -> {page_slug, at}."""
    return _read()


def is_done(rel_path: str) -> bool:
    return rel_path in _read()


def mark(rel_path: str, page_slug: str | None = None) -> None:
    """Record that the source file at `rel_path` has been ingested."""
    if not rel_path:
        return
    data = _read()
    data[rel_path] = {"page_slug": page_slug,
                      "at": datetime.now(timezone.utc).isoformat()}
    config.INGESTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.INGESTED_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
