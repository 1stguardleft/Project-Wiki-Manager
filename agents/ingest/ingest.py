"""
Ingest Agent — Wiki-centric 방식으로 Markdown → Wiki 페이지 생성/갱신.

처리 흐름:
  Step A — 소스 이해        (LLM 1회)
  Step B — 영향 페이지 파악  (LLM 1회, 2단계 탐색)
  Step C — 페이지 정체성 검증 (명명 정규화 + 유사 페이지 확인)
  Step D — 페이지별 변경 계획 (LLM, 영향 페이지 수만큼)
  Step E — 실행 + 매핑 정보 생성
  Step F — IngestState 갱신

출력: wiki/sources/, wiki/entities/, wiki/concepts/
      output/meta/{source_id}_mapping.json
"""

import json
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Any

import anthropic

from models.state import IngestState

META_DIR = Path("output/meta")
WIKI_DIR = Path("wiki")
WIKI_INDEX = WIKI_DIR / "index.md"

NORMALIZER_DIRS = {
    "web": Path("output/normalizer/web"),
    "confluence": Path("output/normalizer/confluence"),
    "local_md": Path("output/normalizer/local"),
}

MODEL = "claude-opus-4-5"
MAX_TOKENS = 4096


def _update_meta(state: IngestState) -> None:
    meta_path = META_DIR / f"{state.source_id}.json"
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["stages"] = state.stages.model_dump()
    meta["timings"] = state.timings.model_dump()
    meta["error"] = state.error
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")
    return anthropic.Anthropic(api_key=api_key)


def _llm(client: anthropic.Anthropic, prompt: str) -> str:
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def _extract_json(text: str) -> Any:
    """LLM 응답에서 JSON 블록 추출."""
    match = re.search(r"```json\s*([\s\S]+?)\s*```", text)
    if match:
        return json.loads(match.group(1))
    # 코드 블록 없이 바로 JSON인 경우
    return json.loads(text.strip())


# ── 페이지명 정규화 ────────────────────────────────────────


def _normalize_page_name(name: str) -> str:
    """
    페이지명 정규화 규칙:
    - 소문자 + 하이픈
    - 축약어(2자 이하 또는 전체 대문자)는 대소문자 유지
    - 띄어쓰기 → 하이픈
    - 특수문자 제거
    """
    name = name.strip()
    # 특수문자(하이픈, 공백 제외) 제거
    name = re.sub(r"[^\w\s\-]", "", name)
    # 공백 → 하이픈
    name = re.sub(r"\s+", "-", name)
    # 연속 하이픈 → 단일 하이픈
    name = re.sub(r"-+", "-", name)
    name = name.lower().strip("-")
    return name


def _find_similar_page(page_name: str, directory: Path) -> Path | None:
    """편집 거리 기반 유사 페이지 탐색 (간단 구현: 정규화 이름 비교)."""
    if not directory.exists():
        return None
    normalized = _normalize_page_name(page_name)
    for existing in directory.glob("*.md"):
        if _normalize_page_name(existing.stem) == normalized:
            return existing
    return None


# ── Wiki 페이지 포맷 ───────────────────────────────────────


