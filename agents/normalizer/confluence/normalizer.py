"""
Normalizer/Confluence — Confluence Storage Format(XML) → Markdown 변환.

출력: output/normalizer/confluence/{source_id}.md

TODO: Phase1 Normalizer/Confluence Stage에서 구현
"""

from models.state import IngestState


def normalizer_confluence_node(state: IngestState) -> IngestState:
    raise NotImplementedError("Normalizer/Confluence는 아직 구현되지 않았습니다.")
