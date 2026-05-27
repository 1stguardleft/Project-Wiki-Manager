"""Wiki engine — page/index/log/edge CRUD over the filesystem.

Adapted in spirit from OmegaWiki's tools/research_wiki.py (MIT): the wiki is a
directory of markdown files plus a graph (edges.jsonl), a catalog (index.md)
and an append-only log (log.md).  This layer is the single owner of wiki/.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from app import config
from app.schema import loader
from app.services import frontmatter


# ── Pages ────────────────────────────────────────────────────────────────
def _page_path(slug: str, page_type: str, sdlc_phase: str | None) -> Path:
    sub = loader.phase_dir(sdlc_phase) if page_type == "deliverable" else loader.ENTITIES_DIR
    return config.WIKI_DIR / sub / f"{slug}.md"


def find_page_path(slug: str) -> Path | None:
    """Locate a page by slug across all phase/entity directories."""
    for p in config.WIKI_DIR.rglob(f"{slug}.md"):
        if "graph" not in p.parts:
            return p
    return None


def write_page(slug: str, fm: dict, body: str) -> Path:
    fm = dict(fm)
    fm.setdefault("slug", slug)
    fm.setdefault("type", "deliverable")
    fm.setdefault("status", "active")
    fm["updated"] = date.today().isoformat()
    path = _page_path(slug, fm.get("type", "deliverable"), fm.get("sdlc_phase"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter.dump(fm, body), encoding="utf-8")
    return path


def read_page(slug: str) -> dict | None:
    path = find_page_path(slug)
    if not path:
        return None
    fm, body = frontmatter.parse(path.read_text(encoding="utf-8"))
    return {"slug": slug, "frontmatter": fm, "body": body,
            "path": str(path.relative_to(config.REPO_ROOT))}


def delete_page(slug: str) -> bool:
    path = find_page_path(slug)
    if path:
        path.unlink()
        return True
    return False


def list_pages(phase: str | None = None) -> list[dict]:
    out: list[dict] = []
    for path in config.WIKI_DIR.rglob("*.md"):
        if "graph" in path.parts or path.name in ("index.md", "log.md"):
            continue
        fm, body = frontmatter.parse(path.read_text(encoding="utf-8"))
        if phase and fm.get("sdlc_phase") != phase:
            continue
        out.append({
            "slug": fm.get("slug", path.stem),
            "title": fm.get("title", path.stem),
            "type": fm.get("type", "deliverable"),
            "sdlc_phase": fm.get("sdlc_phase"),
            "status": fm.get("status", "active"),
            "updated": fm.get("updated"),
            "source_count": fm.get("source_count", 0),
        })
    return sorted(out, key=lambda p: (p.get("sdlc_phase") or "zz", p["slug"]))


# ── Edges / graph ──────────────────────────────────────────────────────────
def _read_edges() -> list[dict]:
    if not config.EDGES_FILE.exists():
        return []
    return [json.loads(line) for line in
            config.EDGES_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]


def add_edge(src: str, dst: str, etype: str,
             confidence: str | None = None, evidence: str | None = None) -> None:
    if etype not in loader.VALID_EDGE_TYPES:
        raise ValueError(f"unknown edge type: {etype}")
    config.GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    edge = {"from": src, "to": dst, "type": etype}
    if confidence:
        edge["confidence"] = confidence
    if evidence:
        edge["evidence"] = evidence
    existing = _read_edges()
    if any(e["from"] == src and e["to"] == dst and e["type"] == etype for e in existing):
        return
    with config.EDGES_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(edge, ensure_ascii=False) + "\n")


def get_edges() -> list[dict]:
    return _read_edges()


def get_graph() -> dict:
    """Nodes (pages) + edges for the knowledge graph view."""
    pages = list_pages()
    nodes = [{"id": p["slug"], "label": p["title"],
              "phase": p["sdlc_phase"], "type": p["type"]} for p in pages]
    return {"nodes": nodes, "edges": _read_edges()}


def backlinks(slug: str) -> list[str]:
    """Pages whose body contains a wikilink to `slug`."""
    out: list[str] = []
    for path in config.WIKI_DIR.rglob("*.md"):
        if "graph" in path.parts or path.stem == slug:
            continue
        text = path.read_text(encoding="utf-8")
        if f"[[{slug}]]" in text:
            out.append(path.stem)
    return out


# ── Index & log ──────────────────────────────────────────────────────────
def rebuild_index() -> None:
    pages = list_pages()
    lines = ["# Wiki Index", "", f"_{len(pages)} pages • updated {date.today().isoformat()}_", ""]
    by_phase: dict[str, list[dict]] = {}
    for p in pages:
        by_phase.setdefault(p.get("sdlc_phase") or "_entities", []).append(p)
    for phase in loader.PHASE_ORDER + ["_entities"]:
        group = by_phase.get(phase)
        if not group:
            continue
        lines.append(f"## {phase}")
        for p in group:
            lines.append(f"- [[{p['slug']}]] — {p['title']} ({p['status']})")
        lines.append("")
    config.WIKI_DIR.mkdir(parents=True, exist_ok=True)
    config.INDEX_FILE.write_text("\n".join(lines), encoding="utf-8")


def append_log(kind: str, title: str, detail: str = "") -> None:
    config.WIKI_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"## [{stamp}] {kind} | {title}"
    if detail:
        line += f"\n{detail}"
    with config.LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n\n")


def read_log(limit: int = 50) -> list[str]:
    if not config.LOG_FILE.exists():
        return []
    entries = [b.strip() for b in config.LOG_FILE.read_text(encoding="utf-8").split("\n\n") if b.strip()]
    return entries[-limit:][::-1]
