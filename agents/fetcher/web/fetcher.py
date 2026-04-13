"""
Fetcher/Web — 웹페이지 URL fetch, 원문 HTML 저장.

출력: output/fetcher/web/{source_id}.html
"""

import json
import time
from pathlib import Path

import httpx

from models.state import IngestState

OUTPUT_DIR = Path("output/fetcher/web")
META_DIR = Path("output/meta")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 30.0


def _update_meta(state: IngestState) -> None:
    meta_path = META_DIR / f"{state.source_id}.json"
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["stages"] = state.stages.model_dump()
    meta["timings"] = state.timings.model_dump()
    meta["error"] = state.error
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def fetcher_web_node(state: IngestState) -> IngestState:
    """HTTP GET으로 HTML을 가져와 output/fetcher/web/{source_id}.html 에 저장."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    state.stages.fetcher = "running"
    state.timings.fetcher_started_at = time.time()
    _update_meta(state)

    try:
        response = httpx.get(state.url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        response.raise_for_status()

        out_path = OUTPUT_DIR / f"{state.source_id}.html"
        out_path.write_bytes(response.content)

        state.stages.fetcher = "done"
        state.timings.fetcher_ended_at = time.time()

    except httpx.HTTPStatusError as e:
        state.stages.fetcher = "error"
        state.error = f"HTTP {e.response.status_code}: {state.url}"
    except httpx.RequestError as e:
        state.stages.fetcher = "error"
        state.error = f"네트워크 오류: {e}"
    finally:
        _update_meta(state)

    return state
