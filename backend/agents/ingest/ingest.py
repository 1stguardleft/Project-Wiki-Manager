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

핵심 원칙:
  - source에 없는 배경지식/정의/예시를 추가하지 않는다.
  - 같은 상위 주제는 가능한 한 하나의 페이지로 정리한다.
  - 다만 source 내부의 독립 개념/엔티티는 별도 페이지 또는 기존 페이지로 라우팅할 수 있다.
"""

import json
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Any

import anthropic

from backend.models.state import IngestState

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

중요 규칙:
- 문서에 직접 드러난 내용만 사용하세요.
- 외부 지식, 일반 상식, 배경 설명을 보태지 마세요.
- 최종 목적은 문서 생성이 아니라 source 정리와 구조화입니다.
- 섹션별로 어떤 내용이 같은 상위 주제에 속하는지 파악하세요.

문서:
{source_md[:8000]}

응답 형식:
```json
{{
  "summary": "1~3문장 요약",
  "entities": ["엔티티1", "엔티티2"],
  "concepts": ["개념1", "개념2"],
  "key_claims": ["주요 주장1", "주요 주장2"],
  "sections": [
    {{
      "heading": "섹션 제목 또는 첫 문장",
      "summary": "이 섹션이 다루는 source 기반 범위",
      "independent_topic": false
    }}
  ]
}}
```
"""
    response = _llm(client, prompt)
    return _extract_json(response)


# ── Step A-1 — 소스 요약 페이지 생성 ─────────────────────────


def _step_a1_write_source_page(
    client: anthropic.Anthropic,
    source_id: str,
    source_md: str,
    understanding: dict,
) -> str:
    """
    wiki/sources/{source_id}.md 를 생성한다.
    소스 원문을 구조화·정리한 페이지. 외부 지식 추가 없이 source 그대로를 정리한다.
    반환: 생성된 파일 경로 문자열
    """
    prompt = f"""다음 문서를 wiki 소스 요약 페이지로 정리하세요.

## 절대 규칙 — SOURCE-GROUNDED
- source 텍스트만 사용하세요. 한 글자도 외부 지식을 추가하지 마세요.
- 문서의 구조(섹션, 순서)를 최대한 유지하세요.
- 중복 제거, 문장 다듬기는 허용합니다.
- source에 없는 내용이 포함되었다면 삭제하세요.
- 결과는 "이 소스가 무엇을 담고 있는가"를 한눈에 볼 수 있는 페이지여야 합니다.

소스 분석:
- 요약: {understanding.get("summary", "")}
- 주요 엔티티: {understanding.get("entities", [])}
- 주요 개념: {understanding.get("concepts", [])}
- 핵심 주장: {understanding.get("key_claims", [])}

소스 원문:
{source_md[:8000]}

응답 형식:
```json
{{
  "title": "소스 제목 (문서 제목 또는 핵심 주제)",
  "content": "# 제목\\n\\n## 요약\\n...(1~3문장)\\n\\n## 주요 내용\\n...(섹션별 정리)\\n\\n## 핵심 주장\\n..."
}}
```
"""
    response = _llm(client, prompt)
    result = _extract_json(response)

    title = result.get("title", source_id)
    content = result.get("content", "")

    out_path = WIKI_DIR / "sources" / f"{source_id}.md"
    _write_wiki_page(out_path, title, "source", [source_id], content)
    return str(out_path)


# ── Step B — 영향 페이지 파악 ──────────────────────────────


