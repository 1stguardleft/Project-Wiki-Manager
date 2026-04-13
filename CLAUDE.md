# CLAUDE.md

이 파일은 LLM에게 프로젝트의 현재 단계와 행동 지침을 정의한다.

---

## 현재 단계: 설계 (Design)

현재는 설계 단계다. 아키텍처, 요구사항, 계획을 정의하는 것이 목적이며 코드를 작성하지 않는다.

### 설계 단계에서 할 일
- `.claude/docs/` 문서를 읽고 설계 결정을 논의한다.
- 사용자의 피드백을 반영해 문서를 갱신한다.
- 구현 방법이 아닌 무엇을 만들지에 집중한다.

### 설계 단계에서 하지 말 것
- 코드 작성 금지
- 디렉토리 구조 외의 파일 생성 금지
- 사용자의 명시적 승인 없이 단계를 개발로 전환하지 않는다.

---

## 개발 단계 진입 시 가이드

사용자가 단계를 **개발(Development)**로 전환하면 아래 순서를 따른다.

### 원칙
- `.claude/docs/plan.md`의 구현 순서를 반드시 준수한다.
- 현재 Phase가 완료되기 전에 다음 Phase로 넘어가지 않는다.
- 각 구현 단계 완료 후 사용자에게 검증을 요청한다.
- Phase 범위 외 기능은 구현하지 않는다.

### 개발 상태 기록 (필수)

**Stage 구현 완료 직후, 커밋 전에 반드시 수행한다.**

- `.claude/docs/plan.md`의 해당 Stage 상태를 `⏳ Pending` → `✅ Done`으로 변경한다.
- 작업을 시작할 때는 `🚧 In Progress`로 먼저 표시한다.
- 파일만 생성하고 로직이 미구현(stub)인 경우 `🔧 Stub`으로 표시한다.
- plan.md 갱신도 같은 커밋에 포함한다.

이 규칙은 Claude Code, Codex 등 여러 AI가 동시에 작업할 때 **현재 개발 상태를 공유하는 단일 소스**로 활용된다.

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

## 설계 문서 동기화 (필수)

**각 Stage 구현 완료 후, main 머지 전에 반드시 수행한다.**

### 확인 절차

1. 구현 코드와 설계 문서(`.claude/docs/design/phaseN.md`)를 대조한다.
2. 요구사항 문서(`.claude/docs/requirements/phaseN.md`)와도 대조한다.
3. 아래 항목 중 하나라도 해당하면 문서를 갱신한다.

| 확인 항목 | 예시 |
|-----------|------|
| 설계에 없던 필드/파라미터가 코드에 추가됨 | `StageTimings`에 `*_ended_at` 필드 추가 |
| 설계의 인터페이스와 실제 함수 시그니처가 다름 | 반환 타입, 입력 경로 변경 |
| 설계에 기술한 라이브러리/도구가 교체됨 | 파서 변경, 모델명 변경 |
| 에러 처리 방식이 설계와 다르게 구현됨 | 예외 종류, 상태 기록 방식 |
| 신규 엔드포인트나 파일 경로가 추가됨 | API 경로, 출력 디렉토리 |
| 설계 의도와 다른 방향으로 구현됨 | 알고리즘, 흐름 변경 |

### 갱신 원칙

- 설계 문서는 **현재 코드의 실제 동작**을 반영해야 한다.
- 설계를 바꾼 이유가 있다면 문서에 간단히 기록한다.
- 미구현(stub/TODO) 항목은 문서에 그대로 유지한다.
- `architecture.md`, `rule.md`도 영향을 받는 경우 함께 갱신한다.

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
