"""
FastAPI 서버 — Phase 1 엔드포인트.

엔드포인트:
  POST /ingest/batch               — 멀티 소스 ingest 배치 실행
  GET  /ingest/batch/{id}/stream   — SSE 스트림
  GET  /status/{source_id}         — 단일 소스 상태 조회
  GET  /files                      — 파일 트리 조회
  GET  /files/content              — 파일 내용 조회
  GET  /compare                    — 소스 → wiki 반영 비교
"""

import asyncio
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.agents.orchestrator.graph import compiled_graph, create_ingest_state
from backend.models.state import IngestState

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="project-wiki-manager", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://((localhost|127\.0\.0\.1|0\.0\.0\.0)|(\d{1,3}\.){3}\d{1,3})(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

META_DIR = Path("output/meta")
WIKI_DIR = Path("wiki")

SourceType = Literal["web", "confluence", "local_md"]
StageName = Literal["fetcher", "normalizer", "ingest", "index_log"]
TERMINAL_STAGES = {"done", "error"}
STAGE_NAMES: tuple[StageName, ...] = ("fetcher", "normalizer", "ingest", "index_log")
NORMALIZER_DIR_BY_TYPE = {
    "web": Path("output/normalizer/web"),
    "confluence": Path("output/normalizer/confluence"),
    "local_md": Path("output/normalizer/local"),
}


class SourceRequest(BaseModel):
    type: SourceType
    url: str = ""
    path: str = ""
    page_id: str = ""


class BatchRequest(BaseModel):
    sources: list[SourceRequest]


class BatchResponse(BaseModel):
    batch_id: str
    source_ids: list[str]
    total: int


class BatchEvent(BaseModel):
    event: str
    data: dict
    event_id: int = 0


class BatchRun(BaseModel):
    batch_id: str
    source_ids: list[str]
    total: int
    events: list[BatchEvent] = Field(default_factory=list)
    completed: bool = False
    condition: threading.Condition = Field(default_factory=threading.Condition)

    model_config = {"arbitrary_types_allowed": True}


BATCH_RUNS: dict[str, BatchRun] = {}
BATCH_LOCK = threading.Lock()


def _extract_confluence_page_id(url: str) -> str:
    match = re.search(r"/pages/(\d+)", url)
    if not match:
        raise HTTPException(status_code=400, detail=f"page_id를 추출할 수 없습니다: {url}")
    return match.group(1)


def _resolve_source_input(source: SourceRequest) -> tuple[str, str]:
    if source.type == "local_md":
        if not source.path:
            raise HTTPException(status_code=400, detail="local_md 소스는 path가 필요합니다.")
        return source.path, ""

    if not source.url:
        raise HTTPException(status_code=400, detail=f"{source.type} 소스는 url이 필요합니다.")

    if source.type == "confluence":
        return source.url, source.page_id or _extract_confluence_page_id(source.url)

    return source.url, ""


def _meta_path(source_id: str) -> Path:
    return META_DIR / f"{source_id}.json"


def _mapping_path(source_id: str) -> Path:
    return META_DIR / f"{source_id}_mapping.json"


def _read_json(path: Path) -> dict:
    last_error: Exception | None = None
    for _ in range(8):
        try:
            content = path.read_text(encoding="utf-8")
            if not content.strip():
                raise json.JSONDecodeError("empty content", content, 0)
            return json.loads(content)
        except (OSError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(0.05)
    raise RuntimeError(f"JSON 파일을 안정적으로 읽지 못했습니다: {path}") from last_error


def _write_initial_meta(source_id: str, source_type: SourceType, url: str, confluence_page_id: str) -> None:
    META_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "source_id": source_id,
        "type": source_type,
        "url": url,
        "confluence_page_id": confluence_page_id,
        "created_at": datetime.now().isoformat(),
        "stages": {
            "fetcher": "pending",
            "normalizer": "pending",
            "ingest": "pending",
            "index_log": "pending",
        },
        "timings": {
            "fetcher_started_at": 0.0,
            "fetcher_ended_at": 0.0,
            "normalizer_started_at": 0.0,
            "normalizer_ended_at": 0.0,
            "ingest_started_at": 0.0,
            "ingest_ended_at": 0.0,
            "index_log_started_at": 0.0,
            "index_log_ended_at": 0.0,
        },
        "error": "",
    }
    _meta_path(source_id).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _stage_elapsed_ms(meta: dict, stage: StageName) -> int:
    timings = meta.get("timings", {})
    started_at = timings.get(f"{stage}_started_at", 0.0) or 0.0
    ended_at = timings.get(f"{stage}_ended_at", 0.0) or 0.0
    if started_at <= 0:
        return 0
    if ended_at > 0:
        return int((ended_at - started_at) * 1000)
    return int((time.time() - started_at) * 1000)