def _step_b_find_affected(
    client: anthropic.Anthropic,
    understanding: dict,
    index_content: str,
) -> dict:
    entities = understanding.get("entities", [])
    concepts = understanding.get("concepts", [])
    summary = understanding.get("summary", "")
    sections = understanding.get("sections", [])

    # 1단계: index.md에서 후보 선별
    prompt_1 = f"""wiki index 파일과 소스 분석 결과를 보고,
영향받을 가능성이 있는 wiki 페이지 후보를 골라주세요.

중요 규칙:
- source에 없는 주제를 새로 꺼내지 마세요.
- 동일 상위 주제를 다루는 섹션들은 가능한 한 하나의 페이지 후보로 모으세요.
- 독립적으로 정의해야 하는 개념/엔티티만 별도 후보로 분리하세요.

소스 요약: {summary}
주요 엔티티: {entities}
주요 개념: {concepts}
섹션 정보: {json.dumps(sections, ensure_ascii=False)}

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

중요 규칙:
- source-grounded 원칙을 지키세요. source에 없는 배경지식을 추가하지 마세요.
- 결과 page 수는 가능한 최소로 유지하세요.
- 같은 상위 주제를 설명하는 섹션은 하나의 페이지로 정리하세요.
- 다만 독립적으로 정의되어야 하는 개념/엔티티는 별도 페이지 또는 기존 페이지로 라우팅할 수 있습니다.
- "파일 하나당 페이지 하나"로 기계적으로 나누지 마세요.

소스 요약: {summary}
주요 엔티티: {entities}
주요 개념: {concepts}
섹션 정보: {json.dumps(sections, ensure_ascii=False)}

후보 페이지 내용:
{json.dumps(candidate_contents, ensure_ascii=False, indent=2) or "(후보 없음)"}

응답 형식:
```json
{{
  "affected_pages": ["wiki/entities/openai.md"],
  "new_pages": [
    {{"path": "wiki/entities/gpt-4.md", "type": "entity", "title": "GPT-4"}},
    {{"path": "wiki/concepts/rlhf.md", "type": "concept", "title": "RLHF"}}
  ],
  "routing_notes": [
    {{"source_section": "섹션명", "target_page": "wiki/entities/openai.md", "reason": "같은 상위 주제로 묶음"}}
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

    SOURCE_GROUNDED_RULES = """
## 절대 규칙 — SOURCE-GROUNDED (반드시 준수)

당신은 source를 wiki 페이지로 옮기는 서기(scribe)입니다. 지식을 생성하는 것이 아닙니다.

[허용]
- source 텍스트를 그대로 옮기거나 문장을 다듬는 것
- source 내 중복 제거
- source 내 여러 섹션을 하나로 묶어 정리하는 것
- source에 명시된 사실을 간결하게 요약하는 것

[절대 금지]
- source에 없는 정의, 설명, 예시, 배경지식 추가
- "일반적으로", "보통", "~라고 알려져 있다" 같은 일반론 문장 작성
- source에 언급되지 않은 관련 개념, 도구, 기술 언급
- source에 없는 섹션 제목 생성
- LLM이 알고 있는 사전 지식으로 내용을 보충하는 것

[자가 검증]
작성 후 각 문장에 대해 "이 내용이 source에 있는가?"를 확인하세요.
없으면 삭제하세요.
"""

    if is_new:
        title = page_info.get("title", Path(page_path).stem)
        page_type = page_info.get("type", "entity")
        prompt = f"""{SOURCE_GROUNDED_RULES}

---

위 규칙을 지켜 새 wiki 페이지를 작성하세요.

페이지 경로: {page_path}
페이지 제목: {title}
페이지 유형: {page_type}

소스 내용 (이 범위에서만 작성):
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
        prompt = f"""{SOURCE_GROUNDED_RULES}

---

위 규칙을 지켜 기존 wiki 페이지를 source 내용으로 갱신하세요.

[갱신 추가 규칙]
- 기존 페이지에서 source와 관련 없는 내용은 그대로 유지하세요 (삭제 금지).
- source에서 새로 확인된 내용만 추가하세요.
- 기존 내용과 source 내용이 겹치면 합치되, source 범위를 벗어나지 마세요.

페이지 경로: {page_path}

기존 페이지 내용:
{existing_content[:4000]}

소스 내용 (이 범위에서만 갱신):
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
    {{"source_paragraph_index": 0, "action": "반영됨", "wiki_section": "개요"}},
    {{"source_paragraph_index": 1, "action": "병합됨", "wiki_section": "배포 전략"}}
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


# ── Step E-1 — 검토 에이전트 ──────────────────────────────


REVIEW_MODEL = "claude-haiku-4-5-20251001"


def _step_e1_review(
    client: anthropic.Anthropic,
    source_md: str,
    wiki_pages: list[str],
    source_id: str,
) -> dict:
    """
    생성/갱신된 wiki 페이지 문장을 source 원문과 비교해
    source에 없는 내용이 포함됐는지 검토한다.

    반환: review 결과 dict (output/meta/{source_id}_review.json 에 저장)
    """
    violations: list[dict] = []

    for page_path_str in wiki_pages:
        page_path = Path(page_path_str)
        if not page_path.exists():
            continue

        wiki_content = page_path.read_text(encoding="utf-8")
        # frontmatter 제거
        wiki_body = re.sub(r"^---[\s\S]+?---\n+", "", wiki_content).strip()

        prompt = f"""당신은 source-grounded 검토자입니다.
wiki 페이지의 각 문장이 아래 source 원문에 근거가 있는지 확인하세요.

