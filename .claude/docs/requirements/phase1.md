# Requirements — Phase 1

Phase 1 (Ingest Feasibility 검증)에 해당하는 요구사항.

## 소스 타입

| 타입 | 설명 | Fetcher | Normalizer |
|------|------|---------|------------|
| 웹페이지 (URL) | HTTP로 HTML 획득 | ✅ | ✅ HTML → MD |
| Confluence 페이지 | REST API로 Storage Format 획득 | ✅ | ✅ XML → MD |
| 로컬 MD 파일 | 이미 markdown, 변환 불필요 | 복사만 | 복사만 |

## Orchestrator

- 사용자 명령에서 소스 타입(web / confluence / local_md)을 판별한다.
- 소스 타입에 따라 적절한 파이프라인 경로로 분기한다.
- 각 Stage 완료 시 `output/meta/{source-id}.json`의 상태를 갱신한다.
- 멀티 소스는 순차 처리한다 (wiki 파일 쓰기 충돌 방지).
- 배치 실행은 `batch_id` 단위로 관리하며, 서버는 배치 진행 이벤트를 SSE로 제공한다.

## Fetcher

- 원문을 그대로 가져와 `output/fetcher/{type}/{source-id}.{ext}`에 저장한다.
- 변환하지 않는다.
- Web: HTTP GET으로 HTML 획득 → `output/fetcher/web/{source-id}.html`
- Confluence: REST API (`/rest/api/content/{id}?expand=body.storage`)로 Storage Format 획득 → `output/fetcher/confluence/{source-id}.xml`
- Local MD: `output/fetcher/local/{source-id}.md`로 파일 복사

## Normalizer

Stage 1: Markdown best-effort 변환

- Web: trafilatura(primary) → Jina AI Reader(fallback) 로 HTML → markdown 변환 → `output/normalizer/web/{source-id}.md`
- Confluence: beautifulsoup4로 Storage Format → markdown 변환 → `output/normalizer/confluence/{source-id}.md`
- Local MD: 변환 없이 `output/normalizer/local/{source-id}.md`로 복사

변환 공통 규칙:
- 단순 테이블 → markdown 테이블 변환
- 복잡한 테이블(셀 병합) → 텍스트 대체 (손실 허용)
- 외부 이미지 → `![alt](url)` 변환
- Confluence 첨부 이미지 → 링크만 기록
- Confluence 매크로 → 지원 가능한 것만 변환

## Ingest

- `output/normalizer/{type}/{source-id}.md` 읽기
- Wiki-centric 방식: 소스 전체 이해 → 소스 요약 페이지 생성 → 영향 페이지 파악(2단계 탐색) → 페이지 정체성 검증 → 페이지별 재합성 → 검토 → 자동 수정
- Ingest의 목적은 LLM이 새 지식을 추가하는 것이 아니라, 사용자가 준 source/raw를 정리하고 구조화하는 것이다.
- source에 없는 배경지식, 정의, 예시, 일반론은 추가하지 않는다 (SOURCE-GROUNDED 원칙).
- 소스 1개 ingest 시 반드시 `wiki/sources/{source-id}.md` 소스 요약 페이지를 생성한다.
- 신규 주제: `wiki/entities/`, `wiki/concepts/` 에 페이지 생성
- 유사 주제: 무조건 하나로 합치지 않고, source의 섹션 의미에 따라 기존 페이지에 병합하거나 별도 페이지로 분리한다.
- 같은 상위 주제를 설명하는 섹션들은 가능한 한 하나의 페이지로 정리하고, 독립적으로 정의되어야 하는 개념/엔티티만 별도 페이지로 분리한다.
- 처리 완료 후 소스↔wiki 매핑 정보를 `output/meta/{source-id}_mapping.json`에 저장

### SOURCE-GROUNDED 검토 및 자동 수정

- 페이지 생성/갱신 후 검토 에이전트(Haiku)가 source 원문과 wiki 페이지를 문장 단위로 비교한다.
- source에 없는 문장이 탐지되면 자동 수정 에이전트(Haiku)가 해당 문장을 삭제한다.
- 검토 결과는 `output/meta/{source-id}_review.json`에 저장한다 (감사 로그).
- 사람의 개입 없이 자동으로 처리된다. 수정 실패 시 원본 유지, ingest는 완료 처리된다.

## Index / Log

- `wiki/index.md`: 신규 페이지 생성 시에만 항목 추가 (링크 + 한 줄 요약)
- `wiki/log.md`: `## [YYYY-MM-DD] ingest | {source-id}` 형식으로 항목 추가

