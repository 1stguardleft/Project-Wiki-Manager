"""
Normalizer/Local — 변환 없이 output/fetcher/local/ → output/normalizer/local/ 복사.

출력: output/normalizer/local/{source_id}.md
"""

import json
import shutil
import time
from pathlib import Path

from models.state import IngestState

INPUT_DIR = Path("output/fetcher/local")
OUTPUT_DIR = Path("output/normalizer/local")
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


def normalizer_local_node(state: IngestState) -> IngestState:
    """output/fetcher/local/{source_id}.md 를 output/normalizer/local/ 에 복사."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    state.stages.normalizer = "running"
    state.timings.normalizer_started_at = time.time()
    _update_meta(state)

    src_path = INPUT_DIR / f"{state.source_id}.md"

    if not src_path.exists():
        state.stages.normalizer = "error"
        state.error = f"Fetcher 출력 파일을 찾을 수 없습니다: {src_path}"
        _update_meta(state)
        return state

    try:
        out_path = OUTPUT_DIR / f"{state.source_id}.md"
        shutil.copy2(src_path, out_path)

        state.stages.normalizer = "done"
        state.timings.normalizer_ended_at = time.time()

    except OSError as e:
        state.stages.normalizer = "error"
        state.error = f"파일 복사 실패: {e}"
    finally:
        _update_meta(state)

    return state
