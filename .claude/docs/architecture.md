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
  ├──▶ Fetcher/Local      — 로컬 MD 파일 복사
  ├──▶ Normalizer/Web        — HTML → markdown
  ├──▶ Normalizer/Confluence — Confluence Storage Format → markdown
  ├──▶ Normalizer/Local      — 복사만 수행
  ├──▶ Ingest Agent       — markdown → wiki 페이지 생성/갱신
  │     ├── Review Agent  — source-grounded 위반 탐지 (Haiku)
  │     └── Fix Agent     — 위반 문장 자동 제거 (Haiku)
  ├──▶ Index/Log Agent    — index.md, log.md 갱신
  ├──▶ Query Agent        — (Phase 3) wiki 검색 및 답변 합성
  └──▶ Lint Agent         — (Phase 3) 모순·고아 페이지·누락 개념 점검
```

## 파이프라인

```
Fetcher/Web        →  Normalizer/Web        ↘
Fetcher/Confluence →  Normalizer/Confluence  → Ingest → [Review → Fix] → Index/Log
Fetcher/Local      →  Normalizer/Local      ↗
```

중간 산출물:
- Fetcher 출력: 원문 (HTML, XML, MD)
- Normalizer 출력: markdown (Ingest Agent의 입력 포맷)
- Ingest 출력: wiki 페이지 (sources/entities/concepts), mapping.json
- Review 출력: review.json (위반 없으면 Fix 생략)

## 역할 정의

| Agent | 책임 | 비고 |
|-------|------|------|
| **Orchestrator** | 사용자 명령 수신, 작업 분해, 에이전트 호출 순서 결정, 결과 취합 | 상태 관리 주체 |
| **Fetcher/Web** | 웹페이지 URL fetch, 원문 HTML 저장 | 읽기 전용 |
| **Fetcher/Confluence** | Confluence REST API로 페이지 획득, 원문 Storage Format XML 저장 | 읽기 전용 |
| **Fetcher/Local** | 로컬 MD 파일을 output/fetcher/local/ 에 복사 | 읽기 전용 |
| **Normalizer/Web** | HTML → markdown (trafilatura primary, Jina fallback) | 변환 전용 |
| **Normalizer/Confluence** | Confluence Storage Format(XML) → markdown (bs4) | 변환 전용 |
| **Normalizer/Local** | 변환 없이 복사 | 변환 전용 |
| **Ingest** | source-grounded 방식으로 wiki 페이지 생성/갱신, 소스 요약 페이지 생성 | wiki 쓰기 주체 |
| **Review** (Ingest 내부) | 생성된 wiki 페이지의 source-grounded 위반 탐지 | Haiku 모델 사용 |
| **Fix** (Ingest 내부) | 위반 문장 자동 삭제, 페이지 덮어쓰기 | 위반 있을 때만 실행 |
| **Index/Log** | `index.md` 카탈로그 갱신, `log.md` 항목 추가 | append/update 전용 |
| **Query** | index 탐색 → 관련 페이지 읽기 → 답변 합성 → 결과 저장 | Phase 3 |
| **Lint** | wiki 전체 순회, 이슈 목록 생성 및 Orchestrator에 보고 | Phase 3 |

## 기술 스택

| 레이어 | 기술 | 역할 |
|--------|------|------|
| **FE** | React + TypeScript (Vite) | 사용자 인터페이스 |
| **BE** | Python + FastAPI | REST API 서버, FE와 통신, SSE 스트리밍 |
| **오케스트레이션** | LangGraph | 멀티 에이전트 파이프라인, 상태 관리, 조건 분기 |
| **LLM (주)** | Anthropic SDK — claude-opus-4-5 | Ingest 핵심 로직 (소스 이해, 페이지 계획, 재합성) |
| **LLM (보조)** | Anthropic SDK — claude-haiku-4-5 | Review/Fix 에이전트 (경량 비용 절감) |
| **Web 정규화** | trafilatura + httpx (Jina fallback) | HTML → markdown |
| **Confluence 정규화** | beautifulsoup4 + lxml | XML → markdown |
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
project-wiki-manager/
├── frontend/                         ← React + TypeScript (Vite)
├── backend/
│   ├── agents/
│   │   ├── orchestrator/graph.py
│   │   ├── fetcher/{web,confluence,local}/fetcher.py
│   │   ├── normalizer/{web,confluence,local}/normalizer.py
│   │   ├── ingest/ingest.py          ← Review/Fix 포함
│   │   └── index_log/index_log.py
│   ├── models/state.py
│   ├── api/main.py
│   └── requirements.txt
├── output/
│   ├── fetcher/
│   │   ├── web/{source-id}.html      ← 원문 HTML
│   │   ├── confluence/{source-id}.xml← 원문 Confluence Storage Format
│   │   └── local/{source-id}.md     ← 로컬 MD 복사본
│   ├── normalizer/
│   │   ├── web/{source-id}.md        ← 변환된 markdown
│   │   ├── confluence/{source-id}.md ← 변환된 markdown
│   │   └── local/{source-id}.md     ← 복사된 markdown
│   └── meta/
│       ├── {source-id}.json          ← 소스 메타데이터
│       ├── {source-id}_mapping.json  ← 소스↔wiki 매핑
│       └── {source-id}_review.json  ← source-grounded 검토 결과
├── wiki/
│   ├── index.md
│   ├── log.md
│   ├── sources/                      ← 소스 요약 페이지 (소스 1개 = 1파일)
│   ├── entities/
│   └── concepts/
└── raw/                              ← 원본 소스 파일 (불변)
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
Orchestrator          output/meta/{id}.json 생성
  │
Fetcher               output/fetcher/{type}/{id}.{ext} 저장
  │
Normalizer            output/normalizer/{type}/{id}.md 저장
  │
Ingest
  ├─ Step A-1       wiki/sources/{id}.md 생성
  ├─ Step E         wiki/entities/, wiki/concepts/ 페이지 생성/갱신
  │                 output/meta/{id}_mapping.json 저장
  ├─ Step E-1       output/meta/{id}_review.json 저장
  └─ Step E-2       위반 wiki 페이지 자동 수정 (위반 있을 때만)
  │
Index/Log             wiki/index.md, wiki/log.md 갱신
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
