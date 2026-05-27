"""Hybrid search: BM25 (keyword) + Chroma (vector), fused with RRF.

requirements §7 / FR-SRCH.  BM25 is built on demand over current wiki chunks;
for the demo scale (~hundreds of pages) this is cheap.  Results are fused by
Reciprocal Rank Fusion and de-duplicated to page level.
"""
from __future__ import annotations

import re

from app.services import chunking, frontmatter, vectordb, wiki_engine
from app import config

_RRF_K = 60


def _all_chunks() -> list[dict]:
    chunks: list[dict] = []
    for path in config.WIKI_DIR.rglob("*.md"):
        if "graph" in path.parts or path.name in ("index.md", "log.md"):
            continue
        fm, body = frontmatter.parse(path.read_text(encoding="utf-8"))
        slug = fm.get("slug", path.stem)
        chunks.extend(chunking.chunk_markdown(body, slug, fm.get("sdlc_phase")))
    return chunks


def _tok(text: str) -> list[str]:
    return re.findall(r"[\w가-힣]+", text.lower())


def _bm25(query: str, chunks: list[dict], k: int) -> list[tuple[str, float]]:
    from rank_bm25 import BM25Okapi
    if not chunks:
        return []
    corpus = [_tok(c["text"]) for c in chunks]
    bm = BM25Okapi(corpus)
    scores = bm.get_scores(_tok(query))
    ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)[:k]
    return [(c["chunk_id"], s) for c, s in ranked if s > 0]


def hybrid_search(query: str, k: int = 8, phase: str | None = None) -> list[dict]:
    chunks = _all_chunks()
    if phase:
        chunks = [c for c in chunks if c.get("sdlc_phase") == phase]
    by_id = {c["chunk_id"]: c for c in chunks}

    bm_ranked = _bm25(query, chunks, k * 2)
    vec_ranked = vectordb.query(query, k=k * 2, phase=phase)

    # Reciprocal Rank Fusion over page slugs
    page_score: dict[str, float] = {}
    page_best_chunk: dict[str, dict] = {}

    def _add(rank: int, cid: str):
        chunk = by_id.get(cid)
        if not chunk:
            return
        slug = chunk["page_slug"]
        page_score[slug] = page_score.get(slug, 0.0) + 1.0 / (_RRF_K + rank)
        page_best_chunk.setdefault(slug, chunk)

    for r, (cid, _) in enumerate(bm_ranked):
        _add(r, cid)
    for r, item in enumerate(vec_ranked):
        _add(r, item["chunk_id"])

    ranked = sorted(page_score.items(), key=lambda x: x[1], reverse=True)[:k]
    results = []
    for slug, score in ranked:
        page = wiki_engine.read_page(slug)
        chunk = page_best_chunk.get(slug, {})
        results.append({
            "slug": slug,
            "title": (page or {}).get("frontmatter", {}).get("title", slug),
            "sdlc_phase": chunk.get("sdlc_phase"),
            "score": round(score, 5),
            "snippet": chunk.get("text", "")[:280],
        })
    return results
