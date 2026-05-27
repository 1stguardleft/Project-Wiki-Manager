"""Browse local markdown sources and batch-ingest selected files.

The file picker lists `.md` files under config.SOURCES_DIR (Confluence-style
exports), surfacing each document's author / created / modified metadata from
its YAML frontmatter so the UI can show it alongside the file list.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import config
from app.services import frontmatter, parser, runs

router = APIRouter(prefix="/api")


class BatchIngestRequest(BaseModel):
    paths: list[str]
    conflict_policy: str | None = None


def _safe_resolve(rel: str) -> Path:
    """Resolve a client-supplied relative path inside SOURCES_DIR (no escape)."""
    base = config.SOURCES_DIR.resolve()
    target = (base / rel).resolve()
    if base != target and base not in target.parents:
        raise HTTPException(400, f"path escapes sources dir: {rel}")
    return target


def _meta(path: Path, base: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    fm, body = frontmatter.parse(text)
    modified = str(fm.get("modified") or fm.get("last_modified") or fm.get("updated") or "")
    if not modified:
        modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return {
        "path": str(path.relative_to(base)),
        "name": path.name,
        "title": fm.get("title") or parser._extract_title(body) or path.stem,
        "author": str(fm.get("author") or fm.get("creator") or ""),
        "created": str(fm.get("created") or fm.get("created_at") or ""),
        "modified": modified,
        "size": path.stat().st_size,
    }


@router.get("/sources/files")
def list_files(subdir: str = "") -> dict:
    """List the folders and `.md` files directly under SOURCES_DIR/<subdir>.

    Folders are returned so the UI can drill down; selection of files persists
    across navigation on the client side.
    """
    base = config.SOURCES_DIR.resolve()
    cwd = _safe_resolve(subdir) if subdir else base
    rel = "" if cwd == base else str(cwd.relative_to(base))
    if not cwd.is_dir():
        return {"root": str(base), "cwd": rel, "parent": None, "dirs": [], "files": []}

    dirs, files = [], []
    for p in sorted(cwd.iterdir(), key=lambda x: x.name.lower()):
        if p.name.startswith("."):
            continue
        if p.is_dir():
            md_count = sum(1 for _ in p.rglob("*.md"))
            dirs.append({"name": p.name, "path": str(p.relative_to(base)),
                         "md_count": md_count})
        elif p.suffix.lower() in (".md", ".markdown"):
            files.append(_meta(p, base))

    if cwd == base:
        parent = None
    else:
        parent = "" if cwd.parent == base else str(cwd.parent.relative_to(base))
    return {"root": str(base), "cwd": rel, "parent": parent,
            "dirs": dirs, "files": files}


@router.post("/ingest/batch")
def ingest_batch(req: BatchIngestRequest) -> dict:
    if not req.paths:
        raise HTTPException(400, "no paths selected")
    base = config.SOURCES_DIR.resolve()
    created = []
    for rel in req.paths:
        path = _safe_resolve(rel)
        if not path.is_file():
            raise HTTPException(404, f"not found: {rel}")
        fm, body = frontmatter.parse(path.read_text(encoding="utf-8"))
        title = fm.get("title") or parser._extract_title(body) or path.stem
        source = {"type": "file", "ref": path.name, "content": body}
        if req.conflict_policy:
            source["conflict_policy"] = req.conflict_policy
        run_id = runs.new_run(source)
        created.append({"path": str(path.relative_to(base)), "title": title,
                        "run_id": run_id})
    return {"runs": created}
