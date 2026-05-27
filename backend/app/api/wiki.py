"""Wiki browsing: pages, graph, log, search, query (FR-IDX, FR-SRCH, FR-OPS-2)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models import QueryRequest
from app.schema import loader
from app.services import lint as lint_svc
from app.services import query as query_svc
from app.services import search as search_svc
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


@router.get("/wiki/graph")
def graph() -> dict:
    return wiki_engine.get_graph()


@router.get("/wiki/log")
def log(limit: int = 50) -> dict:
    return {"entries": wiki_engine.read_log(limit)}


@router.get("/search")
def search(q: str, phase: str | None = None, k: int = 8) -> dict:
    return {"results": search_svc.hybrid_search(q, k=k, phase=phase)}


@router.post("/query")
def query(req: QueryRequest) -> dict:
    return query_svc.answer(req.question)


@router.post("/lint")
def lint() -> dict:
    return lint_svc.run()
