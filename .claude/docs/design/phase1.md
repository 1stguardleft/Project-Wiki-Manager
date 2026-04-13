# Design — Phase 1

Phase 1 (Ingest Feasibility 검증) 상세 설계.

---

## 디렉토리 구조

```
project-wiki-manager/
├── frontend/
└── backend/
    ├── agents/
    │   ├── orchestrator/
    │   │   └── graph.py
    │   ├── fetcher/
    │   │   ├── web/fetcher.py
    │   │   ├── confluence/fetcher.py
    │   │   └── local/fetcher.py          # 로컬 MD 복사
    │   ├── normalizer/
    │   │   ├── web/normalizer.py
    │   │   ├── confluence/normalizer.py
    │   │   └── local/normalizer.py       # 복사만 수행
    │   ├── ingest/ingest.py
    │   └── index_log/index_log.py
    ├── models/
    │   └── state.py
    ├── api/
    │   └── main.py
    ├── requirements.txt
    └── .env.example
└── output/
    ├── fetcher/web/
    ├── fetcher/confluence/
    ├── fetcher/local/
    ├── normalizer/web/
    ├── normalizer/confluence/
    ├── normalizer/local/
    └── meta/                          # {source_id}.json, {source_id}_mapping.json
```

---

## State 스키마 (`backend/models/state.py`)

```python
from pydantic import BaseModel
from typing import Literal

SourceType = Literal["web", "confluence", "local_md"]
StageStatus = Literal["pending", "running", "done", "error"]

class StageStatuses(BaseModel):
    fetcher: StageStatus = "pending"
    normalizer: StageStatus = "pending"
    ingest: StageStatus = "pending"
    index_log: StageStatus = "pending"

class StageTimings(BaseModel):
    fetcher_started_at: float = 0.0
    fetcher_ended_at: float = 0.0
    normalizer_started_at: float = 0.0
    normalizer_ended_at: float = 0.0
    ingest_started_at: float = 0.0
    ingest_ended_at: float = 0.0
    index_log_started_at: float = 0.0
    index_log_ended_at: float = 0.0

class IngestState(BaseModel):
    source_id: str
    source_type: SourceType
    url: str                            # 웹/Confluence URL 또는 로컬 파일 경로
    confluence_page_id: str = ""        # Confluence 전용
    stages: StageStatuses = StageStatuses()
    timings: StageTimings = StageTimings()
    created_wiki_pages: list[str] = []  # 생성된 wiki 페이지 경로 목록
    updated_wiki_pages: list[str] = []  # 갱신된 wiki 페이지 경로 목록
    error: str = ""
```

---

## Orchestrator (`backend/agents/orchestrator/graph.py`)

### 역할
- 소스 타입 판별 (web / confluence / local_md)
- `source_id` 생성 (`YYYYMMDD-HHMMSS-{slug}`)
- `output/meta/{source_id}.json` 생성
- 소스 타입별 조건 분기
- 각 Stage 완료 시 메타데이터 상태 및 타이밍 갱신
- API 배치 실행 시 소스를 순차 처리하며, 진행 이벤트를 SSE로 발행

### LangGraph 그래프 구조

```python
graph = StateGraph(IngestState)

# 노드 등록
graph.add_node("fetcher_web", fetcher_web_node)
graph.add_node("fetcher_confluence", fetcher_confluence_node)
graph.add_node("fetcher_local", fetcher_local_node)
graph.add_node("normalizer_web", normalizer_web_node)
graph.add_node("normalizer_confluence", normalizer_confluence_node)
graph.add_node("normalizer_local", normalizer_local_node)
graph.add_node("ingest", ingest_node)
graph.add_node("index_log", index_log_node)

# 소스 타입별 분기
graph.set_entry_point("orchestrator")
graph.add_conditional_edges(
    "orchestrator",
    route_by_source_type,
    {
        "web": "fetcher_web",
        "confluence": "fetcher_confluence",
        "local_md": "fetcher_local",
    }
)

# Fetcher → Normalizer
graph.add_edge("fetcher_web", "normalizer_web")
graph.add_edge("fetcher_confluence", "normalizer_confluence")
graph.add_edge("fetcher_local", "normalizer_local")

# Normalizer → Ingest (모든 타입이 동일 Ingest로 합류)
graph.add_edge("normalizer_web", "ingest")
graph.add_edge("normalizer_confluence", "ingest")
graph.add_edge("normalizer_local", "ingest")

# 현재 구현은 ingest 성공 여부와 관계없이 index_log 노드까지 진행한다.
graph.add_edge("ingest", "index_log")
graph.add_edge("index_log", END)
```

