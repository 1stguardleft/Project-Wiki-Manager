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

from app import config
from app.agents import nodes
from app.agents.state import IngestState
from app.events import bus
from app.services import ingested

# node id -> implementation
_IMPL = {
    "fetch": nodes.fetch, "parse": nodes.parse_node, "normalize": nodes.normalize,
    "decompose": nodes.decompose,
    "chunk": nodes.chunk, "embed": nodes.embed, "similarity": nodes.similarity,
    "conflict": nodes.conflict, "merge": nodes.merge, "verify": nodes.verify,
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
    if nid == "decompose":
        sp = result.get("spawned_runs") or []
        if sp:
            return f"{len(sp)}개 도메인 단위로 분해"
        dom = result.get("domain")
        return f"단일 도메인{(': ' + dom) if dom else ''}"
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
    if nid == "verify":
        r = result.get("coverage_report", {})
        n = len(r.get("omissions", []))
        cov = r.get("coverage")
        cov_s = f"커버리지 {int(cov * 100)}%" if isinstance(cov, (int, float)) else ""
        return f"누락 {n}건{(' · ' + cov_s) if cov_s else ''}"
    if nid == "crossref":
        return f"상호참조 {len(result.get('edges', []))}건"
    if nid == "index":
        return "인덱스 재생성"
    if nid == "log":
        return "처리 이력 기록"
    return "완료"


def _clip(s, n: int = 1200) -> str:
    s = str(s if s is not None else "")
    return s if len(s) <= n else s[:n] + " …"


def _detail(nid: str, result: dict) -> list:
    """노드별 작업 결과를 UI 상세 패널용 구조로 정리. (항상 안전 — 예외 시 빈 리스트)

    각 항목: {label, value} | {label, items:[..]} | {label, code:".."}
    """
    try:
        d: list = []
        if nid in ("fetch", "parse"):
            if result.get("title"):
                d.append({"label": "제목", "value": str(result["title"])})
            txt = result.get("parsed_text")
            if txt:
                d.append({"label": "본문 길이", "value": f"{len(txt):,}자"})
                d.append({"label": "본문 미리보기", "code": _clip(txt, 1400)})
        elif nid == "normalize":
            for k, lab in (("sdlc_phase", "SDLC 단계"), ("slug", "slug"),
                           ("domain", "도메인"), ("subdomain", "서브도메인")):
                if result.get(k):
                    d.append({"label": lab, "value": str(result[k])})
            md = result.get("normalized_md")
            if md:
                d.append({"label": "정규화 길이", "value": f"{len(md):,}자"})
                d.append({"label": "정규화 본문", "code": _clip(md, 1600)})
        elif nid == "decompose":
            if result.get("domain"):
                d.append({"label": "도메인", "value": str(result["domain"])})
            if result.get("subdomain"):
                d.append({"label": "서브도메인", "value": str(result["subdomain"])})
            units = result.get("units") or []
            if units:
                d.append({"label": f"분해 단위 {len(units)}개", "items": [
                    f"{u.get('domain', '')}/{u.get('subdomain', '')} · {u.get('title', '')}".strip("/ ·")
                    for u in units[:40]]})
            sp = result.get("spawned_runs") or []
            if sp:
                d.append({"label": "생성된 자식 run", "value": f"{len(sp)}개 (도메인 단위 병렬 처리)"})
        elif nid == "chunk":
            chunks = result.get("chunks") or []
            d.append({"label": "청크 수", "value": f"{len(chunks)}개"})
            prev = []
            for c in chunks[:6]:
                t = c.get("text") if isinstance(c, dict) else c
                prev.append(_clip(t, 180))
            if prev:
                d.append({"label": "청크 미리보기 (앞 6개)", "items": prev})
        elif nid == "embed":
            d.append({"label": "저장 벡터 수", "value": f"{len(result.get('vector_ids') or [])}개"})
        elif nid == "similarity":
            dec = result.get("merge_decision") or {}
            if dec.get("action"):
                d.append({"label": "병합 결정", "value": str(dec.get("action"))})
            if dec.get("target_slug"):
                d.append({"label": "대상 페이지", "value": f"[[{dec['target_slug']}]]"})
            if dec.get("reason"):
                d.append({"label": "판단 근거", "value": _clip(dec["reason"], 500)})
            cands = result.get("similar_candidates") or []
            items = []
            for c in cands[:12]:
                if isinstance(c, dict):
                    slug = c.get("slug") or c.get("page_slug") or c.get("target_slug") or "?"
                    score = c.get("score", c.get("similarity", c.get("distance")))
                    items.append(f"[[{slug}]]" + (f" · {score:.3f}" if isinstance(score, (int, float)) else ""))
                else:
                    items.append(str(c))
            if items:
                d.append({"label": f"유사 후보 {len(cands)}건", "items": items})
        elif nid == "conflict":
            r = result.get("conflict_report") or {}
            if r.get("relation"):
                d.append({"label": "관계 판정", "value": str(r["relation"])})
            if r.get("summary"):
                d.append({"label": "요약", "value": _clip(r["summary"], 600)})
            conf = r.get("conflicts") or []
            if conf:
                d.append({"label": f"충돌 {len(conf)}건", "items": [_clip(x, 220) for x in conf[:20]]})
        elif nid == "merge":
            if result.get("page_slug"):
                d.append({"label": "생성/병합 페이지", "value": f"[[{result['page_slug']}]]"})
            if result.get("merge_id"):
                d.append({"label": "merge_id", "value": str(result["merge_id"])})
            au = result.get("merge_audit") or {}
            if au.get("mode"):
                d.append({"label": "병합 모드", "value": str(au["mode"])})
            if au.get("merged"):
                d.append({"label": "병합 결과 본문", "code": _clip(au["merged"], 1800)})
        elif nid == "verify":
            r = result.get("coverage_report") or {}
            cov = r.get("coverage")
            if isinstance(cov, (int, float)):
                d.append({"label": "커버리지", "value": f"{int(cov * 100)}%"})
            if r.get("summary"):
                d.append({"label": "요약", "value": _clip(r["summary"], 600)})
            om = r.get("omissions") or []
            d.append({"label": f"누락 {len(om)}건",
                      "items": [_clip(x, 220) for x in om[:20]] if om else ["누락 없음"]})
        elif nid == "crossref":
            edges = result.get("edges") or []
            items = []
            for e in edges[:20]:
                if isinstance(e, dict):
                    tgt = e.get("target") or e.get("to") or e.get("target_slug") or "?"
                    typ = e.get("type") or e.get("relation") or ""
                    conf = e.get("confidence")
                    s = f"[[{tgt}]]" + (f" · {typ}" if typ else "")
                    if isinstance(conf, (int, float)):
                        s += f" · {int(conf * 100)}%"
                    items.append(s)
                else:
                    items.append(str(e))
            d.append({"label": f"상호참조 {len(edges)}건", "items": items or ["없음"]})
        return d
    except Exception:  # noqa: BLE001 — 상세는 부가정보이므로 실패해도 파이프라인에 영향 없음
        return []


def _make_node(nid: str):
    label = _LABEL[nid]
    fn = _IMPL[nid]

    uses_llm = nid in nodes.LLM_NODES

    async def wrapper(state: IngestState) -> dict:
        run_id = state["run_id"]
        t0 = time.time()
        await bus.publish(run_id, {
            "type": "node_update", "run_id": run_id, "node_id": nid,
            "node_label": label, "status": "running", "started_at": _now(),
            "uses_llm": uses_llm,
        })
        # pace the pipeline so each step is visible in the live view
        if config.STEP_DELAY_SEC > 0:
            await asyncio.sleep(config.STEP_DELAY_SEC)
        result = await asyncio.to_thread(fn, state)
        await bus.publish(run_id, {
            "type": "node_update", "run_id": run_id, "node_id": nid,
            "node_label": label, "status": "succeeded", "ended_at": _now(),
            "duration_ms": int((time.time() - t0) * 1000),
            "output_summary": _summarize(nid, result),
            "output_detail": _detail(nid, result),
            "uses_llm": uses_llm,
        })
        return result

    return wrapper


def _verify_router(state: IngestState) -> str:
    """누락검토 → merge 루프: omissions가 있고 재시도 한도 미만이면 보완 재머지."""
    rep = state.get("coverage_report") or {}
    if rep.get("omissions") and (state.get("merge_retries") or 0) < nodes.MAX_MERGE_RETRIES:
        return "merge"
    return "continue"


def _decompose_router(state: IngestState) -> str:
    """도메인 분해가 자식 run으로 갈라졌으면 이 (부모) run은 페이지 생성 없이 종료."""
    return "split" if state.get("spawned_runs") else "continue"


def build():
    g = StateGraph(IngestState)
    for nid in _ORDER:
        g.add_node(nid, _make_node(nid))
    g.add_edge(START, _ORDER[0])
    after_verify = None
    after_decompose = None
    for a, b in zip(_ORDER, _ORDER[1:]):
        if a == "verify":
            after_verify = b           # wired as a conditional edge below
            continue
        if a == "decompose":
            after_decompose = b        # split → END, single → next node
            continue
        g.add_edge(a, b)
    if after_decompose:
        g.add_conditional_edges("decompose", _decompose_router,
                                {"split": END, "continue": after_decompose})
    if after_verify:
        g.add_conditional_edges("verify", _verify_router,
                                {"merge": "merge", "continue": after_verify})
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
                                   "status": "queued",
                                   "uses_llm": nid in nodes.LLM_NODES})
    state: IngestState = {"run_id": run_id, "source": source, "edges": [], "errors": []}
    try:
        final = await _graph().ainvoke(state)
        # flag the source file as analyzed so the picker can mark/filter it
        if source.get("path"):
            ingested.mark(source["path"], final.get("page_slug"))
        await bus.publish(run_id, {"type": "run_completed", "run_id": run_id,
                                   "ended_at": _now(),
                                   "page_slug": final.get("page_slug"),
                                   "merge_id": final.get("merge_id"),
                                   "spawned_runs": final.get("spawned_runs") or [],
                                   "units": len(final.get("units") or [])})
    except Exception as exc:  # noqa: BLE001 — surface failure to the UI
        await bus.publish(run_id, {"type": "run_failed", "run_id": run_id,
                                   "ended_at": _now(), "error": str(exc)})
    finally:
        await bus.close(run_id)
