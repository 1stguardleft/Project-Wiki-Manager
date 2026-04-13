# Architecture

## Multi-Agent + Orchestrator 구조

모든 단계(Phase 1~3)에 공통으로 적용되는 구조.

```
사용자
  │
  ▼
Orchestrator Agent
  │  작업 분해 및 위임, 결과 취합, wiki 일관성 보장
  ├──▶ Fetcher/Web        — 웹페이지 URL fetch, 원문 HTML 반환
  ├──▶ Fetcher/Confluence — Confluence REST API, 원문 Storage Format 반환
  ├──▶ Normalizer/Web        — HTML → markdown
  ├──▶ Normalizer/Confluence — Confluence Storage Format → markdown
  ├──▶ Ingest Agent       — markdown → wiki 페이지 생성/갱신
  ├──▶ Index/Log Agent    — index.md, log.md 갱신
  ├──▶ Query Agent        — (Phase 3) wiki 검색 및 답변 합성
  └──▶ Lint Agent         — (Phase 3) 모순·고아 페이지·누락 개념 점검
```

## 파이프라인

```
Fetcher/Web        →  Normalizer/Web        ↘
                                              Ingest → Index/Log
Fetcher/Confluence →  Normalizer/Confluence ↗
```

중간 산출물:
- Fetcher 출력: 원문 (HTML, Confluence Storage Format)
- Normalizer 출력: markdown (Ingest Agent의 입력 포맷)

## 역할 정의

| Agent | 책임 | 비고 |
|-------|------|------|
| **Orchestrator** | 사용자 명령 수신, 작업 분해, 에이전트 호출 순서 결정, 결과 취합 | 상태 관리 주체 |
| **Fetcher/Web** | 웹페이지 URL fetch, 원문 HTML 반환 | 읽기 전용 |
| **Fetcher/Confluence** | Confluence REST API로 페이지 획득, 원문 Storage Format 반환 | 읽기 전용 |
| **Normalizer/Web** | HTML → markdown (불필요한 태그 제거, 본문 추출, 이미지 참조 처리) | 변환 전용 |
| **Normalizer/Confluence** | Confluence Storage Format(XML) → markdown (매크로·테이블·첨부파일 처리) | 변환 전용 |
| **Ingest** | markdown → 요약 → wiki 페이지 생성/갱신, 상호 참조 처리 | wiki 쓰기 주체 |
| **Index/Log** | `index.md` 카탈로그 갱신, `log.md` 항목 추가 | append/update 전용 |
| **Query** | index 탐색 → 관련 페이지 읽기 → 답변 합성 → 결과 저장 | Phase 3 |
| **Lint** | wiki 전체 순회, 이슈 목록 생성 및 Orchestrator에 보고 | Phase 3 |

## 기술 스택

| 레이어 | 기술 | 역할 |
|--------|------|------|
| **FE** | React | 사용자 인터페이스 |
| **BE** | Python + FastAPI | REST API 서버, FE와 통신 |
| **오케스트레이션** | LangGraph | 멀티 에이전트 파이프라인, 상태 관리, 조건 분기 |
| **LLM** | Anthropic SDK (Claude) | 각 에이전트의 LLM 호출 |
| **타입 정의** | Pydantic | 에이전트 간 입출력 스키마 정의 |

**LangGraph 선택 이유**
- Orchestrator → Fetcher → Normalizer → Ingest → Index/Log 파이프라인이 그래프 구조와 자연스럽게 매핑됨
- 소스 타입(Web/Confluence)에 따른 조건 분기를 `conditional_edges`로 표현 가능
- State 객체로 중간 산출물(`output/fetcher/`, `output/normalizer/`) 관리 용이
- Phase별 노드 추가로 확장 구조가 깔끔함
- Anthropic SDK 및 FastAPI와 공식 통합 지원

## 에이전트 간 인터페이스 — 파일 기반

에이전트 간 데이터 전달은 **파일 기반**으로 한다. 각 Stage의 산출물이 디렉토리에 저장되므로 중간 단계 디버깅이 가능하다.

### source-id 규칙

각 소스는 고유한 `source-id`를 가지며, 모든 Stage에서 동일한 ID를 공유한다.
이를 통해 특정 소스의 Fetch → Normalize → Ingest 결과를 추적할 수 있다.

```
형식: {YYYYMMDD-HHMMSS}-{slug}
예시: 20260413-153000-openai-gpt4-blog
```

### 디렉토리 구조 및 파일 포맷

```
output/
├── fetcher/
│   ├── web/
│   │   └── {source-id}.html          ← 원문 HTML
│   └── confluence/
│       └── {source-id}.xml           ← 원문 Confluence Storage Format
├── normalizer/
│   ├── web/
│   │   └── {source-id}.md            ← 변환된 markdown
│   └── confluence/
│       └── {source-id}.md            ← 변환된 markdown
└── meta/
    └── {source-id}.json              ← 소스 메타데이터 (아래 참고)
```

### 메타데이터 파일 (`output/meta/{source-id}.json`)

각 소스의 처리 상태와 정보를 기록한다. Orchestrator가 생성하고 각 Stage 완료 시 갱신한다.

```json
{
  "source_id": "20260413-153000-openai-gpt4-blog",
  "type": "web",
  "url": "https://...",
  "created_at": "2026-04-13T15:30:00",
  "stages": {
    "fetcher": "done",
    "normalizer": "done",
    "ingest": "pending",
    "index_log": "pending"
  }
}
```

### 단계별 파일 흐름

```
Orchestrator       output/meta/{id}.json 생성
  │
Fetcher/Web        output/fetcher/web/{id}.html 저장
Fetcher/Confluence output/fetcher/confluence/{id}.xml 저장
  │
Normalizer/Web        output/normalizer/web/{id}.md 저장
Normalizer/Confluence output/normalizer/confluence/{id}.md 저장
  │
Ingest             wiki/sources/, wiki/entities/, wiki/concepts/ 에 페이지 생성/갱신
  │
Index/Log          wiki/index.md, wiki/log.md 갱신
```

## Confluence 인증

- 방식: **Access Token** 기반
- 헤더: `Authorization: Bearer {access_token}`
- 토큰은 환경변수(`CONFLUENCE_ACCESS_TOKEN`)로 관리하며 코드에 포함하지 않는다.

## 설계 원칙

- Orchestrator만 에이전트 간 흐름을 제어한다. 에이전트끼리 직접 통신하지 않는다.
- Fetcher는 원문을 그대로 반환하며 변환하지 않는다.
- Normalizer는 포맷 변환만 담당하며 wiki를 수정하지 않는다.
- Ingest Agent는 항상 markdown 형식의 입력을 받는다.
- 새 소스 타입 추가 시 Fetcher + Normalizer 쌍만 추가하면 Ingest는 재사용된다.
- wiki 쓰기는 Ingest Agent와 Index/Log Agent만 수행한다.
- 각 에이전트는 독립적으로 교체·확장 가능하도록 인터페이스를 최소화한다.
