"""Pluggable conflict-resolution strategies (FR-MERGE).

When an incoming document is judged to *contradict* an existing wiki page, the
`merge` node hands off to one of these strategies. Strategies are looked up by
name from `REGISTRY`, so the active behaviour is a single config switch
(`config.CONFLICT_STRATEGY`, or a per-source `conflict_policy` override) and
adding a new one is one function + one registry entry — no edits to the
LangGraph pipeline.

The default, `llm_merge`, keeps a human out of the loop entirely: the LLM
reconciles both documents into ONE authoritative page and the result is applied
automatically. A confidence gate (`config.CONFLICT_AUTO_THRESHOLD`, default 0)
lets a future operator route low-confidence merges to manual review by changing
a number, not code.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app import config
from app.agents import merge_store
from app.services import llm, titling, wiki_engine


@dataclass
class ConflictContext:
    """Everything a resolver needs about one contradiction."""
    slug: str            # incoming document's slug
    target: str          # existing page slug it would merge into
    title: str
    phase: str | None
    body: str            # incoming normalized markdown
    before: str          # existing page body (pre-merge)
    existing: dict       # existing page record {frontmatter, body, ...}
    conflicts: list[str]  # concrete contradiction strings (Korean)
    report: dict         # full conflict_report from the conflict node
    sources: list[str]   # incoming source refs


# ── shared helpers ─────────────────────────────────────────────────────────
def _evidence(ctx: ConflictContext) -> str:
    return ctx.report.get("summary") or "; ".join(ctx.conflicts)


def _write_incoming(ctx: ConflictContext, status: str) -> None:
    """Persist the incoming doc as its own page with the given status."""
    wiki_engine.write_page(ctx.slug, {
        "title": ctx.title, "slug": ctx.slug, "type": "deliverable",
        "sdlc_phase": ctx.phase, "status": status,
        "source_count": 1, "sources": ctx.sources}, ctx.body)


# ── Strategy: llm_merge (default) — reconcile into ONE page, no human ───────
def llm_merge(ctx: ConflictContext) -> dict:
    merged, confidence, rationale = _reconcile(ctx)

    # Confidence gate: only engages when a positive threshold is configured.
    # With the default 0 this never triggers → fully automatic resolution.
    if config.CONFLICT_AUTO_THRESHOLD > 0 and confidence < config.CONFLICT_AUTO_THRESHOLD:
        return manual(ctx)

    fm = dict(ctx.existing["frontmatter"])
    fm["status"] = "active"
    fm["source_count"] = fm.get("source_count", 1) + 1
    fm["sources"] = list(dict.fromkeys((fm.get("sources") or []) + ctx.sources))
    # accumulated page → let the LLM retitle from the merged content (slug fixed)
    fm["title"] = titling.suggest_title(merged, fm.get("title"))
    wiki_engine.write_page(ctx.target, fm, merged)
    mid = merge_store.create(ctx.target, ctx.before, merged, ctx.conflicts,
                             ctx.sources, relation="contradiction",
                             policy="llm_merge", status="auto_resolved",
                             rationale=rationale, confidence=confidence)
    return {"page_slug": ctx.target, "merge_id": mid,
            "edges": [{"from": ctx.target, "to": ctx.slug,
                       "type": "merged_from", "evidence": _evidence(ctx)}],
            # reconciled into one page → eligible for the 누락검토 coverage loop
            "merge_audit": {"mode": "reconciled", "target": ctx.target,
                            "before": ctx.before, "incoming": ctx.body, "merged": merged}}


def _reconcile(ctx: ConflictContext) -> tuple[str, float, str]:
    """Ask the LLM to fold the two contradicting docs into one page.

    Returns (merged_body, confidence 0..1, rationale). Offline / on parse
    failure it preserves both versions with a low confidence so a configured
    threshold can still divert it to a human.
    """
    if not config.LLM_ENABLED:
        marker = ("\n\n> ⚠️ 자동 화해(offline): 아래는 최신 반영 출처의 내용입니다. "
                  "충돌 가능 — 검토 권장.\n\n")
        return ctx.before + marker + ctx.body, 0.4, "offline 휴리스틱: 본문 이어붙임"

    ex_meta = ctx.existing.get("frontmatter", {})
    system = (
        "You reconcile an EXISTING wiki page and an INCOMING document that "
        "CONTRADICT each other into ONE coherent Korean markdown page. Resolve "
        "each contradiction by preferring the more recent / authoritative claim "
        "(use the given metadata); keep the chosen fact, drop the stale one, and "
        "add a short '> ℹ️ 변경: ...' blockquote noting what changed and why. "
        "Never invent facts. PRESERVE verbatim any HTML comment markers like "
        "'<!-- crossref:auto -->' / '<!-- /crossref:auto -->' and the content "
        "between them — they are auto-managed elsewhere. Return JSON: "
        '{"body": "<full merged markdown>", "confidence": <0..1>, '
        '"rationale": "<short Korean explanation>"}.')
    prompt = (
        f"EXISTING (modified={ex_meta.get('modified', '?')}, "
        f"author={ex_meta.get('author', '?')}):\n{ctx.before[:4000]}\n\n"
        f"INCOMING (newly ingested, source={ctx.sources}):\n{ctx.body[:4000]}\n\n"
        "KNOWN CONTRADICTIONS:\n- " + "\n- ".join(ctx.conflicts or ["(미상)"]))
    try:
        data = json.loads(llm.chat(prompt, system=system, json_mode=True))
        body = (data.get("body") or "").strip()
        if not body:
            raise ValueError("empty body")
        conf = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
        return body, conf, str(data.get("rationale", ""))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        merged = ctx.before + "\n\n> ⚠️ 자동 화해 실패 — 원문 보존\n\n" + ctx.body
        return merged, 0.0, "LLM 화해 응답 파싱 실패 — 원문 보존"


# ── Strategy: prefer_incoming — newer doc wins, old page superseded ────────
def prefer_incoming(ctx: ConflictContext) -> dict:
    _write_incoming(ctx, "active")
    fm = dict(ctx.existing["frontmatter"])
    fm["status"] = "superseded"
    wiki_engine.write_page(ctx.target, fm, ctx.before)
    mid = merge_store.create(ctx.target, ctx.before, ctx.body, ctx.conflicts,
                             ctx.sources, relation="contradiction",
                             policy="prefer_incoming", status="accepted")
    return {"page_slug": ctx.slug, "merge_id": mid,
            "edges": [{"from": ctx.slug, "to": ctx.target, "type": "supersedes",
                       "evidence": _evidence(ctx)}],
            "merge_audit": {"mode": "split"}}


# ── Strategy: prefer_existing — existing wins, incoming parked rejected ────
def prefer_existing(ctx: ConflictContext) -> dict:
    _write_incoming(ctx, "rejected")
    mid = merge_store.create(ctx.target, ctx.before, ctx.body, ctx.conflicts,
                             ctx.sources, relation="contradiction",
                             policy="prefer_existing", status="rejected")
    return {"page_slug": ctx.slug, "merge_id": mid,
            "edges": [{"from": ctx.slug, "to": ctx.target, "type": "conflicts_with",
                       "evidence": _evidence(ctx)}],
            "merge_audit": {"mode": "split"}}


# ── Strategy: manual — keep both, leave the decision to a human ────────────
def manual(ctx: ConflictContext) -> dict:
    _write_incoming(ctx, "active")
    mid = merge_store.create(ctx.target, ctx.before, ctx.body, ctx.conflicts,
                             ctx.sources, relation="contradiction",
                             policy="manual", status="pending")
    return {"page_slug": ctx.slug, "merge_id": mid,
            "edges": [{"from": ctx.slug, "to": ctx.target, "type": "conflicts_with",
                       "evidence": _evidence(ctx)}],
            "merge_audit": {"mode": "split"}}


REGISTRY = {
    "llm_merge": llm_merge,
    "manual": manual,
    "prefer_incoming": prefer_incoming,
    "prefer_existing": prefer_existing,
}


def resolve(strategy: str, ctx: ConflictContext) -> dict:
    """Dispatch to the named strategy, falling back to the configured default."""
    fn = REGISTRY.get(strategy) or REGISTRY.get(config.CONFLICT_STRATEGY) or llm_merge
    return fn(ctx)
