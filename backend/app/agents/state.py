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
    domain: Optional[str]         # business domain (고객/주문/상품 …), self-organized
    subdomain: Optional[str]      # specific topic within the domain (고객 검색 …)

    # composite-document decomposition (도메인 분해 Agent)
    units: list                   # [{domain, subdomain, title, body, target_slug?}]
    spawned_runs: list            # child run_ids when the doc was split by sub-domain

    chunks: list
    vector_ids: list

    similar_candidates: list
    merge_decision: dict          # {action: "merge"|"create", target_slug?, reason}
    conflict_report: dict         # {relation: "contradiction"|"augmentation"|"duplicate"|"none", conflicts: list[str], summary}

    page_slug: Optional[str]
    merge_id: Optional[str]
    # merge-coverage loop (누락검토 Agent → merge)
    merge_audit: dict             # {mode: "reconciled"|"split"|"created", target, before, incoming, merged}
    coverage_report: dict         # {coverage: 0..1, omissions: list[str], summary}
    merge_retries: int
    edges: list
    errors: list
