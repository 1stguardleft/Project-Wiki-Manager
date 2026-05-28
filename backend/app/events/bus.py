"""Per-run event bus for live workflow visualization.

Each ingest run keeps a full event HISTORY plus a set of live subscriber queues.
A (re)connecting SSE client first gets the whole history replayed, then live
events — so a page reload / HMR remount / dropped connection rebuilds the entire
pipeline instead of resuming mid-way. Multiple clients may watch the same run.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

_HISTORY: dict[str, list[dict]] = {}          # run_id -> all events so far
_SUBS: dict[str, list[asyncio.Queue]] = {}    # run_id -> live subscriber queues
_FINISHED: set[str] = set()                   # runs that emitted run_completed/failed
_DONE = object()


def has(run_id: str) -> bool:
    """True once a run's bus exists (running OR finished — history retained)."""
    return run_id in _HISTORY


def create(run_id: str) -> None:
    _HISTORY[run_id] = []
    _SUBS[run_id] = []
    _FINISHED.discard(run_id)


async def publish(run_id: str, event: dict) -> None:
    _HISTORY.setdefault(run_id, []).append(event)
    for q in list(_SUBS.get(run_id, [])):
        await q.put(event)


async def close(run_id: str) -> None:
    _FINISHED.add(run_id)
    for q in list(_SUBS.get(run_id, [])):
        await q.put(_DONE)


def reset() -> None:
    """Drop all run histories (used by the wiki reset)."""
    _HISTORY.clear()
    _SUBS.clear()
    _FINISHED.clear()


async def stream(run_id: str) -> AsyncIterator[dict]:
    """Replay this run's full history, then live events until it finishes.

    Subscribe + snapshot happen with no `await` in between, so no event can slip
    between the replayed history and the live tail (single-threaded loop)."""
    q: asyncio.Queue = asyncio.Queue()
    _SUBS.setdefault(run_id, []).append(q)
    history = list(_HISTORY.get(run_id, []))
    finished = run_id in _FINISHED
    try:
        for ev in history:
            yield ev
        if finished:
            return
        while True:
            item = await q.get()
            if item is _DONE:
                break
            yield item
    finally:
        subs = _SUBS.get(run_id)
        if subs and q in subs:
            subs.remove(q)