### 파이프라인 분기 요약

```
web        → Fetcher/Web        → Normalizer/Web        ↘
confluence → Fetcher/Confluence → Normalizer/Confluence  → Ingest → Index/Log
local_md   → Fetcher/Local      → Normalizer/Local      ↗
             (파일 복사)           (복사만)
```

---

## Fetcher

### Fetcher/Web (`backend/agents/fetcher/web/fetcher.py`)

```
입력: IngestState (url)
처리: HTTP GET → HTML 저장
출력: output/fetcher/web/{source_id}.html
```

- `httpx` 사용, User-Agent 헤더 설정
- HTTP 오류(4xx, 5xx) 시 `stages.fetcher = "error"` 기록 후 중단

### Fetcher/Confluence (`backend/agents/fetcher/confluence/fetcher.py`)

```
입력: IngestState (confluence_page_id)
처리: Confluence REST API → Storage Format XML 저장
출력: output/fetcher/confluence/{source_id}.xml
```

- 엔드포인트: `GET {CONFLUENCE_BASE_URL}/rest/api/content/{page_id}?expand=body.storage`
- 헤더: `Authorization: Bearer {CONFLUENCE_ACCESS_TOKEN}`
- 응답에서 `body.storage.value` 추출하여 저장

### Fetcher/Local (`backend/agents/fetcher/local/fetcher.py`)

```
입력: IngestState (url = 로컬 파일 경로)
처리: 파일 읽기 → output/fetcher/local/ 에 복사
출력: output/fetcher/local/{source_id}.md
```

- 파일 존재 여부 확인, 없으면 `stages.fetcher = "error"`
- `.md` 확장자 검증

---

## Normalizer

### Normalizer/Web (`backend/agents/normalizer/web/normalizer.py`)

```
입력: output/fetcher/web/{source_id}.html
처리: HTML → markdown 변환
출력: output/normalizer/web/{source_id}.md
```

#### 변환 도구

**Primary: trafilatura**
```python
import trafilatura
markdown = trafilatura.extract(html, output_format="markdown")
```

**Fallback: Jina AI Reader** (trafilatura 결과가 비거나 실패 시)
```python
response = httpx.get(
    f"https://r.jina.ai/{url}",
    headers={"Authorization": f"Bearer {JINA_API_KEY}"}
)
markdown = response.text
```

#### 변환 흐름

```
html 입력
  ├─ trafilatura.extract() → 결과 있으면 저장
  └─ 결과 없으면 Jina AI Reader fallback → 저장
```

#### 변환 규칙

| 요소 | 처리 방식 |
|------|-----------|
| 단순 테이블 | markdown 테이블 |
| 복잡한 테이블 (colspan/rowspan) | 텍스트 대체 + `<!-- complex table omitted -->` |
| 외부 이미지 | `![alt](url)` |
| nav, footer, 광고 | trafilatura 자동 제거 |

### Normalizer/Confluence (`backend/agents/normalizer/confluence/normalizer.py`)

```
입력: output/fetcher/confluence/{source_id}.xml
처리: Confluence Storage Format → markdown 변환
출력: output/normalizer/confluence/{source_id}.md
```

- `beautifulsoup4`로 XML 파싱

