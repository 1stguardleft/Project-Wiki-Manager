"""Heading-aware chunking with a soft size cap (requirements §7.3 / §14.4)."""
from __future__ import annotations

import re

_APPROX_CHARS = 1600  # ~ 512-1024 tokens for mixed KO/EN text
_OVERLAP = 200


def chunk_markdown(md: str, page_slug: str, sdlc_phase: str | None) -> list[dict]:
    """Split on markdown headings, then cap long sections by char length."""
    sections = _split_by_heading(md)
    chunks: list[dict] = []
    idx = 0
    for heading, text in sections:
        for piece in _cap(text):
            chunks.append({
                "chunk_id": f"{page_slug}#{idx}",
                "page_slug": page_slug,
                "sdlc_phase": sdlc_phase,
                "heading": heading,
                "text": (f"{heading}\n{piece}" if heading else piece).strip(),
            })
            idx += 1
    if not chunks and md.strip():
        chunks.append({"chunk_id": f"{page_slug}#0", "page_slug": page_slug,
                       "sdlc_phase": sdlc_phase, "heading": "", "text": md.strip()})
    return chunks


def _split_by_heading(md: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    cur_head, buf = "", []
    for line in md.splitlines():
        if re.match(r"^#{1,6}\s", line):
            if buf:
                parts.append((cur_head, "\n".join(buf).strip()))
                buf = []
            cur_head = line.strip()
        else:
            buf.append(line)
    if buf:
        parts.append((cur_head, "\n".join(buf).strip()))
    return [p for p in parts if p[1] or p[0]]


def _cap(text: str) -> list[str]:
    if len(text) <= _APPROX_CHARS:
        return [text] if text else []
    out, start = [], 0
    while start < len(text):
        end = start + _APPROX_CHARS
        out.append(text[start:end])
        start = end - _OVERLAP
    return out
