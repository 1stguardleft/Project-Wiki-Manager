"""Wiki health checks (FR-OPS-3) — adapted from OmegaWiki tools/lint.py (MIT).

Reports broken wikilinks, orphan pages and dangling graph edges.  Read-only;
returns a structured report for the UI / CLI.
"""
from __future__ import annotations

from app import config
from app.schema import loader
from app.services import frontmatter, wiki_engine


def run() -> dict:
    pages = {p["slug"] for p in wiki_engine.list_pages()}
    broken_links: list[dict] = []
    has_outgoing: set[str] = set()
    linked_to: set[str] = set()

    for path in config.WIKI_DIR.rglob("*.md"):
        if "graph" in path.parts or path.name in ("index.md", "log.md"):
            continue
        fm, body = frontmatter.parse(path.read_text(encoding="utf-8"))
        slug = fm.get("slug", path.stem)
        for target in loader.WIKILINK_RE.findall(body):
            has_outgoing.add(slug)
            linked_to.add(target)
            if target not in pages:
                broken_links.append({"from": slug, "to": target})

    orphans = [s for s in pages if s not in linked_to and s not in has_outgoing]

    dangling_edges = [
        e for e in wiki_engine.get_edges()
        if e["from"] not in pages or e["to"] not in pages
    ]

    issues = len(broken_links) + len(orphans) + len(dangling_edges)
    return {
        "ok": issues == 0,
        "issue_count": issues,
        "page_count": len(pages),
        "broken_links": broken_links,
        "orphans": orphans,
        "dangling_edges": dangling_edges,
    }