def _publish_event(batch: BatchRun, event_name: str, data: dict) -> None:
    batch_event = BatchEvent(event=event_name, data=data, event_id=len(batch.events))
    with batch.condition:
        batch.events.append(batch_event)
        batch.condition.notify_all()


def _monitor_source_progress(batch: BatchRun, source_id: str, worker: threading.Thread) -> None:
    last_statuses = {stage: "pending" for stage in STAGE_NAMES}
    last_error = ""

    while worker.is_alive():
        meta_file = _meta_path(source_id)
        if meta_file.exists():
            meta = _read_json(meta_file)
            stages = meta.get("stages", {})
            for stage in STAGE_NAMES:
                status = stages.get(stage, "pending")
                if status != last_statuses[stage]:
                    _publish_event(
                        batch,
                        "stage_update",
                        {
                            "source_id": source_id,
                            "stage": stage,
                            "status": status,
                            "elapsed_ms": _stage_elapsed_ms(meta, stage),
                            "error": meta.get("error", ""),
                        },
                    )
                    last_statuses[stage] = status

            error = meta.get("error", "")
            if error and error != last_error:
                _publish_event(
                    batch,
                    "stage_update",
                    {
                        "source_id": source_id,
                        "stage": "unknown",
                        "status": "error",
                        "elapsed_ms": 0,
                        "error": error,
                    },
                )
                last_error = error

        time.sleep(0.2)

    if _meta_path(source_id).exists():
        meta = _read_json(_meta_path(source_id))
        stages = meta.get("stages", {})
        for stage in STAGE_NAMES:
            status = stages.get(stage, "pending")
            if status != last_statuses[stage]:
                _publish_event(
                    batch,
                    "stage_update",
                    {
                        "source_id": source_id,
                        "stage": stage,
                        "status": status,
                        "elapsed_ms": _stage_elapsed_ms(meta, stage),
                        "error": meta.get("error", ""),
                    },
                )
                last_statuses[stage] = status


def _coerce_state(value: object) -> IngestState | None:
    if isinstance(value, IngestState):
        return value
    if isinstance(value, dict):
        return IngestState.model_validate(value)
    return None


def _run_batch(batch_id: str, states: list[IngestState]) -> None:
    with BATCH_LOCK:
        batch = BATCH_RUNS[batch_id]

    started_at = time.time()
    _publish_event(batch, "batch_start", {"batch_id": batch_id, "total": len(states)})

    try:
        for index, state in enumerate(states, start=1):
            _publish_event(
                batch,
                "source_start",
                {
                    "source_id": state.source_id,
                    "index": index,
                    "total": len(states),
                    "source_type": state.source_type,
                    "url": state.url,
                },
            )

            result_holder: dict[str, object] = {}

            def _invoke_graph() -> None:
                result_holder["state"] = compiled_graph.invoke(state)

            worker = threading.Thread(target=_invoke_graph, daemon=True)
            worker.start()
            _monitor_source_progress(batch, state.source_id, worker)
            worker.join()

            final_state = _coerce_state(result_holder.get("state"))
            if final_state is None:
                _publish_event(
                    batch,
                    "source_done",
                    {
                        "source_id": state.source_id,
                        "index": index,
                        "total": len(states),
                        "status": "error",
                        "created_wiki_pages": [],
                        "updated_wiki_pages": [],
                        "error": "배치 실행 중 결과를 수집하지 못했습니다.",
                    },
                )
                continue

            status = "done" if all(
                getattr(final_state.stages, stage) in TERMINAL_STAGES and getattr(final_state.stages, stage) != "error"
                for stage in STAGE_NAMES
            ) else "error"

            _publish_event(
                batch,
                "source_done",
                {
                    "source_id": final_state.source_id,
                    "index": index,
                    "total": len(states),
                    "status": status,
                    "created_wiki_pages": final_state.created_wiki_pages,
                    "updated_wiki_pages": final_state.updated_wiki_pages,
                    "error": final_state.error,
                },
            )
    finally:
        _publish_event(
            batch,
            "batch_done",
            {
                "batch_id": batch_id,
                "total": len(states),
                "total_elapsed_ms": int((time.time() - started_at) * 1000),
            },
        )
        batch.completed = True
        with batch.condition:
            batch.condition.notify_all()


