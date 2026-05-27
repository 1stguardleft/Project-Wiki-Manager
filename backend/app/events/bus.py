"""Per-run event bus for live workflow visualization.

Each ingest run gets an asyncio.Queue.  Pipeline node wrappers publish
`node_update` / `run_*` events (see requirements §4.2); the SSE endpoint
drains the queue and streams events to the React Flow workflow view.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

_QUEUES: dict[str, asyncio.Queue] = {}
_DONE = object()


def create(run_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _QUEUES[run_id] = q
    return q


def get(run_id: str) -> asyncio.Queue | None:
    return _QUEUES.get(run_id)


async def publish(run_id: str, event: dict) -> None:
    q = _QUEUES.get(run_id)
    if q is not None:
        await q.put(event)


async def close(run_id: str) -> None:
    q = _QUEUES.get(run_id)
    if q is not None:
        await q.put(_DONE)


async def stream(run_id: str) -> AsyncIterator[dict]:
    """Yield events until the run signals completion, then clean up."""
    q = _QUEUES.get(run_id)
    if q is None:
        return
    try:
        while True:
            item = await q.get()
            if item is _DONE:
                break
            yield item
    finally:
        _QUEUES.pop(run_id, None)
