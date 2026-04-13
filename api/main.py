"""
FastAPI 서버 — Phase 1 엔드포인트.

엔드포인트:
  POST /ingest/batch          — 멀티 소스 ingest 배치 실행
  GET  /ingest/batch/{id}/stream — SSE 스트림
  GET  /status/{source_id}    — 단일 소스 상태 조회
  GET  /files                 — 파일 트리 조회
  GET  /files/content         — 파일 내용 조회
  GET  /compare               — 소스 → wiki 반영 비교

TODO: 배치 실행 및 SSE 스트리밍은 이후 Stage에서 구현
"""

import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="project-wiki-manager", version="0.1.0")

META_DIR = Path("output/meta")


# ── 요청/응답 모델 ──────────────────────────────────────────


class SourceRequest(BaseModel):
    type: str          # "web" | "confluence" | "local_md"
    url: str = ""
    path: str = ""     # local_md 전용
    page_id: str = ""  # confluence 전용


class BatchRequest(BaseModel):
    sources: list[SourceRequest]


class BatchResponse(BaseModel):
    batch_id: str
    source_ids: list[str]
    total: int


# ── 엔드포인트 ──────────────────────────────────────────────


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.post("/ingest/batch", response_model=BatchResponse)
def ingest_batch(request: BatchRequest) -> BatchResponse:
    """
    멀티 소스 ingest 배치 실행.
    TODO: 실제 배치 실행 및 SSE 스트리밍 구현
    """
    raise HTTPException(status_code=501, detail="아직 구현되지 않았습니다.")


@app.get("/ingest/batch/{batch_id}/stream")
def ingest_batch_stream(batch_id: str):
    """
    SSE 스트림 — 배치 전체 처리 현황 실시간 전송.
    TODO: SSE 스트리밍 구현
    """
    raise HTTPException(status_code=501, detail="아직 구현되지 않았습니다.")


@app.get("/status/{source_id}")
def get_status(source_id: str) -> dict:
    """단일 소스 처리 상태 조회."""
    meta_path = META_DIR / f"{source_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail=f"source_id를 찾을 수 없습니다: {source_id}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


@app.get("/files")
def list_files(base: str = "wiki") -> dict:
    """파일 트리 조회."""
    base_path = Path(base)
    if not base_path.exists():
        raise HTTPException(status_code=404, detail=f"경로를 찾을 수 없습니다: {base}")

    files = [str(p) for p in sorted(base_path.rglob("*.md"))]
    return {"base": base, "files": files}


@app.get("/files/content")
def get_file_content(path: str) -> dict:
    """파일 내용 조회."""
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"파일을 찾을 수 없습니다: {path}")
    if not file_path.suffix == ".md":
        raise HTTPException(status_code=400, detail="markdown 파일만 조회 가능합니다.")
    return {"path": path, "content": file_path.read_text(encoding="utf-8")}


@app.get("/compare")
def compare(source_ids: str, wiki_path: str) -> dict:
    """
    소스 → wiki 반영 비교.
    TODO: mapping.json 기반 비교 뷰 구현
    """
    raise HTTPException(status_code=501, detail="아직 구현되지 않았습니다.")
