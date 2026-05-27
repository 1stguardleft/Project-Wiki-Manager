"""Chroma vector store wrapper (requirements §14.5).

Single persistent collection `wiki`; chunk metadata carries page_slug,
sdlc_phase and source so search/similarity can filter.  Embeddings are
provided by services.llm (OpenAI or offline fallback) — we pass them in
explicitly rather than relying on Chroma's embedding function.
"""
from __future__ import annotations

from app import config
from app.services import llm

_COLLECTION = "wiki"
_client = None


def _coll():
    global _client
    if _client is None:
        import chromadb
        _client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    return _client.get_or_create_collection(_COLLECTION, metadata={"hnsw:space": "cosine"})


def upsert_chunks(chunks: list[dict]) -> list[str]:
    if not chunks:
        return []
    ids = [c["chunk_id"] for c in chunks]
    texts = [c["text"] for c in chunks]
    metas = [{"page_slug": c["page_slug"],
              "sdlc_phase": c.get("sdlc_phase") or "",
              "heading": c.get("heading") or ""} for c in chunks]
    embeddings = llm.embed(texts)
    _coll().upsert(ids=ids, documents=texts, metadatas=metas, embeddings=embeddings)
    return ids


def delete_page(page_slug: str) -> None:
    _coll().delete(where={"page_slug": page_slug})


def query(text: str, k: int = 8, phase: str | None = None) -> list[dict]:
    where = {"sdlc_phase": phase} if phase else None
    emb = llm.embed([text])[0]
    res = _coll().query(query_embeddings=[emb], n_results=k, where=where,
                        include=["documents", "metadatas", "distances"])
    out: list[dict] = []
    ids = res.get("ids", [[]])[0]
    for i, cid in enumerate(ids):
        out.append({
            "chunk_id": cid,
            "text": res["documents"][0][i],
            "page_slug": res["metadatas"][0][i].get("page_slug"),
            "sdlc_phase": res["metadatas"][0][i].get("sdlc_phase"),
            "distance": res["distances"][0][i],
        })
    return out


def count() -> int:
    return _coll().count()
