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
def _page_path(slug: str, page_type: str, sdlc_phase: str | None,
               domain: str | None = None, subdomain: str | None = None) -> Path:
    if page_type != "deliverable":
        return config.WIKI_DIR / loader.ENTITIES_DIR / f"{slug}.md"
    # {단계}/{도메인}/{서브도메인}/slug.md — 도메인/서브도메인 없으면 상위에 둔다
    parts = [loader.phase_dir(sdlc_phase)]
    dd = loader.domain_dir(sdlc_phase, domain)
    if dd:
        parts.append(dd)
        sd = loader.subdomain_dir(sdlc_phase, domain, subdomain)
        if sd:
            parts.append(sd)
    return config.WIKI_DIR.joinpath(*parts) / f"{slug}.md"


def ensure_skeleton() -> None:
    """Pre-create the empty numbered folder tree (단계>도메인>서브도메인)."""
    for rel in loader.skeleton_dirs():
        (config.WIKI_DIR / rel).mkdir(parents=True, exist_ok=True)


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
    path = _page_path(slug, fm.get("type", "deliverable"), fm.get("sdlc_phase"),
                      fm.get("domain"), fm.get("subdomain"))
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
            "domain": fm.get("domain"),
            "subdomain": fm.get("subdomain"),
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
             confidence: str | None = None,
             evidence: "str | dict | None" = None) -> None:
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


def clear_outbound_edges(src: str, etypes: "tuple[str, ...] | list[str]") -> int:
    """`src`에서 나가는 엣지 중 `etypes` 안의 타입만 제거하고 edges.jsonl 을
    재기록한다. crossref rebuild 처럼 특정 카테고리만 재생성할 때 사용.
    merged_from / conflicts_with 같은 provenance 엣지는 보존된다.
    """
    existing = _read_edges()
    keep = [e for e in existing
            if not (e.get("from") == src and e.get("type") in etypes)]
    removed = len(existing) - len(keep)
    if removed == 0:
        return 0
    config.GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    with config.EDGES_FILE.open("w", encoding="utf-8") as f:
        for e in keep:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return removed


def get_graph() -> dict:
    """Nodes (pages) + edges for the knowledge graph view."""
    pages = list_pages()
    nodes = [{"id": p["slug"], "label": p["title"], "phase": p["sdlc_phase"],
              "domain": p.get("domain"), "subdomain": p.get("subdomain"),
              "type": p["type"]} for p in pages]
    return {"nodes": nodes, "edges": _read_edges()}


def reset() -> dict:
    """Wipe all GENERATED wiki data so the user can start a fresh test:
    pages, graph edges, log, index, vector store, ingested manifest, raw archive
    and in-memory merge records. Source documents (SOURCES_DIR) are NOT touched.
    """
    from app.services import vectordb, ingested  # noqa: F401 — local to avoid cycles
    from app.agents import merge_store
    from app.events import bus

    removed = 0
    for path in config.WIKI_DIR.rglob("*.md"):
        if "graph" in path.parts or path.name in ("index.md", "log.md"):
            continue
        path.unlink()
        removed += 1
    config.GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    config.EDGES_FILE.write_text("", encoding="utf-8")
    config.LOG_FILE.write_text("", encoding="utf-8")
    if config.INGESTED_FILE.exists():
        config.INGESTED_FILE.unlink()
    raw_removed = 0
    if config.RAW_DIR.exists():
        for raw in config.RAW_DIR.glob("*.md"):
            raw.unlink()
            raw_removed += 1
    vectordb.reset()
    merge_store.reset()
    bus.reset()
    ensure_skeleton()  # keep the empty numbered folder tree
    rebuild_index()  # regenerate an empty index
    return {"pages_removed": removed, "raw_removed": raw_removed}


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


def read_log(limit: int = 50, slug: str | None = None) -> list[str]:
    """Return log entries newest-first.

    Without `slug`, returns the most recent `limit` entries (sidebar/recent view).
    With `slug`, filters from the FULL log file by `[[slug]]` token so a page's
    history is always reachable even after many newer ingests have pushed the
    original entry past the default 50-entry window. The cap still applies after
    filtering so a heavily-edited page can't pull megabytes."""
    if not config.LOG_FILE.exists():
        return []
    entries = [b.strip() for b in config.LOG_FILE.read_text(encoding="utf-8").split("\n\n") if b.strip()]
    if slug:
        token = f"[[{slug}]]"
        entries = [e for e in entries if token in e]
    return entries[-limit:][::-1]
