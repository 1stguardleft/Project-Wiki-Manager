"""Seed the wiki by ingesting demo/*.md through the full pipeline.

Usage (from backend/):  .venv/bin/python -m scripts.seed_demo
Demonstrates: new-page creation, duplicate detection + merge, multi-phase wiki.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.agents import graph
from app.events import bus
from app.services import runs, wiki_engine

DEMO_DIR = Path(__file__).resolve().parents[2] / "demo"


async def ingest(path: Path) -> None:
    run_id = runs.new_run({"type": "file", "ref": path.name, "content": path.read_text(encoding="utf-8")})
    runs.claim(run_id)
    bus.create(run_id)
    task = asyncio.create_task(graph.run(run_id, {"type": "file", "ref": path.name,
                                                  "content": path.read_text(encoding="utf-8")}))
    async for ev in bus.stream(run_id):
        if ev["type"] == "run_completed":
            print(f"  ✓ {path.name} -> [[{ev.get('page_slug')}]]"
                  + (f"  (merge {ev['merge_id']})" if ev.get("merge_id") else ""))
        elif ev["type"] == "run_failed":
            print(f"  ✗ {path.name}: {ev.get('error')}")
    await task


async def main() -> None:
    files = sorted(DEMO_DIR.glob("*.md"))
    print(f"Seeding {len(files)} demo documents...")
    for f in files:
        await ingest(f)
    print("\nPages:")
    for p in wiki_engine.list_pages():
        print(f"  [{p['sdlc_phase']}] {p['slug']} (sources={p['source_count']})")


if __name__ == "__main__":
    asyncio.run(main())
