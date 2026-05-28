#!/usr/bin/env bash
# Project Wiki Manager 상태 스냅샷.
#
# 대상: demo/ (입력 문서), wiki/ (생성 결과), raw/ (적재 원본), .chroma/ (벡터 DB)
# 결과: backups/snapshot-YYYYMMDD-HHMMSS[-라벨].tar.gz
#
# 사용:
#   scripts/backup-state.sh              # 타임스탬프 스냅샷
#   scripts/backup-state.sh 1차-적재완료   # 끝에 라벨 붙임
#   scripts/backup-state.sh --list       # 기존 스냅샷 목록
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUPS="$ROOT/backups"
mkdir -p "$BACKUPS"

if [ "${1:-}" = "--list" ] || [ "${1:-}" = "-l" ]; then
    ls -lh "$BACKUPS"/snapshot-*.tar.gz 2>/dev/null || echo "(스냅샷 없음)"
    exit 0
fi

STAMP=$(date +%Y%m%d-%H%M%S)
LABEL="${1:-}"
NAME="snapshot-${STAMP}${LABEL:+-$LABEL}.tar.gz"
OUT="$BACKUPS/$NAME"

cd "$ROOT"

# 존재하는 대상만 묶는다 — 누락되어 있어도 실패하지 않음.
# .chroma 는 backend/app/config.py 의 CHROMA_DIR (= REPO_ROOT/.chroma) 기준.
INCLUDE=()
for d in demo wiki raw .chroma; do
    [ -e "$d" ] && INCLUDE+=("$d")
done
if [ ${#INCLUDE[@]} -eq 0 ]; then
    echo "백업 대상 폴더가 하나도 없습니다." >&2
    exit 1
fi

tar czf "$OUT" \
    --exclude='__pycache__' \
    --exclude='*.egg-info' \
    "${INCLUDE[@]}"

# 메타데이터(생성 시각·포함된 폴더·페이지 수)도 함께 남김. jq 없이 직접 JSON 빌드.
META="$BACKUPS/${NAME%.tar.gz}.json"
PAGES=$(find "$ROOT/wiki" -name "*.md" ! -name "index.md" ! -name "log.md" 2>/dev/null | wc -l)
RAW=$(find "$ROOT/raw" -name "*.md" 2>/dev/null | wc -l)
DEMO=$(find "$ROOT/demo" -name "*.md" 2>/dev/null | wc -l)
INCLUDES_JSON="["
for i in "${!INCLUDE[@]}"; do
    [ "$i" -gt 0 ] && INCLUDES_JSON+=", "
    INCLUDES_JSON+="\"${INCLUDE[$i]}\""
done
INCLUDES_JSON+="]"
cat > "$META" <<EOF
{
  "created_at": "$(date -Iseconds)",
  "label": "${LABEL}",
  "includes": ${INCLUDES_JSON},
  "counts": { "wiki_pages": $PAGES, "raw_files": $RAW, "demo_files": $DEMO },
  "size_bytes": $(stat -c%s "$OUT" 2>/dev/null || stat -f%z "$OUT")
}
EOF

echo "✓ 백업 완료"
echo "  파일: $OUT"
echo "  크기: $(du -h "$OUT" | cut -f1)"
echo "  포함: ${INCLUDE[*]}"
echo "  카운트: wiki=$PAGES · raw=$RAW · demo=$DEMO"
echo
echo "복구: scripts/restore-state.sh ${NAME}   (또는 latest)"
