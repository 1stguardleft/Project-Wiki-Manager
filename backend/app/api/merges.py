"""Merge conflict / diff inspection (FR-MERGE-2, §13.4).

The LLM auto-resolves conflicts, so a merge is already applied when it appears
here — the only operator action is REVERT, which restores the page to its
pre-merge content (body + vectors + index)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agents import merge_store
from app.services import chunking, vectordb, wiki_engine

router = APIRouter(prefix="/api")


@router.get("/merges")
def list_merges() -> dict:
    """충돌 이력만 노출 — augmentation/duplicate 같은 자동 병합은 사람이
    검토할 거리가 없으므로 제외한다(KPI 집계는 별도로 전체 레코드를 사용)."""
    rows = [m for m in merge_store.list_all() if m.get("relation") == "contradiction"]
    return {"merges": rows}


@router.get("/merges/{mid}/diff")
def get_diff(mid: str) -> dict:
    rec = merge_store.get(mid)
    if not rec:
        raise HTTPException(404, "merge not found")
    return rec


@router.post("/merges/{mid}/revert")
def revert(mid: str) -> dict:
    """Undo an applied merge: restore the page body to its pre-merge state and
    re-embed it, so the wiki/search reflect the rollback (not just a flag)."""
    rec = merge_store.get(mid)
    if not rec:
        raise HTTPException(404, "merge not found")
    if rec.get("status") == "reverted":
        return {"status": "reverted"}

    target = rec["target_slug"]
    before = rec.get("before") or ""
    existing = wiki_engine.read_page(target)
    if existing:
        fm = dict(existing["frontmatter"])
        fm["source_count"] = max(1, fm.get("source_count", 1) - 1)
        wiki_engine.write_page(target, fm, before)
        # keep the vector store consistent with the restored body
        vectordb.delete_page(target)
        vectordb.upsert_chunks(chunking.chunk_markdown(before, target, fm.get("sdlc_phase")))
        wiki_engine.rebuild_index()

    merge_store.set_status(mid, "reverted")
    return {"status": "reverted", "page_slug": target}
