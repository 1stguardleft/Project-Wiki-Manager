"""Wiki browsing: pages, graph, log, search, query (FR-IDX, FR-SRCH, FR-OPS-2)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models import QueryRequest
from app.schema import loader
from app.services import chunking
from app.services import lint as lint_svc
from app.services import query as query_svc
from app.services import search as search_svc
from app.services import vectordb
from app.services import wiki_engine

router = APIRouter(prefix="/api")


@router.get("/wiki/phases")
def phases() -> dict:
    return {"phases": loader.PHASE_ORDER, "dirs": loader.SDLC_PHASES}


@router.get("/wiki/pages")
def list_pages(phase: str | None = None) -> dict:
    return {"pages": wiki_engine.list_pages(phase)}


@router.get("/wiki/pages/{slug}")
def get_page(slug: str) -> dict:
    page = wiki_engine.read_page(slug)
    if not page:
        raise HTTPException(404, "page not found")
    page["backlinks"] = wiki_engine.backlinks(slug)
    return page


class PageUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    body: str | None = None


@router.put("/wiki/pages/{slug}")
def update_page(slug: str, req: PageUpdate) -> dict:
    """Edit a page's title/status/body in place (slug & type/phase unchanged)."""
    page = wiki_engine.read_page(slug)
    if not page:
        raise HTTPException(404, "page not found")
    fm = dict(page["frontmatter"])
    if req.title is not None:
        fm["title"] = req.title
    if req.status is not None:
        fm["status"] = req.status
    body = page["body"] if req.body is None else req.body
    wiki_engine.write_page(slug, fm, body)
    if req.body is not None:  # body changed → keep the vector store in sync
        vectordb.delete_page(slug)
        vectordb.upsert_chunks(chunking.chunk_markdown(body, slug, fm.get("sdlc_phase")))
    wiki_engine.rebuild_index()
    wiki_engine.append_log("edit", fm.get("title") or slug, f"page=[[{slug}]]")
    updated = wiki_engine.read_page(slug)
    updated["backlinks"] = wiki_engine.backlinks(slug)
    return updated


@router.delete("/wiki/pages/{slug}")
def delete_page(slug: str) -> dict:
    page = wiki_engine.read_page(slug)
    if not page:
        raise HTTPException(404, "page not found")
    wiki_engine.delete_page(slug)
    wiki_engine.rebuild_index()
    wiki_engine.append_log("delete", page["frontmatter"].get("title") or slug,
                           f"page=[[{slug}]]")
    return {"status": "deleted", "slug": slug}


@router.get("/wiki/graph")
def graph() -> dict:
    return wiki_engine.get_graph()


@router.get("/wiki/structure")
def structure() -> dict:
    """Numbered domain taxonomy tree (단계>도메인>서브도메인) for the page browser."""
    return {"phases": loader.taxonomy_tree()}


@router.post("/wiki/reset")
def reset() -> dict:
    """Wipe all generated wiki data (pages/graph/log/index/vectors/manifest/raw).
    Source documents are not touched. For starting a clean test run."""
    return {"ok": True, **wiki_engine.reset()}


@router.post("/wiki/rebuild-crossref")
def rebuild_crossref(phase: str | None = None) -> dict:
    """모든 페이지의 상호참조 엣지·자동 섹션을 **현재 누적된 코퍼스 기준으로**
    일괄 재생성한다. 초기 적재 때 페이지가 적어 crossref가 비어 있던 경우,
    적재 완료 후 한 번 호출해 채워 넣는 용도. provenance 엣지(merged_from /
    supersedes / conflicts_with)는 보존하고 crossref 계열만 교체한다.
    `phase`가 주어지면 해당 SDLC 단계의 페이지만 대상으로 한다(후보 검색은
    전체 코퍼스에서 수행되므로 다른 단계와의 관계도 발견 가능).
    """
    from app.agents import nodes  # local import — circular guard

    pages = wiki_engine.list_pages(phase)
    if not pages:
        return {"ok": True, "pages_updated": 0, "edges_added": 0,
                "edges_removed": 0, "note": "empty wiki"}

    edges_removed = 0
    edges_added = 0
    updated = 0
    skipped: list[str] = []

    for p in pages:
        slug = p["slug"]
        page_obj = wiki_engine.read_page(slug)
        if not page_obj:
            skipped.append(slug)
            continue
        body = page_obj.get("body") or ""

        # 1) crossref 카테고리 엣지만 초기화 (다른 provenance 엣지는 유지)
        edges_removed += wiki_engine.clear_outbound_edges(slug, nodes.CROSSREF_EDGE_TYPES)

        # 2) 벡터 후보 재조회 — 본문 앞부분으로 검색해 자기 자신/중복 제거
        cands_raw = vectordb.query(body[:2000], k=10)
        seen: set = set()
        cands: list[dict] = []
        for c in cands_raw:
            ps = c.get("page_slug")
            if not ps or ps == slug or ps in seen:
                continue
            seen.add(ps)
            cands.append({"page_slug": ps,
                          "text": c.get("text", ""),
                          "distance": c.get("distance")})

        # 3) 가짜 state로 crossref 노드 호출 — 임계값 가드는 우회해야 하므로
        #    별도 구현하지 않고 노드 함수를 활용하되, MIN_PAGES_FOR_CROSSREF은
        #    이미 코퍼스가 충분하므로 자연스럽게 통과한다.
        before = len(wiki_engine.get_edges())
        state = {"page_slug": slug, "normalized_md": body,
                 "similar_candidates": cands, "edges": []}
        try:
            nodes.crossref(state)
        except Exception:  # noqa: BLE001 — 한 페이지 실패가 전체를 막지 않게
            skipped.append(slug)
            continue
        after = len(wiki_engine.get_edges())
        edges_added += max(0, after - before)
        updated += 1

    return {"ok": True, "pages_updated": updated, "edges_removed": edges_removed,
            "edges_added": edges_added, "skipped": skipped}


@router.get("/wiki/log")
def log(limit: int = 50, slug: str | None = None) -> dict:
    """Recent activity (default) or per-page history when `slug` is given —
    server-side filter from the FULL log file so a page's earliest ingestion
    entry is reachable even after many newer ingests."""
    return {"entries": wiki_engine.read_log(limit, slug=slug)}


@router.get("/search")
def search(q: str, phase: str | None = None, k: int = 8) -> dict:
    return {"results": search_svc.hybrid_search(q, k=k, phase=phase)}


@router.post("/query")
def query(req: QueryRequest) -> dict:
    return query_svc.answer(req.question)


@router.post("/lint")
def lint() -> dict:
    return lint_svc.run()
