"""Merge conflict / diff inspection (FR-MERGE-2, §13.4)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agents import merge_store

router = APIRouter(prefix="/api")


@router.get("/merges")
def list_merges() -> dict:
    return {"merges": merge_store.list_all()}


@router.get("/merges/{mid}/diff")
def get_diff(mid: str) -> dict:
    rec = merge_store.get(mid)
    if not rec:
        raise HTTPException(404, "merge not found")
    return rec


@router.post("/merges/{mid}/accept")
def accept(mid: str) -> dict:
    if not merge_store.set_status(mid, "accepted"):
        raise HTTPException(404, "merge not found")
    return {"status": "accepted"}


@router.post("/merges/{mid}/revert")
def revert(mid: str) -> dict:
    if not merge_store.set_status(mid, "reverted"):
        raise HTTPException(404, "merge not found")
    return {"status": "reverted"}
