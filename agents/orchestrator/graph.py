"""
Orchestrator — LangGraph 파이프라인 그래프 정의.

역할:
- source_id 생성 및 output/meta/{source_id}.json 초기화
- 소스 타입별 조건 분기 (web / confluence / local_md)
- 각 Stage 완료 시 메타데이터 파일 갱신
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path

from langgraph.graph import END, StateGraph

from agents.fetcher.confluence.fetcher import fetcher_confluence_node
from agents.fetcher.local.fetcher import fetcher_local_node
from agents.fetcher.web.fetcher import fetcher_web_node
from agents.index_log.index_log import index_log_node
from agents.ingest.ingest import ingest_node
from agents.normalizer.confluence.normalizer import normalizer_confluence_node
from agents.normalizer.local.normalizer import normalizer_local_node
from agents.normalizer.web.normalizer import normalizer_web_node
from models.state import IngestState, SourceType

META_DIR = Path("output/meta")


def _generate_source_id(url: str) -> str:
    """source-id 생성: YYYYMMDD-HHMMSS-{slug}"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", url.lower())
    slug = slug.strip("-")[:50]
    return f"{timestamp}-{slug}"


def _write_meta(state: IngestState) -> None:
    """output/meta/{source_id}.json 생성 또는 갱신."""
    META_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = META_DIR / f"{state.source_id}.json"
    meta = {
        "source_id": state.source_id,
        "type": state.source_type,
        "url": state.url,
        "confluence_page_id": state.confluence_page_id,
        "created_at": datetime.now().isoformat(),
        "stages": state.stages.model_dump(),
        "timings": state.timings.model_dump(),
        "error": state.error,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def orchestrator_node(state: IngestState) -> IngestState:
    """소스 타입 검증 및 메타데이터 초기화."""
    _write_meta(state)
    return state


def route_by_source_type(state: IngestState) -> str:
    return state.source_type


def build_graph() -> StateGraph:
    graph = StateGraph(IngestState)

    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("fetcher_web", fetcher_web_node)
    graph.add_node("fetcher_confluence", fetcher_confluence_node)
    graph.add_node("fetcher_local", fetcher_local_node)
    graph.add_node("normalizer_web", normalizer_web_node)
    graph.add_node("normalizer_confluence", normalizer_confluence_node)
    graph.add_node("normalizer_local", normalizer_local_node)
    graph.add_node("ingest", ingest_node)
    graph.add_node("index_log", index_log_node)

    graph.set_entry_point("orchestrator")

    graph.add_conditional_edges(
        "orchestrator",
        route_by_source_type,
        {
            "web": "fetcher_web",
            "confluence": "fetcher_confluence",
            "local_md": "fetcher_local",
        },
    )

    graph.add_edge("fetcher_web", "normalizer_web")
    graph.add_edge("fetcher_confluence", "normalizer_confluence")
    graph.add_edge("fetcher_local", "normalizer_local")

    graph.add_edge("normalizer_web", "ingest")
    graph.add_edge("normalizer_confluence", "ingest")
    graph.add_edge("normalizer_local", "ingest")

    graph.add_edge("ingest", "index_log")
    graph.add_edge("index_log", END)

    return graph


def create_ingest_state(
    source_type: SourceType,
    url: str,
    confluence_page_id: str = "",
) -> IngestState:
    """IngestState 초기값 생성."""
    source_id = _generate_source_id(url)
    return IngestState(
        source_id=source_id,
        source_type=source_type,
        url=url,
        confluence_page_id=confluence_page_id,
    )


# 컴파일된 그래프 (API에서 import해서 사용)
compiled_graph = build_graph().compile()
