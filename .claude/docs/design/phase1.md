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

## Wiki 카테고리

```
wiki/
├── sources/        ← 소스 요약 (소스 1개 = 파일 1개, 자동 생성)
├── requirements/   ← 요구사항, 유저 스토리, 검증 기준
├── design/         ← 아키텍처, 시스템 설계, API 스펙
├── development/    ← 구현 가이드, 기술 결정, 트러블슈팅
├── records/        ← 회의록, 스프린트 회고, 결정 이유
├── domain/         ← 도메인 지식, 외부 기술 리서치, 업계 개념
├── etc/            ← 카테고리 판단 불명확한 내용
├── index.md
└── log.md
```

LLM 카테고리 판단 기준:

| 카테고리 | 핵심 질문 |
|----------|-----------|
| `requirements/` | 무엇을 만들어야 하는가? |
| `design/` | 어떻게 생겼는가? |
| `development/` | 어떻게 구현하는가? |
| `records/` | 언제, 무엇을, 왜 결정했는가? |
| `domain/` | 이 분야에서 알아야 할 지식은? |
| `etc/` | 위 어디에도 명확히 속하지 않는가? |

---

## Ingest (`backend/agents/ingest/ingest.py`)

```
입력: output/normalizer/{type}/{source_id}.md
처리: Wiki-centric 방식으로 wiki 페이지 생성/갱신
출력: wiki/sources/{source_id}.md (소스 요약)
      wiki/{category}/{page_name}.md (카테고리별 페이지)
      output/meta/{source_id}_mapping.json
```

### 설계 원칙

소스를 청크 단위로 배분하는 것이 아니라 **wiki 페이지를 최적 상태로 유지**하는 것을 목표로 한다.
- Ingest는 source-grounded 정리기다. source에 없는 배경지식, 일반론, 정의를 새로 쓰지 않는다.
- 병합 단위는 파일 전체가 아니라 의미 있는 섹션이다.
- 각 페이지는 위 6개 카테고리 중 가장 적합한 곳에 위치한다. 판단 불명확 시 `etc/`에 생성한다.

---

### LLM 호출 목록

파이프라인 전체에서 LLM을 호출하는 곳은 **Ingest Agent 내부로만 한정**된다.  
Fetcher / Normalizer / Orchestrator / Index·Log 는 LLM을 사용하지 않는다.

> **예외**: Normalizer/Web의 Jina AI Reader fallback은 외부 API이며, 내부적으로 LLM을 사용하지만 직접 호출하는 것은 아니다.

#### Ingest 내 LLM 호출 전체 목록

| 단계 | 함수 | 모델 | 호출 횟수 | 역할 | 입력 | 출력 |
|------|------|------|-----------|------|------|------|
| Step A | `_step_a_understand()` | Opus | 1회 | 소스 전체 구조 파악 | source_md (최대 8000자) | summary, key_claims, sections |
| Step A-1 | `_step_a1_write_source_page()` | Opus | 1회 | 소스 요약 페이지 초안 작성 | source_md + Step A 결과 | wiki/sources/{id}.md 본문 |
| Step B-1 | `_step_b_find_affected()` 1단계 | Opus | 1회 | index.md 기반 1차 후보 페이지 선별 | summary, sections, index.md | candidates 목록 |
| Step B-2 | `_step_b_find_affected()` 2단계 | Opus | 1회 | 후보 본문 확인 → 최종 영향 페이지 확정 + 섹션 할당 | candidates 본문, sections | affected_pages, new_pages, page_sections |
| Step C | `_step_c_semantic_dedup()` | Haiku | 1회 (new_pages 있을 때) | 의미 중복 페이지 탐지 | 신규 후보 목록, wiki 전체 제목 | duplicates 매핑 |
| Step D | `_step_d_plan_page()` | Opus | N회 (영향 페이지 수) | 페이지별 변경 계획 수립 + 본문 생성 | 담당 섹션 텍스트, 기존 페이지 내용 | 완성된 페이지 본문, paragraph_actions |
| Step E-1 | `_step_e1_review()` | Haiku | M회 (변경된 페이지 수) | 추가된 내용의 source-grounded 위반 탐지 | 추가된 내용(diff), 담당 섹션 텍스트 | violations 목록 |
| Step E-2 | `_step_e2_fix()` | Haiku | P회 (위반 페이지 수) | 위반 문장 삭제 | 위반 목록, 페이지 본문 | 수정된 페이지 본문 |