판단 기준:
- source 원문에 해당 내용이 직접 언급되어 있으면 → 통과
- source 원문에서 논리적으로 직접 도출 가능하면 → 통과
- source에 없는 외부 지식, 일반론, 배경 설명이면 → 위반

주의: 당신 자신의 외부 지식으로 판단하지 마세요.
오직 아래 source 텍스트에 있는지 없는지만 판단하세요.

---
SOURCE 원문:
{source_md[:6000]}

---
검토할 wiki 페이지 ({page_path_str}):
{wiki_body[:3000]}

---
응답 형식:
```json
{{
  "page": "{page_path_str}",
  "violations": [
    {{
      "sentence": "위반 문장 그대로",
      "reason": "source에 없는 이유 한 줄"
    }}
  ],
  "passed": true
}}
```
위반이 없으면 violations를 빈 배열로, passed를 true로 반환하세요.
"""
        try:
            msg = client.messages.create(
                model=REVIEW_MODEL,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            result = _extract_json(msg.content[0].text)  # type: ignore[union-attr]
            page_violations = result.get("violations", [])
            if page_violations:
                violations.extend(
                    {"page": page_path_str, **v} for v in page_violations
                )
        except Exception:
            # 검토 실패는 ingest 전체를 막지 않음
            pass

    review = {
        "source_id": source_id,
        "pages_reviewed": wiki_pages,
        "violations": violations,
        "passed": len(violations) == 0,
    }

    review_path = META_DIR / f"{source_id}_review.json"
    review_path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return review


# ── Step E-2 — 자동 수정 ──────────────────────────────────


def _step_e2_fix(
    client: anthropic.Anthropic,
    review: dict,
) -> None:
    """
    검토 에이전트가 발견한 위반 문장을 wiki 페이지에서 자동 제거한다.
    페이지별로 위반 목록을 모아 LLM에게 수정 요청.
    """
    # 페이지별 위반 그룹핑
    page_violations: dict[str, list[dict]] = {}
    for v in review.get("violations", []):
        page = v["page"]
        page_violations.setdefault(page, []).append(v)

    for page_path_str, violations in page_violations.items():
        page_path = Path(page_path_str)
        if not page_path.exists():
            continue

        wiki_content = page_path.read_text(encoding="utf-8")
        # frontmatter 분리
        fm_match = re.match(r"^(---[\s\S]+?---\n+)", wiki_content)
        frontmatter = fm_match.group(1) if fm_match else ""
        wiki_body = wiki_content[len(frontmatter):]

        violation_list = "\n".join(
            f'- "{v["sentence"]}" → {v["reason"]}' for v in violations
        )

        prompt = f"""아래 wiki 페이지에서 source-grounded 위반 문장을 제거하세요.

## 규칙
- 위반 문장만 제거하세요. 나머지 내용은 그대로 유지하세요.
- 위반 문장을 다른 말로 바꾸거나 보완하지 마세요. 그냥 삭제하세요.
- 문장 제거 후 문단이 어색해지면 자연스럽게 이어지도록 최소한만 수정하세요.
- 새로운 내용을 추가하지 마세요.

## 제거할 위반 문장
{violation_list}

## 현재 wiki 페이지 본문
{wiki_body}

## 응답 형식
수정된 본문만 반환하세요. frontmatter, 코드 블록, 설명 없이 본문 텍스트만.
"""
        try:
            msg = client.messages.create(
                model=REVIEW_MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            fixed_body = msg.content[0].text.strip()  # type: ignore[union-attr]
            page_path.write_text(frontmatter + fixed_body + "\n", encoding="utf-8")
        except Exception:
            # 수정 실패 시 원본 유지 (로그만)
            pass


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

        # Step A — 소스 이해
        understanding = _step_a_understand(client, source_md)

        # Step A-1 — 소스 요약 페이지 생성 (wiki/sources/{source_id}.md)
        source_page = _step_a1_write_source_page(
            client, state.source_id, source_md, understanding
        )

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

        # Step E — 실행 + 매핑 생성
        created, updated, mappings = _step_e_execute(
            plans, state.source_id, source_md, state.source_type
        )
        _write_mapping(state.source_id, state.source_type, mappings)

        # Step E-1 — 검토 에이전트 (source-grounded 위반 탐지)
        all_wiki_pages = [source_page] + created + updated
        review = _step_e1_review(client, source_md, all_wiki_pages, state.source_id)

        # Step E-2 — 위반 자동 수정
        if not review["passed"]:
            _step_e2_fix(client, review)

        # Step F — IngestState 갱신 (소스 요약 페이지 포함)
        state.created_wiki_pages = [source_page] + created
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
