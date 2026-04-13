from typing import Literal

from pydantic import BaseModel, Field

SourceType = Literal["web", "confluence", "local_md"]
StageStatus = Literal["pending", "running", "done", "error"]


class StageStatuses(BaseModel):
    fetcher: StageStatus = "pending"
    normalizer: StageStatus = "pending"
    ingest: StageStatus = "pending"
    index_log: StageStatus = "pending"


class StageTimings(BaseModel):
    fetcher_started_at: float = 0.0
    fetcher_ended_at: float = 0.0
    normalizer_started_at: float = 0.0
    normalizer_ended_at: float = 0.0
    ingest_started_at: float = 0.0
    ingest_ended_at: float = 0.0
    index_log_started_at: float = 0.0
    index_log_ended_at: float = 0.0


class IngestState(BaseModel):
    source_id: str
    source_type: SourceType
    url: str                              # 웹/Confluence URL 또는 로컬 파일 경로
    confluence_page_id: str = ""          # Confluence 전용
    stages: StageStatuses = Field(default_factory=StageStatuses)
    timings: StageTimings = Field(default_factory=StageTimings)
    created_wiki_pages: list[str] = Field(default_factory=list)
    updated_wiki_pages: list[str] = Field(default_factory=list)
    error: str = ""
