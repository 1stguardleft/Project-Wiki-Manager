"""FastAPI application entrypoint.

Run:  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.api import ingest, merges, sources, wiki
from app.schema import loader
from app.services import vectordb

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


@app.on_event("startup")
def _startup() -> None:
    config.ensure_dirs()
    # seed SDLC phase directories + entities dir so the layout is visible
    for sub in list(loader.SDLC_PHASES.values()) + [loader.ENTITIES_DIR]:
        (config.WIKI_DIR / sub).mkdir(parents=True, exist_ok=True)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "llm_enabled": config.LLM_ENABLED,
            "provider": config.LLM_PROVIDER,
            "chat_model": config.OPENAI_CHAT_MODEL,
            "embed_model": config.OPENAI_EMBED_MODEL,
            "conflict_policy": config.CONFLICT_POLICY,
            "conflict_policies": list(config.CONFLICT_POLICIES)}


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
