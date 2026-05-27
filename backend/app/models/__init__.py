"""Pydantic request/response models."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class IngestRequest(BaseModel):
    source_type: Literal["url", "file"]
    url: Optional[str] = None
    filename: Optional[str] = None
    content: Optional[str] = None
    conflict_policy: Optional[Literal["manual", "prefer_incoming", "prefer_existing"]] = None


class IngestResponse(BaseModel):
    run_id: str


class QueryRequest(BaseModel):
    question: str