**총 호출 수 (소스 1개)**: `5 + N + M + P`
- 고정: A(1) + A-1(1) + B-1(1) + B-2(1) + C(1) = 5회
- 가변: D(영향 페이지 수) + E-1(변경 페이지 수) + E-2(위반 페이지 수, 0이면 생략)

#### 모델별 역할 분리 이유

| 모델 | 사용 단계 | 이유 |
|------|-----------|------|
| **claude-opus-4-5** | Step A, A-1, B, D | 소스 이해, 섹션 판단, 페이지 생성 등 복잡한 추론 필요 |
| **claude-haiku-4-5** | Step C, E-1, E-2 | 단순 비교·판정·삭제 작업. 비용 절감 목적 |

#### LLM을 쓰지 않는 단계

| 단계 | 처리 방식 |
|------|-----------|
| Step C 명명 정규화 | 정규식 기반 소문자+하이픈 변환 |
| Step E 실행 | 파일 읽기/쓰기, difflib diff |
| Step F | IngestState 필드 갱신 |
| Fetcher (전체) | HTTP GET / Confluence REST API / 파일 복사 |
| Normalizer/Web | trafilatura 라이브러리 (+ Jina fallback) |
| Normalizer/Confluence | BeautifulSoup XML 파싱 |
| Normalizer/Local | 파일 복사 |
| Index/Log | 파일 append/update |

---

### 처리 흐름

```
Step A   — 소스 이해                    (LLM 1회, claude-opus-4-5)
Step A-1 — 소스 요약 페이지 생성         (LLM 1회) → wiki/sources/{source_id}.md
Step B   — 영향 페이지 파악 + 섹션 라우팅 (LLM 2회) ← 2단계 탐색, 페이지별 담당 섹션 결정
Step C   — 페이지 정체성 검증 + Semantic Dedup (LLM 1회, claude-haiku-4-5)
             ├─ 명명 정규화 (소문자+하이픈)
             └─ 의미 중복 검사 — wiki 전체 대상, 배치 처리
Step D   — 페이지별 변경 계획  (LLM, 영향 페이지 수만큼, 담당 섹션만 전달)
Step E   — 실행 + before/after 스냅샷 + 매핑 정보 생성
Step E-1 — 검토 에이전트       (LLM, 추가된 내용만, 담당 섹션 기준, claude-haiku-4-5)
Step E-2 — 자동 수정           (LLM, 위반 페이지 수만큼) ← 위반 없으면 생략
Step F   — IngestState에 wiki 페이지 목록 기록
```

**LLM 호출 수 (소스 1개 기준)**: 4 + 2N (N = 영향 페이지 수, E-2 제외)
- Step A(1) + A-1(1) + B(2) + C-dedup(1) + D(N) + E-1(추가된 페이지 수)

### Step A — 소스 이해 (LLM 1회, claude-opus-4-5)

