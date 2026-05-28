#!/usr/bin/env bash
# Project Wiki Manager 스냅샷 복구.
#
# 사용:
#   scripts/restore-state.sh                       # 가장 최근 스냅샷
#   scripts/restore-state.sh latest                # 동일
#   scripts/restore-state.sh snapshot-...-라벨.tar.gz
#   scripts/restore-state.sh --yes <스냅샷>        # 확인 프롬프트 건너뛰기
#
# 동작:
#   1) 현재 demo/ wiki/ raw/ .chroma/ 를 깨끗이 비움
#   2) 스냅샷을 동일 위치에 풀어놓음
#   3) 백엔드가 uvicorn --reload 모드면 main.py 를 touch 해서 자동 재기동 (벡터 DB 캐시 새로고침)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUPS="$ROOT/backups"

AUTO_YES=0
if [ "${1:-}" = "--yes" ] || [ "${1:-}" = "-y" ]; then
    AUTO_YES=1
    shift
fi

TARGET="${1:-latest}"

if [ "$TARGET" = "latest" ]; then
    SNAP=$(ls -1t "$BACKUPS"/snapshot-*.tar.gz 2>/dev/null | head -1 || true)
    [ -n "$SNAP" ] || { echo "스냅샷이 없습니다: $BACKUPS" >&2; exit 1; }
elif [ -f "$TARGET" ]; then
    SNAP="$TARGET"
elif [ -f "$BACKUPS/$TARGET" ]; then
    SNAP="$BACKUPS/$TARGET"
else
    echo "스냅샷을 찾을 수 없습니다: $TARGET" >&2
    echo "사용 가능 목록:" >&2
    ls -1 "$BACKUPS"/snapshot-*.tar.gz 2>/dev/null >&2 || echo "  (없음)" >&2
    exit 1
fi

echo "복구 대상: $SNAP"
META="${SNAP%.tar.gz}.json"
if [ -f "$META" ]; then
    echo "메타: $(cat "$META")"
fi
echo
echo "주의: 다음 폴더가 모두 삭제 후 스냅샷으로 대체됩니다:"
echo "  - $ROOT/demo"
echo "  - $ROOT/wiki"
echo "  - $ROOT/raw"
echo "  - $ROOT/.chroma"
echo

if [ "$AUTO_YES" -ne 1 ]; then
    read -r -p "복구하려면 'restore' 입력: " ans
    [ "$ans" = "restore" ] || { echo "취소됨"; exit 1; }
fi

cd "$ROOT"
rm -rf demo wiki raw .chroma
tar xzf "$SNAP"

# 백엔드가 살아 있으면 reload 트리거 (uvicorn --reload 모드일 때만 의미 있음)
if [ -f "$ROOT/backend/app/main.py" ]; then
    touch "$ROOT/backend/app/main.py" || true
fi

echo "✓ 복구 완료"
PAGES=$(find "$ROOT/wiki" -name "*.md" ! -name "index.md" ! -name "log.md" 2>/dev/null | wc -l)
RAW=$(find "$ROOT/raw" -name "*.md" 2>/dev/null | wc -l)
DEMO=$(find "$ROOT/demo" -name "*.md" 2>/dev/null | wc -l)
echo "  현재 카운트: wiki=$PAGES · raw=$RAW · demo=$DEMO"
echo
echo "참고: 백엔드가 떠 있다면 자동 reload되며, 안 떠 있다면 직접 재기동하세요."
