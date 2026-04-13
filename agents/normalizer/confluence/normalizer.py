"""
Normalizer/Confluence — Confluence Storage Format(XML) → Markdown 변환.

변환 대상:
  - p, h1~h6, ul, ol, li, code, pre
  - 단순 table → markdown 테이블
  - 복잡한 table (colspan/rowspan) → 텍스트 대체
  - ac:image (첨부) → <!-- attachment: {filename} -->
  - ac:link → markdown 링크
  - ac:structured-macro name="code" → 펜스드 코드 블록
  - 그 외 매크로 → <!-- macro: {name} omitted -->

출력: output/normalizer/confluence/{source_id}.md
"""

import json
import time
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

from models.state import IngestState

INPUT_DIR = Path("output/fetcher/confluence")
OUTPUT_DIR = Path("output/normalizer/confluence")
META_DIR = Path("output/meta")


def _update_meta(state: IngestState) -> None:
    meta_path = META_DIR / f"{state.source_id}.json"
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["stages"] = state.stages.model_dump()
    meta["timings"] = state.timings.model_dump()
    meta["error"] = state.error
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 변환 헬퍼 ──────────────────────────────────────────────


def _is_complex_table(table: Tag) -> bool:
    """colspan 또는 rowspan이 있으면 복잡한 테이블로 판단."""
    for cell in table.find_all(["td", "th"]):
        if cell.get("colspan") or cell.get("rowspan"):
            return True
    return False


def _table_to_markdown(table: Tag) -> str:
    rows = table.find_all("tr")
    if not rows:
        return ""

    md_rows: list[list[str]] = []
    for row in rows:
        cells = row.find_all(["th", "td"])
        md_rows.append([_node_to_text(cell).strip() for cell in cells])

    if not md_rows:
        return ""

    # 헤더 행
    header = md_rows[0]
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("| " + " | ".join(["---"] * len(header)) + " |")
    for row in md_rows[1:]:
        # 열 수가 헤더와 다르면 패딩
        while len(row) < len(header):
            row.append("")
        lines.append("| " + " | ".join(row[: len(header)]) + " |")

    return "\n".join(lines)


def _node_to_text(node: Tag | NavigableString) -> str:
    """태그 내부 텍스트를 재귀적으로 추출 (간단 텍스트 전용)."""
    if isinstance(node, NavigableString):
        return str(node)
    return node.get_text(separator=" ", strip=True)


def _convert_node(node: Tag | NavigableString, depth: int = 0) -> str:
    """단일 노드를 markdown 문자열로 변환."""
    if isinstance(node, NavigableString):
        text = str(node)
        return text if text.strip() else (" " if text else "")

    tag = node.name

    # ── 헤딩 ──
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(tag[1])
        inner = _children_to_markdown(node, depth)
        return f"\n{'#' * level} {inner.strip()}\n"

    # ── 단락 ──
    if tag == "p":
        inner = _children_to_markdown(node, depth)
        return f"\n{inner.strip()}\n"

    # ── 강조 ──
    if tag in ("strong", "b"):
        return f"**{_children_to_markdown(node, depth).strip()}**"
    if tag in ("em", "i"):
        return f"*{_children_to_markdown(node, depth).strip()}*"

    # ── 인라인 코드 ──
    if tag == "code" and node.parent and node.parent.name != "pre":
        return f"`{node.get_text()}`"

    # ── 코드 블록 ──
    if tag == "pre":
        code = node.find("code")
        content = code.get_text() if code else node.get_text()
        return f"\n```\n{content}\n```\n"

    # ── 링크 ──
    if tag == "a":
        href = node.get("href", "")
        text = _children_to_markdown(node, depth).strip()
        return f"[{text}]({href})" if href else text

    # ── 이미지 ──
    if tag == "img":
        alt = node.get("alt", "")
        src = node.get("src", "")
        return f"![{alt}]({src})"

    # ── 목록 ──
    if tag in ("ul", "ol"):
        items = []
        for i, li in enumerate(node.find_all("li", recursive=False), start=1):
            content = _children_to_markdown(li, depth + 1).strip()
            prefix = f"{i}." if tag == "ol" else "-"
            items.append(f"{'  ' * depth}{prefix} {content}")
        return "\n" + "\n".join(items) + "\n"

    if tag == "li":
        return _children_to_markdown(node, depth)

    # ── 테이블 ──
    if tag == "table":
        if _is_complex_table(node):
            return f"\n<!-- complex table omitted -->\n{node.get_text(separator=' ', strip=True)}\n"
        return "\n" + _table_to_markdown(node) + "\n"

    # ── Confluence 매크로 ──
    if tag == "ac:structured-macro":
        name = node.get("ac:name", "")
        if name == "code":
            lang_param = node.find("ac:parameter", {"ac:name": "language"})
            lang = lang_param.get_text().strip() if lang_param else ""
            body = node.find("ac:plain-text-body") or node.find("ac:rich-text-body")
            content = body.get_text() if body else ""
            return f"\n```{lang}\n{content}\n```\n"
        return f"\n<!-- macro: {name} omitted -->\n"

    # ── Confluence 첨부 이미지 ──
    if tag == "ac:image":
        attachment = node.find("ri:attachment")
        filename = attachment.get("ri:filename", "unknown") if attachment else "unknown"
        return f"<!-- attachment: {filename} -->"

    # ── Confluence 링크 ──
    if tag == "ac:link":
        page = node.find("ri:page")
        title = page.get("ri:content-title", "") if page else ""
        link_body = node.find("ac:link-body") or node.find("ac:plain-text-link-body")
        link_text = link_body.get_text().strip() if link_body else title
        return f"[{link_text}]" if link_text else ""

    # ── 줄바꿈 ──
    if tag == "br":
        return "\n"

    # ── 수평선 ──
    if tag == "hr":
        return "\n---\n"

    # ── 그 외: 자식 노드 재귀 처리 ──
    return _children_to_markdown(node, depth)


def _children_to_markdown(node: Tag, depth: int = 0) -> str:
    parts = [_convert_node(child, depth) for child in node.children]
    return "".join(parts)


def _xml_to_markdown(xml: str) -> str:
    soup = BeautifulSoup(xml, "lxml-xml")
    # Confluence Storage Format은 최상위 body 없이 내용이 바로 있음
    # lxml-xml 파서로 파싱 후 전체 자식 순회
    root = soup.find() or soup
    md = _children_to_markdown(root)

    # 연속 빈 줄 3개 이상 → 2개로 압축
    import re
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


# ── 노드 함수 ──────────────────────────────────────────────


def normalizer_confluence_node(state: IngestState) -> IngestState:
    """XML 파일을 읽어 markdown으로 변환 후 output/normalizer/confluence/{source_id}.md 에 저장."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    state.stages.normalizer = "running"
    state.timings.normalizer_started_at = time.time()
    _update_meta(state)

    xml_path = INPUT_DIR / f"{state.source_id}.xml"

    if not xml_path.exists():
        state.stages.normalizer = "error"
        state.error = f"Fetcher 출력 파일을 찾을 수 없습니다: {xml_path}"
        _update_meta(state)
        return state

    try:
        xml = xml_path.read_text(encoding="utf-8")
        markdown = _xml_to_markdown(xml)

        out_path = OUTPUT_DIR / f"{state.source_id}.md"
        out_path.write_text(markdown, encoding="utf-8")

        state.stages.normalizer = "done"
        state.timings.normalizer_ended_at = time.time()

    except Exception as e:
        state.stages.normalizer = "error"
        state.error = f"Confluence XML 변환 오류: {e}"
    finally:
        _update_meta(state)

    return state
