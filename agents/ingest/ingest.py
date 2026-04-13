"""
Ingest Agent — Markdown → Wiki 페이지 생성/갱신 (Wiki-centric 방식).

출력: wiki/sources/, wiki/entities/, wiki/concepts/
      output/meta/{source_id}_mapping.json

TODO: Phase1 Ingest Stage에서 구현
"""

from models.state import IngestState


def ingest_node(state: IngestState) -> IngestState:
    raise NotImplementedError("Ingest Agent는 아직 구현되지 않았습니다.")
