# Rules

개발 단계에서 모든 에이전트 구현에 공통으로 적용되는 규칙.

---

## 일반 원칙

- `plan.md`의 Phase/Stage 순서를 반드시 준수한다. 건너뛰지 않는다.
- 현재 Phase 범위 외 기능은 구현하지 않는다.
- 각 Stage 완료 후 사용자 확인을 받고 다음 Stage로 진행한다.

---

## 코드 규칙

### 언어 및 포맷
- Python 3.11 이상 사용
- 타입 힌트 필수 (`def fetch(url: str) -> str:`)
- Pydantic 모델로 에이전트 간 입출력 스키마 정의

### 네이밍
- 파일명: `snake_case.py`
- 클래스명: `PascalCase`
- 변수/함수명: `snake_case`
- 상수: `UPPER_SNAKE_CASE`

### 에러 처리
- 외부 호출(HTTP fetch, Confluence API)은 반드시 예외 처리
- 에러 발생 시 `output/meta/{source-id}.json`의 stage 상태를 `"error"`로 기록
- 에러 메시지는 사용자가 이해할 수 있는 수준으로 작성

---

## 에이전트 규칙

- 에이전트는 자신의 담당 Stage 산출물만 쓴다. 다른 에이전트의 출력을 직접 수정하지 않는다.
- Fetcher는 `output/fetcher/{type}/{source-id}.{ext}`에만 쓴다.
- Normalizer는 `output/normalizer/{type}/{source-id}.md`에만 쓴다.
- Ingest는 `wiki/`에만 쓴다.
- Index/Log는 `wiki/index.md`, `wiki/log.md`에만 쓴다.
- `raw/` 디렉토리는 어떤 에이전트도 수정하지 않는다.

---

## 환경변수

민감 정보는 코드에 포함하지 않고 환경변수로 관리한다.

| 변수 | 설명 |
|------|------|
| `CONFLUENCE_ACCESS_TOKEN` | Confluence API 인증 토큰 |
| `CONFLUENCE_BASE_URL` | Confluence 인스턴스 URL |
| `ANTHROPIC_API_KEY` | Claude API 키 |
| `JINA_API_KEY` | Jina AI Reader API 키 (Normalizer/Web fallback용) |

---

## source-id 규칙

- 형식: `{YYYYMMDD-HHMMSS}-{slug}`
- slug: URL 또는 페이지 제목에서 영문 소문자·숫자·하이픈만 사용
- 예시: `20260413-153000-openai-gpt4-blog`
- 동일 소스를 재처리할 경우 새 source-id를 생성한다 (덮어쓰지 않는다)

---

## Git

- 커밋 단위: Stage 완료 단위
- 커밋 메시지 형식: `[Phase1][Fetcher/Web] Stage 1 구현`
- `output/` 디렉토리는 `.gitignore`에 추가한다 (중간 산출물은 버전 관리 불필요)
- `wiki/` 디렉토리는 버전 관리에 포함한다
