# Plan

## 용어 정의

| 용어 | 설명 |
|------|------|
| **Phase** | MVP 개발의 Sprint 단위. 독립적으로 검증 가능한 목표를 가진다. |
| **Stage** | Phase 내 개별 Task의 구현 단계. 하나의 Stage가 완료되어야 다음 Stage로 진행한다. |

---

## MVP 범위

| 타입 | 설명 |
|------|------|
| 웹페이지 | URL을 입력하면 LLM이 내용을 읽고 wiki에 통합 |
| WIKI (Confluence) | Confluence 페이지를 소스로 읽어 wiki에 통합 |

그 외 소스 타입(PDF, 로컬 파일, Slack 등)은 MVP 범위 외.

---

## Phase 1 — Ingest Feasibility 검증 ← 현재

**목표**: Ingest 파이프라인이 end-to-end로 동작하는지 최소 범위로 검증.

**검증 기준**
- 유사 페이지 2개 + 다른 페이지 1개로 전체 파이프라인 실행 성공
- `wiki/index.md`, `wiki/log.md`가 올바르게 생성·갱신됨
- 유사 페이지 2개가 하나로 합쳐지거나 상호 참조로 연결됨

**범위 외** → Phase 2, 3으로 이월
- Query, Lint 기능
- 기존 wiki 갱신 품질 검증
- 모순·중복 감지

### Orchestrator

| Stage | 내용 |
|-------|------|
| Stage 1 | 명령 수신 → 에이전트 호출 흐름 골격 구현 |

### Fetcher

| Stage | 대상 | 내용 |
|-------|------|------|
| Stage 1 | Web | 웹페이지 URL fetch, 원문 HTML을 `output/fetcher/web/`에 저장 |
| Stage 2 | Confluence | Confluence REST API로 페이지 획득, 원문을 `output/fetcher/confluence/`에 저장 |

### Normalizer

| Stage | 대상 | 내용 |
|-------|------|------|
| Stage 1 | Web / Confluence | **Markdown best-effort 변환** — 원문을 markdown으로 최대한 변환, 표현 불가 요소는 손실 허용. 결과를 `output/normalizer/{web\|confluence}/`에 저장 |

best-effort 변환 기준:

| 요소 | 처리 방식 |
|------|-----------|
| 단순 테이블 | markdown 테이블로 변환 |
| 복잡한 테이블 (셀 병합 등) | 단순화하거나 텍스트로 대체 (손실 허용) |
| 외부 URL 이미지 | `![alt](url)` 로 변환 |
| Confluence 첨부 이미지 | 링크만 기록, 이미지 내용 손실 허용 |
| Confluence 매크로 | 지원 가능한 것만 변환, 나머지는 텍스트로 대체 |

### Ingest

Wiki-centric 방식으로 동작한다. 소스를 청크로 배분하는 것이 아니라 wiki 페이지를 최적 상태로 유지하는 것을 목표로 한다.

| Stage | 내용 |
|-------|------|
| Stage 1 | **Wiki-centric Ingest** — 소스 전체 이해 → 영향 페이지 파악(2단계 탐색) → 페이지 정체성 검증 → 페이지별 재합성. frontmatter `sources` 필드로 역추적 지원 |

**Phase 1 적용 고도화 포인트**

| 번호 | 포인트 | 내용 |
|------|--------|------|
| 4 | 소스 역추적 (Traceability) | wiki 페이지 frontmatter에 `sources: [source_id]` 유지. 합성 시 갱신 |
| 5 | 영향 페이지 탐색 정확도 | index.md 1차 후보 선별 → 후보 페이지 본문 읽기 → 최종 확정 (2단계 탐색) |
| 6 | 페이지 정체성 일관성 | 신규 페이지 생성 전 유사 이름 페이지 존재 여부 확인. 페이지명 정규화 규칙 적용 |

**이후 Phase로 이월된 포인트**

| 번호 | 포인트 | 이월 이유 |
|------|--------|-----------|
| 1 | Context Window 한계 | Phase 1 소규모(소스 3개)에서는 문제없음 |
| 2 | 충돌 처리 정책 | Phase 1 소스 간 충돌 소지 적음 |
| 3 | 멱등성 | 검증용 소스 3개는 수동 관리 가능 |
| 7 | 부분 실패 복구 | Phase 1은 소규모라 재실행으로 대응 가능 |

### Index / Log

| Stage | 내용 |
|-------|------|
| Stage 1 | `wiki/index.md` 카탈로그 갱신 (신규/추가 시에만), `wiki/log.md` 항목 추가 |

---

## Phase 2 — Ingest 품질 및 점진적 확장

**목표**: 기존 wiki에 소스를 추가할 때 갱신 품질 검증. Normalizer 충실도 향상.

**검증 기준**
- 기존 wiki 페이지가 새 소스로 올바르게 갱신·보강됨
- 새 주제가 기존 구조에 자연스럽게 통합됨
- 모순이나 중복을 LLM이 감지하고 표시함

**투입 소스**

| 소스 | 수량 |
|------|------|
| 웹페이지 또는 Confluence 페이지 | 1개 (Phase 1 wiki에 추가할 동일 주제) |
| WIKI (Confluence) | 1개 (신규 또는 기존 주제) |
| 다른 페이지 | 1개 (독립 주제) |

### Normalizer

| Stage | 내용 |
|-------|------|
| Stage 2 | **원문 보존 병행** — `output/fetcher/`의 원문(HTML/XML)을 유지하며 Ingest가 손실 구간에서 원문 참조 가능하도록 연결. 재변환(re-normalize) 지원. |
| Stage 3 | **이미지 로컬 다운로드** — Confluence 첨부 이미지 및 외부 URL 이미지를 로컬에 다운로드, markdown 이미지 경로를 로컬 경로로 교체. |

### Ingest

| Stage | 내용 |
|-------|------|
| Stage 2 | 기존 wiki 페이지 갱신 — 새 소스로 보강, 모순·중복 감지 및 표시 |

---

## Phase 3 — Query / Lint

**목표**: 축적된 wiki를 대상으로 질의응답 및 건강 점검 기능 검증.

### Query

| Stage | 내용 |
|-------|------|
| Stage 1 | `wiki/index.md` 탐색 → 관련 페이지 읽기 → 답변 합성 → 결과 wiki 저장 |

### Lint

| Stage | 내용 |
|-------|------|
| Stage 1 | 모순 탐지, 고아 페이지, 누락 개념, 데이터 공백 점검 및 리포트 생성 |

---

## Phase 전환 조건

| 전환 | 조건 |
|------|------|
| Phase 1 → Phase 2 | Phase 1 검증 기준 통과 + 사용자 승인 |
| Phase 2 → Phase 3 | Phase 2 검증 기준 통과 + 사용자 승인 |

---

## 미결 사항 (TBD)

- Confluence 인증 방식 (API token, OAuth 등)
- 웹페이지 fetch 방법 (직접 HTTP vs. Obsidian Web Clipper)
- 유사/다른 페이지 판단 기준 (사용자가 직접 지정 vs. LLM이 자동 분류)