def _read_wiki_page(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _write_wiki_page(
    path: Path,
    title: str,
    page_type: str,
    source_ids: list[str],
    content: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    sources_yaml = json.dumps(source_ids, ensure_ascii=False)
    frontmatter = (
        f"---\n"
        f"title: {title}\n"
        f"type: {page_type}\n"
        f"sources: {sources_yaml}\n"
        f"updated: {today}\n"
        f"---\n\n"
    )
    path.write_text(frontmatter + content, encoding="utf-8")


def _extract_frontmatter_sources(content: str) -> list[str]:
    """기존 wiki 페이지 frontmatter에서 sources 목록 추출."""
    match = re.search(r"^sources:\s*(\[.*?\])", content, re.MULTILINE)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return []


# ── Step A — 소스 이해 ─────────────────────────────────────


def _step_a_understand(client: anthropic.Anthropic, source_md: str) -> dict:
    prompt = f"""다음 문서를 분석하고 JSON으로 결과를 반환하세요.

문서:
{source_md[:8000]}

응답 형식:
```json
{{
  "summary": "1~3문장 요약",
  "entities": ["엔티티1", "엔티티2"],
  "concepts": ["개념1", "개념2"],
  "key_claims": ["주요 주장1", "주요 주장2"]
}}
```
"""
    response = _llm(client, prompt)
    return _extract_json(response)


# ── Step B — 영향 페이지 파악 ──────────────────────────────


def _step_b_find_affected(
    client: anthropic.Anthropic,
    understanding: dict,
    index_content: str,
) -> dict:
    entities = understanding.get("entities", [])
    concepts = understanding.get("concepts", [])
    summary = understanding.get("summary", "")

    # 1단계: index.md에서 후보 선별
    prompt_1 = f"""wiki index 파일과 소스 분석 결과를 보고,
영향받을 가능성이 있는 wiki 페이지 후보를 골라주세요.

소스 요약: {summary}
주요 엔티티: {entities}
주요 개념: {concepts}

wiki index:
{index_content or "(비어 있음)"}

응답 형식:
```json
{{
  "candidates": ["wiki/entities/openai.md", "wiki/concepts/rlhf.md"]
}}
```
후보가 없으면 candidates를 빈 배열로 반환하세요.
"""
    resp_1 = _llm(client, prompt_1)
    candidates_data = _extract_json(resp_1)
    candidates: list[str] = candidates_data.get("candidates", [])

    # 2단계: 후보 페이지 본문 읽기 → 최종 확정
    candidate_contents = {}
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            candidate_contents[candidate] = path.read_text(encoding="utf-8")[:3000]

    prompt_2 = f"""소스 분석 결과와 후보 페이지 내용을 보고,
실제로 수정/보강이 필요한 페이지와 새로 만들어야 할 페이지를 확정해주세요.

소스 요약: {summary}
주요 엔티티: {entities}
주요 개념: {concepts}

후보 페이지 내용:
{json.dumps(candidate_contents, ensure_ascii=False, indent=2) or "(후보 없음)"}

응답 형식:
```json
{{
  "affected_pages": ["wiki/entities/openai.md"],
  "new_pages": [
    {{"path": "wiki/entities/gpt-4.md", "type": "entity", "title": "GPT-4"}},
    {{"path": "wiki/concepts/rlhf.md", "type": "concept", "title": "RLHF"}}
  ]
}}
```
"""
    resp_2 = _llm(client, prompt_2)
    return _extract_json(resp_2)


# ── Step C — 페이지 정체성 검증 ────────────────────────────


def _step_c_validate_pages(affected: dict) -> dict:
    """
    new_pages의 path를 정규화하고, 이미 존재하는 유사 페이지가 있으면
    신규 생성 대신 해당 페이지를 affected_pages로 이동.
    """
    validated_affected = list(affected.get("affected_pages", []))
    validated_new: list[dict] = []

    for page_info in affected.get("new_pages", []):
        path = Path(page_info["path"])
        normalized_name = _normalize_page_name(path.stem)
        normalized_path = path.parent / f"{normalized_name}.md"

        # 유사 페이지 탐색
        similar = _find_similar_page(path.stem, path.parent)
        if similar and str(similar) not in validated_affected:
            validated_affected.append(str(similar))
        elif not normalized_path.exists():
            page_info["path"] = str(normalized_path)
            validated_new.append(page_info)
        else:
            if str(normalized_path) not in validated_affected:
                validated_affected.append(str(normalized_path))

    return {"affected_pages": validated_affected, "new_pages": validated_new}


# ── Step D — 페이지별 변경 계획 ────────────────────────────


def _step_d_plan_page(
    client: anthropic.Anthropic,
    page_path: str,
    source_md: str,
    understanding: dict,
    is_new: bool,
    page_info: dict | None = None,
) -> dict:
    existing_content = _read_wiki_page(Path(page_path))

    if is_new:
        title = page_info.get("title", Path(page_path).stem)
        page_type = page_info.get("type", "entity")
        prompt = f"""새 wiki 페이지를 작성하세요.

페이지 경로: {page_path}
페이지 제목: {title}
페이지 유형: {page_type}

소스 내용 (관련 부분만 활용):
{source_md[:6000]}

소스 분석:
{json.dumps(understanding, ensure_ascii=False)}

응답 형식:
```json
{{
  "page": "{page_path}",
  "title": "{title}",
  "type": "{page_type}",
  "content": "# {title}\\n\\n페이지 본문 (markdown)",
  "paragraph_actions": [
    {{"source_paragraph_index": 0, "action": "반영됨", "wiki_section": "개요"}}
  ]
}}
```
"""
    else:
        prompt = f"""기존 wiki 페이지를 소스 내용으로 보강/갱신하세요.
기존 내용을 최대한 유지하며, 새로운 정보를 자연스럽게 통합하세요.

페이지 경로: {page_path}

기존 페이지 내용:
{existing_content[:4000]}

소스 내용 (관련 부분만 활용):
{source_md[:4000]}

소스 분석:
{json.dumps(understanding, ensure_ascii=False)}

응답 형식:
```json
{{
  "page": "{page_path}",
  "title": "기존 제목 유지",
  "type": "기존 type 유지",
  "content": "갱신된 전체 페이지 본문 (frontmatter 제외, markdown)",
  "paragraph_actions": [
    {{"source_paragraph_index": 0, "action": "반영됨", "wiki_section": "개요"}}
  ]
}}
```
"""

    response = _llm(client, prompt)
    return _extract_json(response)


# ── Step E — 실행 + 매핑 ──────────────────────────────────


def _step_e_execute(
    plans: list[dict],
    source_id: str,
    source_md: str,
    source_type: str,
) -> tuple[list[str], list[str], list[dict]]:
    """
    계획대로 wiki 페이지를 쓰고, 매핑 정보를 수집한다.
    반환: (created_pages, updated_pages, mappings)
    """
    created: list[str] = []
    updated: list[str] = []
    all_mappings: list[dict] = []

    paragraphs = [p.strip() for p in source_md.split("\n\n") if p.strip()]

    for plan in plans:
        page_path = Path(plan["page"])
        title = plan.get("title", page_path.stem)
        page_type = plan.get("type", "entity")
        content = plan.get("content", "")

        is_new = not page_path.exists()

        # sources 목록 갱신
        existing_sources: list[str] = []
        if not is_new:
            existing_content = page_path.read_text(encoding="utf-8")
            existing_sources = _extract_frontmatter_sources(existing_content)

        if source_id not in existing_sources:
            existing_sources.append(source_id)

        _write_wiki_page(page_path, title, page_type, existing_sources, content)

        if is_new:
            created.append(str(page_path))
        else:
            updated.append(str(page_path))

        # 매핑 정보 수집
        for action_info in plan.get("paragraph_actions", []):
            idx = action_info.get("source_paragraph_index", 0)
            preview = paragraphs[idx][:100] if idx < len(paragraphs) else ""
            all_mappings.append(
                {
                    "source_paragraph_index": idx,
                    "source_text_preview": preview,
                    "wiki_page": str(page_path),
                    "wiki_section": action_info.get("wiki_section"),
                    "action": action_info.get("action", "반영됨"),
                }
            )

    # 매핑에 포함되지 않은 단락 → 제외됨 처리
    mapped_indices = {m["source_paragraph_index"] for m in all_mappings}
    for i, para in enumerate(paragraphs):
        if i not in mapped_indices:
            all_mappings.append(
                {
                    "source_paragraph_index": i,
                    "source_text_preview": para[:100],
                    "wiki_page": None,
                    "wiki_section": None,
                    "action": "제외됨",
                }
            )

    all_mappings.sort(key=lambda x: x["source_paragraph_index"])
    return created, updated, all_mappings


def _write_mapping(source_id: str, source_type: str, mappings: list[dict]) -> None:
    normalizer_dir = NORMALIZER_DIRS.get(source_type, Path("output/normalizer/web"))
    source_path = str(normalizer_dir / f"{source_id}.md")
    mapping_data = {
        "source_id": source_id,
        "source_path": source_path,
        "mappings": mappings,
    }
    mapping_path = META_DIR / f"{source_id}_mapping.json"
    mapping_path.write_text(
        json.dumps(mapping_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── 노드 함수 ──────────────────────────────────────────────


def ingest_node(state: IngestState) -> IngestState:
    """Wiki-centric 방식으로 Markdown 소스를 wiki 페이지로 통합."""
    state.stages.ingest = "running"
    state.timings.ingest_started_at = time.time()
    _update_meta(state)

    # Normalizer 출력 파일 경로 결정
    normalizer_dir = NORMALIZER_DIRS.get(state.source_type, Path("output/normalizer/web"))
    source_md_path = normalizer_dir / f"{state.source_id}.md"

    if not source_md_path.exists():
        state.stages.ingest = "error"
        state.error = f"Normalizer 출력 파일을 찾을 수 없습니다: {source_md_path}"
        _update_meta(state)
        return state

    try:
        client = _get_client()
        source_md = source_md_path.read_text(encoding="utf-8")
        index_content = WIKI_INDEX.read_text(encoding="utf-8") if WIKI_INDEX.exists() else ""

        # Step A
        understanding = _step_a_understand(client, source_md)

        # Step B
        affected_raw = _step_b_find_affected(client, understanding, index_content)

        # Step C
        affected = _step_c_validate_pages(affected_raw)

        # Step D — 영향 페이지별 계획
        plans: list[dict] = []

        for page_path in affected.get("affected_pages", []):
            plan = _step_d_plan_page(
                client, page_path, source_md, understanding, is_new=False
            )
            plans.append(plan)

        for page_info in affected.get("new_pages", []):
            plan = _step_d_plan_page(
                client,
                page_info["path"],
                source_md,
                understanding,
                is_new=True,
                page_info=page_info,
            )
            plans.append(plan)

        # Step E
        created, updated, mappings = _step_e_execute(
            plans, state.source_id, source_md, state.source_type
        )
        _write_mapping(state.source_id, state.source_type, mappings)

        # Step F
        state.created_wiki_pages = created
        state.updated_wiki_pages = updated
        state.stages.ingest = "done"
        state.timings.ingest_ended_at = time.time()

    except ValueError as e:
        state.stages.ingest = "error"
        state.error = str(e)
    except anthropic.APIError as e:
        state.stages.ingest = "error"
        state.error = f"Claude API 오류: {e}"
    except (json.JSONDecodeError, KeyError) as e:
        state.stages.ingest = "error"
        state.error = f"LLM 응답 파싱 오류: {e}"
    finally:
        _update_meta(state)

    return state
