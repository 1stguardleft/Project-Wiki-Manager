"""
Index/Log Agent — wiki/index.md, wiki/log.md 갱신.

index.md: 신규 페이지 생성 시에만 항목 추가 (링크 + 한 줄 요약)
log.md  : 매 ingest마다 항목 추가
"""

import json
import re
import time
from datetime import date
from pathlib import Path

import anthropic

from models.state import IngestState

WIKI_DIR = Path("wiki")
WIKI_INDEX = WIKI_DIR / "index.md"
WIKI_LOG = WIKI_DIR / "log.md"
META_DIR = Path("output/meta")

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 512


def _update_meta(state: IngestState) -> None:
    meta_path = META_DIR / f"{state.source_id}.json"
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["stages"] = state.stages.model_dump()
    meta["timings"] = state.timings.model_dump()
    meta["error"] = state.error
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_summary(page_path: str) -> str:
    """wiki 페이지 첫 단락을 한 줄 요약으로 반환 (LLM 없이 간단 추출)."""
    path = Path(page_path)
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8")
    # frontmatter 제거
    content = re.sub(r"^---[\s\S]+?---\n+", "", content).strip()
    # 첫 번째 비어 있지 않은 줄 (헤딩 제외)
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line[:80] + ("..." if len(line) > 80 else "")
    return ""


def _get_page_title(page_path: str) -> str:
    """wiki 페이지 frontmatter의 title 추출."""
    path = Path(page_path)
    if not path.exists():
        return Path(page_path).stem
    content = path.read_text(encoding="utf-8")
    match = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else Path(page_path).stem


def _update_index(created_pages: list[str]) -> None:
    """신규 생성 페이지만 index.md에 추가."""
    if not created_pages:
        return

    WIKI_INDEX.parent.mkdir(parents=True, exist_ok=True)
    existing = WIKI_INDEX.read_text(encoding="utf-8") if WIKI_INDEX.exists() else ""

    new_entries: list[str] = []
    for page_path in created_pages:
        title = _get_page_title(page_path)
        summary = _get_summary(page_path)
        # 이미 index에 링크가 있으면 스킵
        if page_path in existing or f"({page_path})" in existing:
            continue
        entry = f"- [{title}]({page_path})"
        if summary:
            entry += f" — {summary}"
        new_entries.append(entry)

    if not new_entries:
        return

    if existing.strip():
        updated = existing.rstrip() + "\n" + "\n".join(new_entries) + "\n"
    else:
        updated = "\n".join(new_entries) + "\n"

    WIKI_INDEX.write_text(updated, encoding="utf-8")


def _append_log(state: IngestState) -> None:
    """log.md에 처리 항목 추가."""
    WIKI_LOG.parent.mkdir(parents=True, exist_ok=True)
    existing = WIKI_LOG.read_text(encoding="utf-8") if WIKI_LOG.exists() else ""

    today = date.today().isoformat()
    created_str = ", ".join(state.created_wiki_pages) if state.created_wiki_pages else "(없음)"
    updated_str = ", ".join(state.updated_wiki_pages) if state.updated_wiki_pages else "(없음)"

    entry = (
        f"\n## [{today}] ingest | {state.source_id}\n\n"
        f"- 소스 타입: {state.source_type}\n"
        f"- URL: {state.url}\n"
        f"- 생성 페이지: {created_str}\n"
        f"- 갱신 페이지: {updated_str}\n"
    )

    WIKI_LOG.write_text(existing + entry, encoding="utf-8")


def index_log_node(state: IngestState) -> IngestState:
    """wiki/index.md, wiki/log.md 갱신."""
    state.stages.index_log = "running"
    state.timings.index_log_started_at = time.time()
    _update_meta(state)

    try:
        _update_index(state.created_wiki_pages)
        _append_log(state)

        state.stages.index_log = "done"
        state.timings.index_log_ended_at = time.time()

    except OSError as e:
        state.stages.index_log = "error"
        state.error = f"index/log 파일 쓰기 오류: {e}"
    finally:
        _update_meta(state)

    return state