| Confluence 요소 | 변환 결과 |
|----------------|-----------|
| `<p>`, `<h1>`~`<h6>` | 단락, `#`~`######` |
| `<ul>`, `<ol>` | markdown 목록 |
| `<code>`, `<pre>` | 코드 블록 |
| 단순 `<table>` | markdown 테이블 |
| 복잡한 `<table>` | 텍스트 대체 + `<!-- complex table omitted -->` |
| `<ac:image>` (첨부) | `<!-- attachment: {filename} -->` |
| `<ac:link>` | markdown 링크 |
| `<ac:structured-macro name="code">` | 펜스드 코드 블록 |
| 그 외 매크로 | `<!-- macro: {name} omitted -->` |

### Normalizer/Local (`backend/agents/normalizer/local/normalizer.py`)

```
입력: output/fetcher/local/{source_id}.md
처리: 변환 없이 복사
출력: output/normalizer/local/{source_id}.md
```

---

## Ingest (`backend/agents/ingest/ingest.py`)

```
입력: output/normalizer/{type}/{source_id}.md
처리: Wiki-centric 방식으로 wiki 페이지 생성/갱신
출력: wiki/sources/, wiki/entities/, wiki/concepts/
      output/meta/{source_id}_mapping.json
```

### 설계 원칙

소스를 청크 단위로 배분하는 것이 아니라 **wiki 페이지를 최적 상태로 유지**하는 것을 목표로 한다.
- Ingest는 source-grounded 정리기다. source에 없는 배경지식, 일반론, 정의를 새로 쓰지 않는다.
- 병합 단위는 파일 전체가 아니라 의미 있는 섹션이다.
- 같은 상위 주제를 설명하는 섹션은 가능한 한 하나의 페이지로 모으고, 독립적으로 정의되어야 하는 개념/엔티티만 별도 페이지로 분리한다.

### 처리 흐름

```
Step A   — 소스 이해             (LLM 1회, claude-opus-4-5)
Step A-1 — 소스 요약 페이지 생성  (LLM 1회) → wiki/sources/{source_id}.md
Step B   — 영향 페이지 파악       (LLM 1회) ← 2단계 탐색
Step C   — 페이지 정체성 검증                ← 명명 정규화
Step D   — 페이지별 변경 계획     (LLM, 영향 페이지 수만큼)
Step E   — 실행 (페이지별 재합성) + 매핑 정보 생성
Step E-1 — 검토 에이전트          (LLM 1회, claude-haiku-4-5) ← source-grounded 위반 탐지
Step E-2 — 자동 수정              (LLM, 위반 페이지 수만큼)  ← 위반 없으면 생략
Step F   — IngestState에 wiki 페이지 목록 기록
```

### Step A — 소스 이해 (LLM 1회, claude-opus-4-5)

```json
{
  "summary": "1~3문장 요약",
  "entities": ["OpenAI", "GPT-4"],
  "concepts": ["Few-shot learning", "RLHF"],
  "key_claims": ["GPT-4는 멀티모달을 지원한다"],
  "sections": [
    {
      "heading": "배포 자동화",
      "summary": "문서의 이 섹션이 다루는 범위",
      "independent_topic": false
    }
  ]
}
```

### Step A-1 — 소스 요약 페이지 생성 (LLM 1회)

```
출력: wiki/sources/{source_id}.md
```

- source 원문을 구조화·정리한 페이지. 외부 지식 추가 없이 source 그대로를 정리한다.
- 사용자가 "이 소스가 무엇을 담고 있는가"를 확인하는 용도.
- frontmatter `type: source`, `sources: ["{source_id}"]` 로 기록.

---

### Step B — 영향 페이지 파악 (LLM 1회)

```
1단계: index.md 읽기 → entities/concepts 비교 → 1차 후보 선별
2단계: 후보 페이지 본문 읽기 → 최종 영향 페이지 확정
```

