"""Shared state for the LangGraph ingest pipeline (requirements §5.1)."""
from __future__ import annotations

from typing import Optional, TypedDict


class IngestState(TypedDict, total=False):
    run_id: str
    source: dict                  # {type: "url"|"file", ref, content?}

    raw_path: Optional[str]
    parsed_text: Optional[str]
    title: Optional[str]

    normalized_md: Optional[str]
    sdlc_phase: Optional[str]
    slug: Optional[str]

    chunks: list
    vector_ids: list

    similar_candidates: list
    merge_decision: dict          # {action: "merge"|"create", target_slug?, reason}
    conflict_report: dict         # {relation: "contradiction"|"augmentation"|"duplicate"|"none", conflicts: list[str], summary}

    page_slug: Optional[str]
    merge_id: Optional[str]
    edges: list
    errors: list
