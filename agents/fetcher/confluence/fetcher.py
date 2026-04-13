"""
Fetcher/Confluence — Confluence REST API로 Storage Format(XML) 획득, 저장.

출력: output/fetcher/confluence/{source_id}.xml
"""

import json
import os
import time
from pathlib import Path

import httpx

from models.state import IngestState

OUTPUT_DIR = Path("output/fetcher/confluence")
META_DIR = Path("output/meta")

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


def fetcher_confluence_node(state: IngestState) -> IngestState:
    """
    Confluence REST API로 페이지 Storage Format을 가져와
    output/fetcher/confluence/{source_id}.xml 에 저장.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    state.stages.fetcher = "running"
    state.timings.fetcher_started_at = time.time()
    _update_meta(state)

    base_url = os.environ.get("CONFLUENCE_BASE_URL", "").rstrip("/")
    access_token = os.environ.get("CONFLUENCE_ACCESS_TOKEN", "")

    if not base_url:
        state.stages.fetcher = "error"
        state.error = "CONFLUENCE_BASE_URL 환경변수가 설정되지 않았습니다."
        _update_meta(state)
        return state

    if not access_token:
        state.stages.fetcher = "error"
        state.error = "CONFLUENCE_ACCESS_TOKEN 환경변수가 설정되지 않았습니다."
        _update_meta(state)
        return state

    if not state.confluence_page_id:
        state.stages.fetcher = "error"
        state.error = "confluence_page_id가 없습니다."
        _update_meta(state)
        return state

    endpoint = f"{base_url}/rest/api/content/{state.confluence_page_id}?expand=body.storage"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    try:
        response = httpx.get(endpoint, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()

        data = response.json()
        storage_value: str = data["body"]["storage"]["value"]

        out_path = OUTPUT_DIR / f"{state.source_id}.xml"
        out_path.write_text(storage_value, encoding="utf-8")

        state.stages.fetcher = "done"
        state.timings.fetcher_ended_at = time.time()

    except httpx.HTTPStatusError as e:
        state.stages.fetcher = "error"
        state.error = f"Confluence API HTTP {e.response.status_code}: page_id={state.confluence_page_id}"
    except httpx.RequestError as e:
        state.stages.fetcher = "error"
        state.error = f"Confluence API 네트워크 오류: {e}"
    except (KeyError, ValueError) as e:
        state.stages.fetcher = "error"
        state.error = f"Confluence 응답 파싱 오류: {e}"
    finally:
        _update_meta(state)

    return state
