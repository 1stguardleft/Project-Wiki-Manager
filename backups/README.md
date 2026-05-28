# 백업 / 복구 스냅샷

`scripts/backup-state.sh` 가 만든 파일이 여기에 저장됩니다.

각 스냅샷은 두 파일 한 쌍:

- `snapshot-YYYYMMDD-HHMMSS[-라벨].tar.gz` — 실제 데이터
- `snapshot-YYYYMMDD-HHMMSS[-라벨].json` — 메타데이터 (생성 시각·포함 폴더·페이지 수·크기)

## 무엇이 들어있나

| 폴더 | 의미 |
|---|---|
| `demo/` | 입력 문서 (1차/2차/3차 × SDLC 단계 × 도메인/서브도메인 ERP 데모) |
| `wiki/` | 생성된 위키 페이지 + `edges.jsonl` + `index.md` + `log.md` |
| `raw/` | 적재 시 원본 보관 아카이브 |
| `.chroma/` | Chroma 벡터 DB (임베딩 캐시 — 복구 시 다시 임베딩할 필요 없음) |

## 명령어

```bash
# 만들기
scripts/backup-state.sh                        # 타임스탬프
scripts/backup-state.sh 1차-적재완료             # 라벨 붙여서
scripts/backup-state.sh --list                 # 기존 목록

# 되돌리기
scripts/restore-state.sh                       # 가장 최근 스냅샷
scripts/restore-state.sh latest                # 동일
scripts/restore-state.sh snapshot-...-라벨.tar.gz
scripts/restore-state.sh --yes latest          # 확인 프롬프트 건너뛰기
```

복구는 **현재 `demo/ wiki/ raw/ .chroma/` 를 모두 덮어쓰므로**
프롬프트에 `restore` 라고 정확히 입력해야 실행됩니다 (`--yes` 옵션 사용 시 생략).

백엔드가 `uvicorn --reload` 로 떠 있으면 복구 직후 자동 재기동되며,
그렇지 않으면 직접 재기동해야 Chroma 벡터 DB 캐시가 새로고침됩니다.
