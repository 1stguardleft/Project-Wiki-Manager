"""LLM page-title suggestion for accumulated (merged) pages.

When a page grows from multiple sources, its display title should reflect the
combined content. We regenerate only the display `title` — never the `slug`
(page identity / file path / [[wikilinks]]). Offline or on failure the current
title is kept, so behaviour degrades gracefully.
"""
from __future__ import annotations

from app import config
from app.services import llm


def suggest_title(body: str, current: str | None) -> str:
    cur = (current or "").strip()
    if not config.LLM_ENABLED or not (body or "").strip():
        return cur
    system = ("Give ONE concise, natural Korean wiki page title that best "
              "captures the document below — the kind of title a person would "
              "write at the top of the doc. Rules: a single line, ≤ 10 words; "
              "do NOT include round/version markers such as (1차), (2차), 1차, "
              "2차; no quotes, no markdown, no trailing punctuation. Return ONLY "
              "the title.")
    out = (llm.chat(body[:3000], system=system) or "").strip()
    line = out.splitlines()[0].strip() if out else ""
    for ch in ("#", "*", "`", '"', "'"):
        line = line.strip(ch).strip()
    return line[:60] or cur