UPLOAD_DIR = Path("raw/uploads")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.post("/upload/local")
async def upload_local_file(file: UploadFile = File(...)) -> dict:
    """로컬 MD 파일을 서버에 업로드하고 저장 경로를 반환한다."""
    filename = file.filename or ""
    if not filename.endswith(".md"):
        raise HTTPException(status_code=400, detail=".md 파일만 업로드 가능합니다.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # 동일 파일명 충돌 방지: timestamp prefix
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_name = re.sub(r"[^\w\-.]", "_", filename)
    save_path = UPLOAD_DIR / f"{timestamp}-{safe_name}"

    content = await file.read()
    save_path.write_bytes(content)

    return {"path": str(save_path), "filename": filename}


@app.post("/ingest/batch", response_model=BatchResponse)
def ingest_batch(request: BatchRequest) -> BatchResponse:
    if not request.sources:
        raise HTTPException(status_code=400, detail="최소 1개 이상의 소스가 필요합니다.")

    batch_id = f"batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    states = []
    source_ids = []

    for source in request.sources:
        url, confluence_page_id = _resolve_source_input(source)
        state = create_ingest_state(
            source_type=source.type,
            url=url,
            confluence_page_id=confluence_page_id,
        )
        states.append(state)
        source_ids.append(state.source_id)
        _write_initial_meta(state.source_id, state.source_type, state.url, state.confluence_page_id)

    batch = BatchRun(batch_id=batch_id, source_ids=source_ids, total=len(states))
    with BATCH_LOCK:
        BATCH_RUNS[batch_id] = batch

    threading.Thread(target=_run_batch, args=(batch_id, states), daemon=True).start()

    return BatchResponse(batch_id=batch_id, source_ids=source_ids, total=len(states))


@app.get("/ingest/batch/{batch_id}/stream")
async def ingest_batch_stream(batch_id: str):
    with BATCH_LOCK:
        batch = BATCH_RUNS.get(batch_id)

    if batch is None:
        raise HTTPException(status_code=404, detail=f"batch_id를 찾을 수 없습니다: {batch_id}")

    async def event_generator():
        replay_from = 0
        while True:
            def _wait_for_next_event() -> BatchEvent | None:
                with batch.condition:
                    batch.condition.wait_for(lambda: replay_from < len(batch.events) or batch.completed)
                    if replay_from < len(batch.events):
                        return batch.events[replay_from]
                    return None

            next_event = await asyncio.to_thread(_wait_for_next_event)
            if next_event is None:
                break
            replay_from += 1
            yield {
                "event": next_event.event,
                "id": str(next_event.event_id),
                "data": json.dumps(next_event.data, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@app.get("/status/{source_id}")
def get_status(source_id: str) -> dict:
    meta_path = _meta_path(source_id)
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail=f"source_id를 찾을 수 없습니다: {source_id}")
    return _read_json(meta_path)


@app.get("/files")
def list_files(base: str = "wiki") -> dict:
    base_path = Path(base)
    if not base_path.exists():
        raise HTTPException(status_code=404, detail=f"경로를 찾을 수 없습니다: {base}")

    files = [str(path) for path in sorted(base_path.rglob("*.md"))]
    return {"base": base, "files": files}


@app.get("/files/content")
def get_file_content(path: str) -> dict:
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"파일을 찾을 수 없습니다: {path}")
    if file_path.suffix != ".md":
        raise HTTPException(status_code=400, detail="markdown 파일만 조회 가능합니다.")
    return {"path": path, "content": file_path.read_text(encoding="utf-8")}


@app.get("/compare")
def compare(source_ids: str, wiki_path: str) -> dict:
    wiki_file = Path(wiki_path)
    if not wiki_file.exists():
        raise HTTPException(status_code=404, detail=f"wiki 파일을 찾을 수 없습니다: {wiki_path}")

    parsed_source_ids = [source_id.strip() for source_id in source_ids.split(",") if source_id.strip()]
    if not parsed_source_ids:
        raise HTTPException(status_code=400, detail="최소 1개 이상의 source_id가 필요합니다.")

    sources_payload = []
    for source_id in parsed_source_ids:
        meta_file = _meta_path(source_id)
        mapping_file = _mapping_path(source_id)
        if not meta_file.exists():
            raise HTTPException(status_code=404, detail=f"source_id를 찾을 수 없습니다: {source_id}")

        meta = _read_json(meta_file)
        source_type = meta.get("type", "web")
        normalizer_path = NORMALIZER_DIR_BY_TYPE.get(source_type, Path("output/normalizer/web")) / f"{source_id}.md"
        mappings = _read_json(mapping_file).get("mappings", []) if mapping_file.exists() else []

        sources_payload.append(
            {
                "source_id": source_id,
                "content": normalizer_path.read_text(encoding="utf-8") if normalizer_path.exists() else "",
                "mappings": [mapping for mapping in mappings if mapping.get("wiki_page") == wiki_path],
            }
        )

    return {
        "wiki_page": {
            "path": wiki_path,
            "content": wiki_file.read_text(encoding="utf-8"),
            "sources": parsed_source_ids,
        },
        "sources": sources_payload,
    }