```json
{
  "affected_pages": ["wiki/entities/openai.md"],
  "new_pages": ["wiki/entities/gpt-4.md"],
  "routing_notes": [
    {
      "source_section": "배포 자동화",
      "target_page": "wiki/entities/openai.md",
      "reason": "기존 상위 주제 문서에 포함하는 것이 적절함"
    },
    {
      "source_section": "RLHF",
      "target_page": "wiki/concepts/rlhf.md",
      "reason": "독립 개념으로 분리 필요"
    }
  ]
}
```

### Step C — 페이지 정체성 검증

**페이지명 정규화 규칙**

| 규칙 | 예시 |
|------|------|
| 소문자 + 하이픈 | `gpt-4.md`, `large-language-model.md` |
| 축약어는 대문자 유지 | `openai.md`, `rlhf.md` |
| 띄어쓰기 → 하이픈 | `few-shot-learning.md` |
| 특수문자 제거 | `gpt4.md` |

유사 페이지가 있으면 신규 생성 대신 해당 페이지에 병합한다. 다만 source 내부 일부가 독립 개념이면 그 섹션만 별도 페이지 또는 기존 페이지로 라우팅할 수 있다.

### Step D — 페이지별 변경 계획 수립

```json
{
  "page": "wiki/entities/openai.md",
  "actions": [
    { "type": "add", "section": "제품", "content": "source에 있는 내용을 정리해 추가" },
    { "type": "update", "section": "개요", "content": "source에 있는 범위 안에서 재배열" }
  ]
}
```

계획 수립 규칙:
- page 수는 가능한 최소로 유지한다.
- 동일 상위 주제를 설명하는 섹션은 한 페이지에 정리한다.
- source에 없는 설명을 추가하지 않는다.
- 기존 문장을 부드럽게 다듬는 것은 허용되지만 사실 확장은 금지한다.

### Step E — 실행 + 매핑 정보 생성

페이지 재합성 후 소스↔wiki 매핑을 `output/meta/{source_id}_mapping.json`에 저장.

**매핑 파일 포맷**

```json
{
  "source_id": "20260413-153000-openai-blog",
  "source_path": "output/normalizer/web/20260413-153000-openai-blog.md",
  "mappings": [
    {
      "source_paragraph_index": 0,
      "source_text_preview": "OpenAI는 2023년...",
      "wiki_page": "wiki/entities/openai.md",
      "wiki_section": "개요",
      "action": "반영됨"
    },
    {
      "source_paragraph_index": 1,
      "source_text_preview": "GPT-4의 성능은...",
      "wiki_page": "wiki/entities/gpt-4.md",
      "wiki_section": "성능",
      "action": "요약됨"
    },
    {
      "source_paragraph_index": 2,
      "source_text_preview": "부록: 라이선스 정보...",
      "wiki_page": null,
      "wiki_section": null,
      "action": "제외됨"
    }
  ]
}
```

**action 종류**

| action | 의미 |
|--------|------|
| `반영됨` | 원본 내용이 그대로 또는 거의 그대로 wiki에 포함 |
| `요약됨` | 원본 내용이 압축되어 wiki에 반영 |
| `병합됨` | 동일 상위 주제 페이지 안에서 다른 source/기존 wiki와 함께 정리됨 |
| `제외됨` | wiki에 반영되지 않음 |

### Step E-1 — 검토 에이전트 (LLM, claude-haiku-4-5)

```
입력: source 원문 + 생성/갱신된 wiki 페이지 목록
처리: 페이지별 문장을 source 원문과 비교 → source에 없는 문장 탐지
출력: output/meta/{source_id}_review.json
```

**검토 결과 포맷**

```json
{
  "source_id": "20260413-153000-openai-blog",
  "pages_reviewed": ["wiki/sources/...", "wiki/entities/openai.md"],
  "violations": [
    {
      "page": "wiki/entities/openai.md",
      "sentence": "Google이 2014년 오픈소스로 공개했다.",
      "reason": "source에 연도 언급 없음"
    }
  ],
  "passed": false
}
```

