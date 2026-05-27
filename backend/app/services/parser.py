"""Fetch and parse sources into raw markdown.

- URL  -> download HTML, strip chrome, convert to markdown
- file -> stored markdown/text content
Raw content is written under raw/ (immutable source-of-truth layer).
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from app import config


def _slugify_source(ref: str) -> str:
    base = re.sub(r"[^\w.-]+", "-", ref).strip("-")[:60] or "source"
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{base}"


def save_raw(name: str, content: str) -> Path:
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = config.RAW_DIR / f"{_slugify_source(name)}.md"
    path.write_text(content, encoding="utf-8")
    return path


def fetch_url(url: str) -> str:
    import httpx
    resp = httpx.get(url, timeout=20, follow_redirects=True,
                     headers={"User-Agent": "ProjectWikiManager/0.1"})
    resp.raise_for_status()
    return resp.text


def html_to_markdown(html: str) -> str:
    from bs4 import BeautifulSoup
    from markdownify import markdownify

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    md = markdownify(str(main), heading_style="ATX")
    return re.sub(r"\n{3,}", "\n\n", md).strip()


def parse_source(source: dict) -> tuple[str, str]:
    """Return (title, markdown). source = {type: url|file, ref, content?}."""
    if source["type"] == "url":
        html = fetch_url(source["ref"])
        md = html_to_markdown(html)
        title = _extract_title(md) or source["ref"]
        return title, md
    # file
    content = source.get("content", "")
    title = _extract_title(content) or Path(source["ref"]).stem
    return title, content


def _extract_title(md: str) -> str | None:
    for line in md.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None
