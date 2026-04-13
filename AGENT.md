# AGENT.md

이 파일은 에이전트에게 프로젝트의 현재 단계와 행동 지침을 정의한다.

---

## 현재 단계: 개발 (Development)

현재는 개발 단계다. 승인된 요구사항, 설계, 아키텍처, 계획을 기준으로 구현과 검증을 진행한다.

### 개발 단계에서 할 일
- `.claude/docs/` 문서를 구현 기준으로 삼아 개발한다.
- `.claude/docs/plan.md`의 순서와 개발 상태를 항상 최신으로 유지한다.
- 소스 코드는 역할별로 모아 관리한다: 백엔드 코드는 `backend/`, 프론트엔드 코드는 `frontend/`.
- 구현 후 검증 결과와 남은 작업을 문서에 반영한다.

### 개발 단계에서 하지 말 것
- `plan.md` 순서를 건너뛰고 다음 Stage 또는 다음 Phase로 넘어가지 않는다.
- Phase 범위 외 기능을 임의로 추가하지 않는다.
- 사용자 확인 없이 Phase 완료로 간주하지 않는다.

---

## 개발 단계 가이드

### 원칙
- `.claude/docs/plan.md`의 구현 순서를 반드시 준수한다.
- 구현을 시작하거나 완료하거나 상태가 바뀌면 `.claude/docs/plan.md`의 개발 상태를 즉시 현행화한다.
- 현재 Phase가 완료되기 전에 다음 Phase로 넘어가지 않는다.
- 각 구현 단계 완료 후 사용자에게 검증을 요청한다.
- Phase 범위 외 기능은 구현하지 않는다.
- Ingest는 원문 정리와 구조화가 목적이며, source에 없는 배경지식이나 설명을 임의로 덧붙이지 않는다.
- 페이지 분할/병합은 문서 전체를 무조건 합치지 말고, 섹션 의미와 기존 wiki 구조를 기준으로 최소한으로 수행한다.

### Phase 1 구현 순서 (`.claude/docs/plan.md` 참고)

다음 순서대로 하나씩 구현하고, 각 단계 완료 시 사용자 확인 후 다음으로 진행한다.

1. **Orchestrator 골격** — 명령 수신 → 에이전트 호출 흐름 정의
2. **Fetcher/Web** — 웹페이지 URL fetch, 원문 HTML을 `output/fetcher/web/`에 저장
3. **Fetcher/Confluence** — Confluence REST API로 페이지 획득, 원문을 `output/fetcher/confluence/`에 저장
4. **Normalizer/Web** — HTML → markdown (best-effort), 결과를 `output/normalizer/web/`에 저장
5. **Normalizer/Confluence** — Confluence Storage Format → markdown (best-effort), 결과를 `output/normalizer/confluence/`에 저장
6. **Ingest Agent** — markdown → wiki 페이지 생성/갱신, 상호 참조 처리
7. **Index/Log Agent** — `wiki/index.md`, `wiki/log.md` 갱신
8. **end-to-end 검증** — 유사 페이지 2개 + 다른 페이지 1개로 전체 파이프라인 실행

### Phase 전환 조건

| Phase | 전환 조건 |
|-------|-----------|
| Phase 1 → Phase 2 | end-to-end 검증 통과 + 사용자 승인 |
| Phase 2 → Phase 3 | Ingest 품질 검증 통과 + 사용자 승인 |

---

## 문서 구조

| 파일 | 설명 |
|------|------|
| `.claude/docs/architecture.md` | Multi-Agent + Orchestrator 구조, 기술 스택, 인터페이스 |
| `.claude/docs/plan.md` | 단계별 계획 및 구현 순서 |
| `.claude/docs/rule.md` | 개발 규칙 |
| `.claude/docs/requirements/common.md` | 전체 공통 요구사항 |
| `.claude/docs/requirements/phase1.md` | Phase 1 요구사항 |
| `.claude/docs/requirements/phase2.md` | Phase 2 요구사항 |
| `.claude/docs/requirements/phase3.md` | Phase 3 요구사항 |
| `.claude/docs/design/phase1.md` | Phase 1 상세 설계 |
| `.claude/docs/design/phase2.md` | Phase 2 상세 설계 |
| `.claude/docs/design/phase3.md` | Phase 3 상세 설계 |