## FE 요구사항

### 전체 UX 흐름

```
[소스 입력] → [처리 요청] → [워크플로우 팝업] → [결과 비교 뷰]
```

### 1. 소스 입력

- "소스 추가" 버튼으로 소스를 멀티로 지정할 수 있어야 한다.
- 소스 타입은 세 가지 중 선택:
  - 웹 페이지 URL (텍스트 입력)
  - Confluence 페이지 URL (텍스트 입력, page_id 자동 추출)
  - 로컬 MD 파일 경로 (파일 경로 입력 또는 파일 선택)
- Confluence URL 입력 시 `pages/{page_id}/` 패턴으로 page_id 자동 추출 및 표시
- 추가된 소스는 목록으로 표시되며 개별 삭제 가능
- 소스가 1개 이상일 때 "처리 시작" 버튼 활성화

### 2. 워크플로우 팝업

작업 요청 시 팝업이 열리며 에이전트별 처리 현황 및 결과를 실시간으로 확인할 수 있어야 한다.

- 배치 내 소스를 순차적으로 처리하며, 현재 처리 중인 소스와 전체 진행률을 표시
- 각 소스에 대해 파이프라인 단계(Orchestrator → Fetcher → Normalizer → Ingest → Index/Log)를 흐름도로 시각화
- 각 에이전트 노드에 실시간 상태 표시: 대기 / 진행 중 / 완료 / 오류
- 완료된 에이전트 노드 클릭 시 해당 단계의 산출물 미리보기 가능
- 단계별 소요 시간 표시
- 오류 발생 시 해당 노드에 오류 메시지 표시 (오류 재시도는 추후 고려)
- 전체 완료 시 "결과 보기" 버튼으로 결과 뷰로 전환

백엔드 SSE 이벤트 계약:
- `batch_start`: 배치 시작, 전체 소스 수 전달
- `source_start`: 현재 처리할 소스 시작
- `stage_update`: 단계별 상태 변경 (`fetcher`, `normalizer`, `ingest`, `index_log`) 및 소요 시간 전달
- `source_done`: 단일 소스 처리 완료
- `batch_done`: 배치 전체 완료

### 3. 결과 비교 뷰

처리 완료 후 원본 소스 기준으로 어떤 부분이 어떻게 처리되었는지 git diff 스타일로 확인할 수 있어야 한다.

- 좌측: 원본 소스 내용 (normalized markdown 기준)
- 우측: 변환 결과 wiki 페이지의 diff (추가된 줄 초록색, 제거된 줄 빨간색, 컨텍스트 줄 회색)
- 여러 소스 입력 시 소스별 탭으로 전환
- 우측 wiki 페이지가 여러 개일 경우 드롭다운으로 선택 가능
- 원본 단락 클릭 시 대응하는 우측 wiki 부분으로 스크롤 + 하이라이트
- 원본 기준 처리 결과 레이블: 반영됨 / 요약됨 / 병합됨 / 제외됨

현재 Phase 1 API 기준:
- `/compare`는 서버에서 완성된 diff를 계산하지 않고, `wiki_page + normalized source + mapping` 데이터를 반환한다.
- git diff 스타일 렌더링은 프런트엔드에서 구성한다.

Ingest 판단 기준:
- 같은 주제의 소스 2개가 들어오면 결과가 1개 MD 파일이 될 수 있다.
- 다만 source 내부 일부가 독립 개념/엔티티라면 해당 부분만 별도 문서로 정의되거나 기존 문서에 병합될 수 있다.
- 즉, 병합 단위는 "파일 전체"가 아니라 "의미 있는 섹션"이다.

## 검증 기준

- 유사 페이지 2개 + 다른 페이지 1개로 전체 파이프라인 실행 성공
- `output/meta/{source-id}.json` 모든 stage 상태가 `"done"`
- `output/meta/{source-id}_mapping.json` 생성 확인
- `output/meta/{source-id}_review.json` 생성 확인
- `wiki/sources/{source-id}.md` 소스 요약 페이지 생성 확인
- `wiki/index.md`, `wiki/log.md` 올바르게 갱신됨
- 유사 페이지 2개가 필요 시 하나의 페이지로 통합되며, 독립 섹션은 별도 페이지 또는 기존 페이지로 라우팅됨
- 최종 wiki 문장에 source에 없는 일반 지식이 임의로 추가되지 않음
