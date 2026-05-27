"""LangGraph pipeline assembly + event-emitting runner.

The pipeline is a linear StateGraph over the §4.1 nodes (the merge/create branch
is handled inside the `merge` node).  Each node is wrapped so it publishes
`node_update` events (queued→running→succeeded/failed) to the per-run event bus,
which the SSE endpoint streams to the React Flow workflow view.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph

from app.agents import nodes
from app.agents.state import IngestState
from app.events import bus

# node id -> implementation
_IMPL = {
    "fetch": nodes.fetch, "parse": nodes.parse_node, "normalize": nodes.normalize,
    "chunk": nodes.chunk, "embed": nodes.embed, "similarity": nodes.similarity,
    "conflict": nodes.conflict, "merge": nodes.merge,
    "crossref": nodes.crossref, "index": nodes.index, "log": nodes.log,
}
_LABEL = dict(nodes.NODE_SPECS)
_ORDER = [nid for nid, _ in nodes.NODE_SPECS]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summarize(nid: str, result: dict) -> str:
    if nid == "fetch":
        return f"제목: {result.get('title', '')[:40]}"
    if nid == "normalize":
        return f"단계={result.get('sdlc_phase')} slug={result.get('slug')}"
    if nid == "chunk":
        return f"청크 {len(result.get('chunks', []))}개"
    if nid == "embed":
        return f"벡터 {len(result.get('vector_ids', []))}개 저장"
    if nid == "similarity":
        d = result.get("merge_decision", {})
        return f"{d.get('action')} ({d.get('reason', '')[:50]})"
    if nid == "conflict":
        r = result.get("conflict_report", {})
        return f"{r.get('relation')} (충돌 {len(r.get('conflicts', []))}건)"
    if nid == "merge":
        return f"page=[[{result.get('page_slug')}]]"
    return "완료"


def _make_node(nid: str):
    label = _LABEL[nid]
    fn = _IMPL[nid]

    async def wrapper(state: IngestState) -> dict:
        run_id = state["run_id"]
        t0 = time.time()
        await bus.publish(run_id, {
            "type": "node_update", "run_id": run_id, "node_id": nid,
            "node_label": label, "status": "running", "started_at": _now(),
        })
        result = await asyncio.to_thread(fn, state)
        await bus.publish(run_id, {
            "type": "node_update", "run_id": run_id, "node_id": nid,
            "node_label": label, "status": "succeeded", "ended_at": _now(),
            "duration_ms": int((time.time() - t0) * 1000),
            "output_summary": _summarize(nid, result),
        })
        return result

    return wrapper


def build():
    g = StateGraph(IngestState)
    for nid in _ORDER:
        g.add_node(nid, _make_node(nid))
    g.add_edge(START, _ORDER[0])
    for a, b in zip(_ORDER, _ORDER[1:]):
        g.add_edge(a, b)
    g.add_edge(_ORDER[-1], END)
    return g.compile()


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build()
    return _GRAPH


async def run(run_id: str, source: dict) -> None:
    """Execute the pipeline for one source, emitting lifecycle events."""
    await bus.publish(run_id, {"type": "run_started", "run_id": run_id,
                               "source": source, "started_at": _now()})
    # announce planned nodes so the UI can render the full graph up-front
    for nid in _ORDER:
        await bus.publish(run_id, {"type": "node_update", "run_id": run_id,
                                   "node_id": nid, "node_label": _LABEL[nid],
                                   "status": "queued"})
    state: IngestState = {"run_id": run_id, "source": source, "edges": [], "errors": []}
    try:
        final = await _graph().ainvoke(state)
        await bus.publish(run_id, {"type": "run_completed", "run_id": run_id,
                                   "ended_at": _now(),
                                   "page_slug": final.get("page_slug"),
                                   "merge_id": final.get("merge_id")})
    except Exception as exc:  # noqa: BLE001 — surface failure to the UI
        await bus.publish(run_id, {"type": "run_failed", "run_id": run_id,
                                   "ended_at": _now(), "error": str(exc)})
    finally:
        await bus.close(run_id)
