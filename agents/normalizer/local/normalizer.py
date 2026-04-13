"""
Normalizer/Local — 변환 없이 output/fetcher/local/ → output/normalizer/local/ 복사.

출력: output/normalizer/local/{source_id}.md

TODO: Phase1 Normalizer/Local Stage에서 구현
"""

from models.state import IngestState


def normalizer_local_node(state: IngestState) -> IngestState:
    raise NotImplementedError("Normalizer/Local은 아직 구현되지 않았습니다.")