- 위반이 없으면 `passed: true`, `violations: []`
- 검토 실패(API 오류 등)는 ingest 전체를 중단시키지 않는다.

### Step E-2 — 자동 수정 (LLM, claude-haiku-4-5)

```
입력: output/meta/{source_id}_review.json + 위반 wiki 페이지
처리: 위반 문장만 삭제, 나머지 내용 유지 → 페이지 덮어쓰기
조건: review.passed == false 일 때만 실행
```

- 위반 문장을 다른 말로 바꾸거나 보완하지 않는다. 삭제만 한다.
- 문장 제거 후 문단이 어색해지면 최소한만 자연스럽게 이어준다.
- 수정 실패 시 원본 유지, ingest는 계속 진행한다.
- `_review.json`은 감사 목적으로 항상 보존한다.

### Step F — IngestState 갱신

```python
state.created_wiki_pages = ["wiki/sources/source-id.md", "wiki/entities/gpt-4.md"]
state.updated_wiki_pages = ["wiki/entities/openai.md"]
```

- `created_wiki_pages` 첫 번째 항목은 항상 `wiki/sources/{source_id}.md`.

### wiki 페이지 포맷

```markdown
---
title: {제목}
type: {source|entity|concept}
sources: ["{source_id_1}", "{source_id_2}"]
updated: {YYYY-MM-DD}
---

# {제목}

{본문}

## 관련 페이지

- [[{관련 페이지}]]
```

### Step F — index.md 갱신 조건

| 상황 | index.md 갱신 |
|------|--------------|
| 신규 페이지 생성 | 갱신 (항목 추가) |
| 기존 페이지 재합성 | 갱신 불필요 |

---

## Index/Log (`backend/agents/index_log/index_log.py`)

```
입력: IngestState (created_wiki_pages, updated_wiki_pages)
출력: wiki/index.md, wiki/log.md
```

### index.md

```markdown
- [제목](경로) — 한 줄 요약
```

### log.md

```markdown
## [YYYY-MM-DD] ingest | {source_id}

- 소스 타입: web
- URL: https://...
- 생성 페이지: wiki/sources/{source_id}.md, wiki/entities/gpt-4.md
- 갱신 페이지: wiki/entities/openai.md
```

---

## FastAPI 엔드포인트 (`backend/api/main.py`)

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/ingest/batch` | 멀티 소스 ingest 배치 실행 |
| `GET` | `/ingest/batch/{batch_id}/stream` | 배치 전체 SSE 스트림 |
| `GET` | `/status/{source_id}` | 단일 소스 처리 상태 조회 |
| `GET` | `/files` | 파일 트리 조회 |
| `GET` | `/files/content` | 파일 내용 조회 |
| `GET` | `/compare` | 소스 → wiki 반영 비교 |

### `POST /ingest/batch`

```json
{
  "sources": [
    { "type": "web", "url": "https://..." },
    { "type": "confluence", "url": "https://confluence.../pages/123456/", "page_id": "123456" },
    { "type": "local_md", "path": "/path/to/file.md" }
  ]
}
```

응답:
```json
{
  "batch_id": "batch-20260413-153000",
  "source_ids": ["id1", "id2", "id3"],
  "total": 3
}
```

구현 메모:
- Phase 1 현재 구현은 서버 프로세스 메모리에서 배치 상태를 관리한다.
- 배치 이벤트는 메모리에 누적되어, SSE 클라이언트가 늦게 연결되어도 기존 이벤트를 재생할 수 있다.
- 서버 재시작 시 배치 런타임 상태와 SSE 히스토리는 유지되지 않는다.

### `GET /ingest/batch/{batch_id}/stream` — SSE (단일 스트림)

소스를 순차 처리하며 하나의 SSE 스트림으로 모든 이벤트를 전송한다.

```
event: batch_start
data: { "batch_id": "...", "total": 3 }

