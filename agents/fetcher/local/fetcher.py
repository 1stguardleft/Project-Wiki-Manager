"""
Fetcher/Local — 로컬 MD 파일을 output/fetcher/local/ 에 복사.

출력: output/fetcher/local/{source_id}.md
"""

import json
import shutil
import time
from pathlib import Path

from models.state import IngestState

OUTPUT_DIR = Path("output/fetcher/local")
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


def fetcher_local_node(state: IngestState) -> IngestState:
    """
    로컬 MD 파일을 읽어 output/fetcher/local/{source_id}.md 에 복사.
    state.url 이 로컬 파일 경로로 사용됨.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    state.stages.fetcher = "running"
    state.timings.fetcher_started_at = time.time()
    _update_meta(state)

    src_path = Path(state.url)

    if not src_path.exists():
        state.stages.fetcher = "error"
        state.error = f"파일을 찾을 수 없습니다: {state.url}"
        _update_meta(state)
        return state

    if src_path.suffix.lower() != ".md":
        state.stages.fetcher = "error"
        state.error = f".md 파일만 지원합니다: {state.url}"
        _update_meta(state)
        return state

    try:
        out_path = OUTPUT_DIR / f"{state.source_id}.md"
        shutil.copy2(src_path, out_path)

        state.stages.fetcher = "done"
        state.timings.fetcher_ended_at = time.time()

    except OSError as e:
        state.stages.fetcher = "error"
        state.error = f"파일 복사 실패: {e}"
    finally:
        _update_meta(state)

    return state
