"""FastAPI application entrypoint.

Run:  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.api import ingest, kpi, merges, sources, wiki
from app.schema import loader
from app.services import vectordb, wiki_engine

app = FastAPI(title="Project Wiki Manager", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(sources.router)
app.include_router(wiki.router)
app.include_router(merges.router)
app.include_router(kpi.router)


@app.on_event("startup")
def _startup() -> None:
    config.ensure_dirs()
    # seed the numbered 단계>도메인>서브도메인 skeleton + entities dir so the layout is visible
    wiki_engine.ensure_skeleton()
    (config.WIKI_DIR / loader.ENTITIES_DIR).mkdir(parents=True, exist_ok=True)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "llm_enabled": config.LLM_ENABLED,
            "provider": config.LLM_PROVIDER,
            "chat_model": config.OPENAI_CHAT_MODEL,
            "embed_model": config.OPENAI_EMBED_MODEL,
            "conflict_strategy": config.CONFLICT_STRATEGY,
            "conflict_strategies": list(config.CONFLICT_STRATEGIES),
            "conflict_auto_threshold": config.CONFLICT_AUTO_THRESHOLD,
            # legacy keys kept for the existing frontend dropdown
            "conflict_policy": config.CONFLICT_STRATEGY,
            "conflict_policies": list(config.CONFLICT_STRATEGIES)}


@app.get("/api/stats")
def stats() -> dict:
    from app.services import wiki_engine
    pages = wiki_engine.list_pages()
    by_phase: dict[str, int] = {}
    for p in pages:
        key = p.get("sdlc_phase") or "_entities"
        by_phase[key] = by_phase.get(key, 0) + 1
    return {"page_count": len(pages), "by_phase": by_phase,
            "vector_count": _safe_vec_count()}


def _safe_vec_count() -> int:
    try:
        return vectordb.count()
    except Exception:  # noqa: BLE001
        return 0