event: source_start
data: { "source_id": "id1", "index": 1, "total": 3 }

event: stage_update
data: { "source_id": "id1", "stage": "fetcher", "status": "running", "elapsed_ms": 0 }

event: stage_update
data: { "source_id": "id1", "stage": "fetcher", "status": "done", "elapsed_ms": 1200 }

event: source_done
data: { "source_id": "id1", "index": 1, "total": 3 }

event: source_start
data: { "source_id": "id2", "index": 2, "total": 3 }

...

event: batch_done
data: { "batch_id": "...", "total_elapsed_ms": 35000 }
```

실제 `stage_update` payload:
- `source_id`
- `stage`
- `status`
- `elapsed_ms`
- `error`

### `GET /compare`

```
Query: source_ids=id1,id2&wiki_path=wiki/entities/openai.md
```

응답:
```json
{
  "wiki_page": {
    "path": "wiki/entities/openai.md",
    "content": "...",
    "sources": ["id1", "id2"]
  },
  "sources": [
    {
      "source_id": "id1",
      "content": "...",
      "mappings": [
        {
          "source_paragraph_index": 0,
          "source_text_preview": "OpenAI는 2023년...",
          "wiki_section": "개요",
          "action": "반영됨"
        }
      ]
    }
  ]
}
```

구현 메모:
- 현재 Phase 1의 `/compare`는 서버에서 diff를 계산하지 않는다.
- 서버는 `wiki_page`, normalized source 본문, `mapping.json` 기반 매핑만 반환한다.
- git diff 스타일 비교 렌더링은 FE에서 수행한다.

---

## Confluence page_id 추출

Confluence URL 패턴: `https://{host}/...pages/{page_id}/`

```python
import re

def extract_confluence_page_id(url: str) -> str:
    match = re.search(r"/pages/(\d+)", url)
    if match:
        return match.group(1)
    raise ValueError(f"page_id를 추출할 수 없습니다: {url}")
```

---

## FE 설계

### 디렉토리 구조

```
frontend/src/
├── components/
│   ├── SourceInput/
│   │   ├── SourceInputList.tsx     # 소스 목록 + 추가/삭제
│   │   └── SourceInputItem.tsx     # 개별 소스 입력 (URL / Confluence / 로컬 MD)
│   ├── WorkflowModal/
│   │   ├── WorkflowModal.tsx       # 팝업 컨테이너
│   │   ├── BatchProgress.tsx       # 소스 진행률 (N/M)
│   │   ├── PipelineFlow.tsx        # 에이전트 흐름도
│   │   ├── AgentNode.tsx           # 개별 에이전트 노드
│   │   └── ArtifactPreview.tsx     # 노드 클릭 시 산출물 미리보기
│   └── ResultView/
│       ├── ResultView.tsx          # 결과 비교 뷰 컨테이너
│       ├── SourcePanel.tsx         # 좌측: 원본 소스
│       ├── DiffPanel.tsx           # 우측: git diff 스타일 wiki 변경
│       └── MappingLayer.tsx        # 원본↔결과 연결
└── pages/
    └── IngestPage.tsx
```

---

### 전체 UX 흐름

```
IngestPage
  ├─ [1] SourceInput         소스 추가 (URL / Confluence / 로컬 MD)
  ├─ [처리 시작]  →  POST /ingest/batch
  ├─ [2] WorkflowModal       SSE 연결 → 실시간 업데이트
  └─ [3] ResultView          git diff 스타일 비교
```

---

### 1. 소스 입력 (`SourceInput`)

