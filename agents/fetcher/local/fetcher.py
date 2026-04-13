"""
Fetcher/Local — 로컬 MD 파일을 output/fetcher/local/ 에 복사.

출력: output/fetcher/local/{source_id}.md

TODO: Phase1 Fetcher/Local Stage에서 구현
"""

from models.state import IngestState


def fetcher_local_node(state: IngestState) -> IngestState:
    raise NotImplementedError("Fetcher/Local은 아직 구현되지 않았습니다.")