```json
{
  "summary": "1~3문장 요약",
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

`entities`, `concepts` 필드는 제거됨. 카테고리 기반 구조로 전환되어 Step B에서 직접 category와 섹션을 결정한다.

### Step A-1 — 소스 요약 페이지 생성 (LLM 1회)

```
출력: wiki/sources/{source_id}.md
```

- source 원문을 구조화·정리한 페이지. 외부 지식 추가 없이 source 그대로를 정리한다.
- 사용자가 "이 소스가 무엇을 담고 있는가"를 확인하는 용도.
- frontmatter `type: source`, `sources: ["{source_id}"]` 로 기록.

---

### Step B — 영향 페이지 파악 + 섹션 라우팅 (LLM 2회)

```
1단계: index.md 읽기 → 카테고리 + 주제 비교 → 1차 후보 선별
2단계: 후보 페이지 본문 읽기 → 최종 영향 페이지 확정 + 페이지별 담당 섹션 결정
```

```json
{
  "affected_pages": ["wiki/design/auth-architecture.md"],
  "new_pages": [
    {
      "path": "wiki/development/deploy-guide.md",
      "category": "development",
      "title": "배포 가이드"
    },
    {
      "path": "wiki/domain/oauth2.md",
      "category": "domain",
      "title": "OAuth2"
    }
  ],
  "page_sections": {
    "wiki/design/auth-architecture.md": ["인증 아키텍처", "토큰 처리"],
    "wiki/development/deploy-guide.md": ["배포 절차", "롤백"],
    "wiki/domain/oauth2.md": ["OAuth2 개요", "Authorization Code Flow"]
  },
  "routing_notes": [
    {
      "source_section": "배포 절차",
      "target_page": "wiki/development/deploy-guide.md",
      "reason": "구현/운영 절차이므로 development 카테고리"
    }
  ]
}
```

`page_sections`: 각 페이지가 담당하는 source 섹션 목록. Step D와 E-1에서 이 범위만 사용한다.

카테고리 결정 규칙:

| 카테고리 | 핵심 질문 | 예시 |
|----------|-----------|------|
| `requirements/` | 무엇을 만들어야 하는가? | 요구사항, 유저 스토리, 검증 기준 |
| `design/` | 어떻게 생겼는가? | 아키텍처, 설계 결정, API/데이터 스펙 |
| `development/` | 어떻게 구현하는가? | 구현 방법, 기술 선택, 트러블슈팅 |
| `records/` | 언제, 무엇을, 왜? | 회의록, 회고, 결정 배경, 스프린트 기록 |
| `domain/` | 이 분야 지식은? | 외부 기술/개념/업계 지식 |
| `etc/` | 위 기준으로 판단 불가 | 분류 불명확한 내용 |

### Step C — 페이지 정체성 검증 + Semantic Dedup

두 단계로 처리한다.

**1단계 — 페이지명 정규화 (코드, LLM 없음)**

| 규칙 | 예시 |
|------|------|
| 소문자 + 하이픈 | `gpt-4.md`, `large-language-model.md` |
| 축약어는 대문자 유지 | `openai.md`, `rlhf.md` |
| 띄어쓰기 → 하이픈 | `few-shot-learning.md` |
| 특수문자 제거 | `gpt4.md` |

정규화 후 동일한 이름의 페이지가 같은 디렉토리에 존재하면 신규 생성 대신 해당 페이지를 `affected_pages`로 이동한다.

**2단계 — Semantic Dedup (LLM 1회, claude-haiku-4-5)**

1단계 후에도 남은 `new_pages` 후보를 기존 wiki 전체와 의미 중복 검사한다.

```
입력: 신규 후보 목록 (path + title), wiki 전체 페이지 제목 목록
처리: Haiku가 배치로 의미 중복 판정
출력: {new_page_path: duplicate_existing_page_path | null}
```

```json
{
  "duplicates": {
    "wiki/domain/k8s.md": "wiki/domain/kubernetes.md",
    "wiki/development/deploy-guide.md": null
  }
}
```

- 중복 판정 시: `new_pages`에서 제거 → 기존 페이지를 `affected_pages`로 이동, `page_sections`도 이전
- 중복 아님: `new_pages`에 유지
- API 오류 시: 중복 없음으로 처리 (ingest 계속 진행)

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
입력: page_snapshots (before/after), page_source_map (페이지별 담당 섹션 텍스트)
처리: 이번 ingest에서 추가된 내용만 담당 섹션과 비교 → source에 없는 문장 탐지
출력: output/meta/{source_id}_review.json
```

**핵심 변경 (기존 대비)**
- 기존: 페이지 전체를 source 전체와 비교 → 이전 ingest 내용도 재검토, false positive 발생
- 현재: `_extract_new_content(before, after)`로 추가분만 추출 → `page_source_map`으로 담당 섹션만 비교

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
category: {source|requirements|design|development|records|domain|etc}
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