```
┌──────────────────────────────────────────────────┐
│  소스 입력                                        │
│  ┌───────────────────────────────────┬─────────┐ │
│  │ 🌐 https://example.com/article    │ [삭제]  │ │
│  └───────────────────────────────────┴─────────┘ │
│  ┌───────────────────────────────────┬─────────┐ │
│  │ 🏢 confluence.../pages/123456/    │ [삭제]  │ │
│  │    page_id: 123456 ✅             │         │ │
│  └───────────────────────────────────┴─────────┘ │
│  ┌───────────────────────────────────┬─────────┐ │
│  │ 📄 /Users/.../note.md             │ [삭제]  │ │
│  └───────────────────────────────────┴─────────┘ │
│  [+ 소스 추가 ▾]                                  │
│    ├─ 웹 페이지 URL                               │
│    ├─ Confluence 페이지                           │
│    └─ 로컬 MD 파일                                │
│                          [처리 시작]              │
└──────────────────────────────────────────────────┘
```

- Confluence URL 입력 시 page_id 자동 추출 후 표시 및 검증
- 소스 타입별 아이콘 구분 (🌐 웹 / 🏢 Confluence / 📄 로컬)

---

### 2. 워크플로우 팝업 (`WorkflowModal`)

```
┌──────────────────────────────────────────────────────┐
│  처리 현황  (2 / 3 완료)                        [✕]  │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━    │
│  ✅ source-1: https://example.com         (3.2s)      │
│  🔄 source-2: confluence.../pages/123456/            │
│  ⏳ source-3: /Users/.../note.md                      │
│  ──────────────────────────────────────────────────  │
│  현재: source-2                                       │
│  [Orchestrator]→[Fetcher]→[Normalizer]→[Ingest]→[Log]│
│      ✅ 0.1s     ✅ 1.4s    🔄 2.1s...  ⏳      ⏳    │
│  ──────────────────────────────────────────────────  │
│  🔄 Normalizer/Confluence 변환 중...                  │
│                              [결과 보기] ← 완료 시    │
└──────────────────────────────────────────────────────┘
```

- 상단: 배치 전체 진행률 + 소스별 완료 상태
- 중단: 현재 처리 중인 소스의 파이프라인 흐름도
- 완료된 노드 클릭 → 해당 단계 산출물 미리보기

| 상태 | 표시 |
|------|------|
| pending | 회색 ⏳ |
| running | 파란색 🔄 + 경과 시간 |
| done | 초록색 ✅ + 소요 시간 |
| error | 빨간색 ❌ + 오류 메시지 |

---

### 3. 결과 비교 뷰 — git diff 스타일 (`ResultView`)

```
┌──────────────────────────────────────────────────────┐
│  [소스1] [소스2] [소스3]        wiki: [openai.md ▾]  │
├──────────────────┬───────────────────────────────────┤
│   원본 소스       │   wiki 변경 (diff)                │
├──────────────────┼───────────────────────────────────┤
│  ## Introduction │   # OpenAI                        │
│  OpenAI는...     │                                   │
│  [반영됨] ───────┼──→  + ## 개요                     │
│                  │     + OpenAI는 AI 연구 기업으로... │
│                  │                                   │
│  ### 모델 성능   │     ## 제품                       │
│  GPT-4는...      │   - 기존 내용...                  │
│  [요약됨] ───────┼──→  + GPT-4: 멀티모달 지원 (요약) │
│                  │                                   │
│  ### 부록        │                                   │
│  라이선스...     │                                   │
│  [제외됨]        │                                   │
└──────────────────┴───────────────────────────────────┘
  범례: + 추가(초록)  - 제거(빨강)  컨텍스트(회색)
        반영됨  요약됨  병합됨  제외됨
```

- 우측은 기존 wiki 대비 변경된 diff를 표시 (git diff 스타일)
  - `+` 초록: 추가된 줄
  - `-` 빨강: 제거된 줄
  - 회색: 변경 없는 컨텍스트 줄
- 소스별 탭으로 전환 (`mapping.json` 기반)
- 우측 wiki 페이지 드롭다운: 생성/갱신된 여러 페이지 중 선택
- 원본 단락 클릭 → 대응하는 diff 위치로 스크롤 + 하이라이트
- `output/meta/{source_id}_mapping.json`으로 매핑 구성
