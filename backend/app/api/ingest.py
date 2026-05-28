"""Ingest + run event streaming (FR-ING, FR-VIZ-3)."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agents import graph
from app.events import bus
from app.models import IngestRequest, IngestResponse
from app.services import runs

router = APIRouter(prefix="/api")


@router.post("/ingest", response_model=IngestResponse)
def start_ingest(req: IngestRequest) -> IngestResponse:
    if req.source_type == "url":
        if not req.url:
            raise HTTPException(400, "url required")
        source = {"type": "url", "ref": req.url}
    else:
        if not req.content:
            raise HTTPException(400, "content required for file")
        source = {"type": "file", "ref": req.filename or "upload.md", "content": req.content}
    if req.conflict_policy:
        source["conflict_policy"] = req.conflict_policy
    run_id = runs.new_run(source)
    return IngestResponse(run_id=run_id)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    # First connection for a pending run → claim it and launch the pipeline.
    # Re-connection (reload / HMR / dropped stream) → bus already exists, so just
    # re-subscribe; bus.stream replays the full history before live events.
    if not bus.has(run_id):
        source = runs.claim(run_id)
        if source is None:
            raise HTTPException(404, "unknown or already-started run")
        bus.create(run_id)
        asyncio.create_task(graph.run(run_id, source))

    async def gen():
        async for event in bus.stream(run_id):
            yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
