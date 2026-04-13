"""
Normalizer/Web — HTML → Markdown 변환.

변환 전략:
  Primary : trafilatura (본문 추출 + markdown 변환)
  Fallback: Jina AI Reader (JS 렌더링 페이지 등 trafilatura 실패 시)

출력: output/normalizer/web/{source_id}.md
"""

import json
import os
import time
from pathlib import Path

import httpx
import trafilatura

from models.state import IngestState

INPUT_DIR = Path("output/fetcher/web")
OUTPUT_DIR = Path("output/normalizer/web")
META_DIR = Path("output/meta")

JINA_TIMEOUT = 60.0


def _update_meta(state: IngestState) -> None:
    meta_path = META_DIR / f"{state.source_id}.json"
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["stages"] = state.stages.model_dump()
    meta["timings"] = state.timings.model_dump()
    meta["error"] = state.error
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _trafilatura_convert(html: str) -> str | None:
    """trafilatura로 HTML → markdown 변환. 결과가 비면 None 반환."""
    result = trafilatura.extract(
        html,
        output_format="markdown",
        include_tables=True,
        include_images=True,
        include_links=True,
        no_fallback=False,
    )
    if result and result.strip():
        return result
    return None


def _jina_convert(url: str) -> str | None:
    """Jina AI Reader로 URL → markdown 변환. 실패 시 None 반환."""
    jina_api_key = os.environ.get("JINA_API_KEY", "")
    headers = {"Accept": "text/markdown"}
    if jina_api_key:
        headers["Authorization"] = f"Bearer {jina_api_key}"

    try:
        response = httpx.get(
            f"https://r.jina.ai/{url}",
            headers=headers,
            timeout=JINA_TIMEOUT,
            follow_redirects=True,
        )
        response.raise_for_status()
        result = response.text.strip()
        return result if result else None
    except (httpx.HTTPStatusError, httpx.RequestError):
        return None


def normalizer_web_node(state: IngestState) -> IngestState:
    """HTML 파일을 읽어 markdown으로 변환 후 output/normalizer/web/{source_id}.md 에 저장."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    state.stages.normalizer = "running"
    state.timings.normalizer_started_at = time.time()
    _update_meta(state)

    html_path = INPUT_DIR / f"{state.source_id}.html"

    if not html_path.exists():
        state.stages.normalizer = "error"
        state.error = f"Fetcher 출력 파일을 찾을 수 없습니다: {html_path}"
        _update_meta(state)
        return state

    try:
        html = html_path.read_text(encoding="utf-8", errors="replace")

        # Primary: trafilatura
        markdown = _trafilatura_convert(html)

        # Fallback: Jina AI Reader
        if markdown is None:
            markdown = _jina_convert(state.url)

        if markdown is None:
            state.stages.normalizer = "error"
            state.error = "trafilatura와 Jina AI Reader 모두 변환에 실패했습니다."
            _update_meta(state)
            return state

        out_path = OUTPUT_DIR / f"{state.source_id}.md"
        out_path.write_text(markdown, encoding="utf-8")

        state.stages.normalizer = "done"
        state.timings.normalizer_ended_at = time.time()

    except OSError as e:
        state.stages.normalizer = "error"
        state.error = f"파일 처리 오류: {e}"
    finally:
        _update_meta(state)

    return state
