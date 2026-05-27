# Project Wiki Manager — 설계 문서 (Design)

> 본 문서는 [requirements.md](./requirements.md)의 확정 요구사항(§10 Q1~Q20)을 구현하기 위한
> 설계다. 재사용 분석은 [omegawiki-reuse.md](./omegawiki-reuse.md) 참조.
> 스택: Python(FastAPI) + React(React Flow) + LangGraph + Chroma + OpenAI.

---

## 1. 설계 목표

- 요구사항의 **멀티 에이전트 적재 파이프라인**(§4.1)을 LangGraph 상태머신으로 구현하고,
  진행 과정을 **실시간 시각화**(과제 핵심)한다.
- VectorDB(Chroma)를 **검색·유사도·내용 보강** 세 용도의 공통 기반으로 사용한다.
- OmegaWiki의 **데이터 주도 스키마·위키 엔진·린트·규약**을 차용해 개발 비용을 절감한다.
- 데모 엔드투엔드 흐름(적재→병합→검색→질의)을 끊김 없이 시연 가능하게 한다.

---

## 2. 시스템 아키텍처

```
┌─────────────────────────── Frontend (React) ───────────────────────────┐
│  WorkflowView(React Flow)  IngestView  WikiBrowser+Search  DiffView      │
│        │ SSE 구독              │ POST        │ GET/검색        │ GET/액션   │
└────────┼─────────────────────┼─────────────┼─────────────────┼──────────┘
         ▼                     ▼             ▼                 ▼
┌─────────────────────────── Backend (FastAPI) ──────────────────────────┐
│  api/  (ingest, runs/events, search, query, wiki, merges)                │
│  agents/  LangGraph 그래프 + 노드  ──이벤트──▶  events/ (run별 큐→SSE)     │
│  services/  wiki_engine · parser · embedding · vectordb · search · query │
│  schema/  entities.yaml · edges.yaml · conventions.yaml + loader.py      │
└──────┬───────────────────────┬──────────────────────┬───────────────────┘
       ▼                       ▼                      ▼
   raw/ (불변)            wiki/ (md+graph+index+log)   Chroma (벡터)
                                                       ▲
                                           OpenAI (LLM 생성 / 임베딩)
```

- **3계층 유지**(req §4): raw(원본) / wiki(LLM 생성) / schema(CLAUDE.md + YAML 스키마).
- 백엔드는 파일시스템(`wiki/`, `raw/`)과 Chroma를 단일 소유. 프론트는 API만 호출.

---

## 3. 프로젝트 디렉토리 구조

```
project-wiki-manager/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI 앱 · 라우터 등록 · CORS
│   │   ├── api/                   # 라우터
│   │   │   ├── ingest.py  runs.py  search.py  query.py  wiki.py  merges.py
│   │   ├── agents/                # LangGraph
│   │   │   ├── graph.py           # StateGraph 정의 · 컴파일
│   │   │   ├── state.py           # IngestState (TypedDict)
│   │   │   └── nodes/             # fetch.py parse.py normalize.py chunk.py
│   │   │       embed.py similarity.py merge.py crossref.py index.py log.py lint.py
│   │   ├── services/
│   │   │   ├── wiki_engine.py     # 페이지 CRUD · index.md · log.md · edges.jsonl
│   │   │   ├── parser.py          # URL/HTML/md 파싱
│   │   │   ├── embedding.py       # OpenAI 임베딩
│   │   │   ├── vectordb.py        # Chroma 래퍼
│   │   │   ├── search.py          # 하이브리드(BM25+벡터) + RRF + 재랭킹
│   │   │   └── query.py           # 질의 종합 + 인용
│   │   ├── events/
│   │   │   └── bus.py             # run_id별 asyncio.Queue · SSE 발행기
│   │   ├── schema/                # ★ OmegaWiki 차용·개작
│   │   │   ├── entities.yaml  edges.yaml  conventions.yaml  loader.py
│   │   └── models/                # Pydantic 요청/응답 모델
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── views/                 # WorkflowView IngestView WikiBrowser DiffView
│   │   ├── components/            # nodes/ (React Flow 커스텀 노드) · PagePanel 등
│   │   ├── hooks/                 # useRunEvents(SSE) · useSearch · useWiki
│   │   └── api/                   # fetch 클라이언트
│   └── package.json
├── wiki/                          # 생성물 (git 추적)
├── raw/                           # 원본 (git 추적)
└── CLAUDE.md                      # 위키 스키마·워크플로 규약
```

---

## 4. 백엔드 — API 명세

| 메서드·경로 | 설명 | 요청/응답 | 관련 FR |
| --- | --- | --- | --- |
| `POST /api/ingest` | 단건 적재 시작 | `{source_type:"url"\|"file", url?, file?}` → `{run_id}` | FR-ING, FR-OPS-1 |
| `GET /api/runs/{run_id}/events` | 진행 이벤트 SSE 스트림 | `text/event-stream` (§5.3 이벤트) | FR-VIZ-3, FR-AGT-2 |
| `POST /api/runs/{run_id}/approve` | HITL 승인(awaiting_input) | `{node_id, decision}` | FR-OPS-1, NFR-3 |
| `POST /api/runs/{run_id}/resume` | 실패 지점부터 재개 | → `{run_id}` | §4.3 |
| `GET /api/search` | 하이브리드 검색 | `?q=&phase=&k=` → 결과+스코어+출처 | FR-SRCH |
| `POST /api/query` | 위키 질의 | `{question}` → `{answer, citations[]}` | FR-OPS-2, UC-4 |
| `GET /api/wiki/pages` | 페이지 목록(단계별) | `?phase=` → 목록 | FR-IDX |
| `GET /api/wiki/pages/{slug}` | 페이지 본문·frontmatter·백링크 | → 페이지 | 13.3 |
| `GET /api/wiki/graph` | 지식그래프 노드/엣지 | → `{nodes, edges}` | FR-VIZ-4 |
| `GET /api/wiki/log` | 타임라인 로그 | → log 항목 | FR-LOG |
| `GET /api/merges/{id}/diff` | 병합 충돌·diff 데이터 | → diff/충돌 블록 | FR-MERGE-2, 13.4 |
| `POST /api/merges/{id}/accept`·`/revert` | 병합 수락/되돌리기 | | 13.4 |

- 인증 없음(Q15, 로컬·단일 사용자). CORS는 프론트 dev 서버 허용.

---

## 5. LangGraph 멀티 에이전트 설계

### 5.1 상태 (`agents/state.py`)
```python
class IngestState(TypedDict):
    run_id: str
    source: dict                 # {type:"url"|"file", ref}
    raw_path: str | None
    parsed_text: str | None
    normalized_md: str | None
    chunks: list[dict]           # [{chunk_id, sdlc_phase, text}]
    vector_ids: list[str]
    similar_candidates: list[dict]   # 벡터 후보 + LLM 판정
    merge_decision: dict | None      # {action:"merge"|"create", target_slug?}
    page_slug: str | None
    edges: list[dict]
    errors: list[dict]
```

### 5.2 그래프 (`agents/graph.py`)
```
START → fetch → parse → normalize → chunk → embed → similarity
                                                         │ (조건 분기)
                                  ┌──────────────────────┴───────────┐
                          action="merge"                      action="create"
                                  └──────────────► merge ◄───────────┘
                                                    │
                                  crossref → index → log → END
```
- `add_conditional_edges(similarity, route_by_decision)`로 merge/create 분기(merge 노드가 두 경우 모두 처리).
- 각 노드는 `IngestState`를 입력받아 부분 갱신 dict 반환.
- **세분화**(Q18)로 노드 수를 늘려 시각화를 풍부하게 함.

### 5.3 이벤트 발행
- 각 노드 진입/종료 시 `events/bus.py`의 run별 `asyncio.Queue`에 `node_update` 이벤트 push.
- LangGraph `astream`/콜백을 노드 래퍼로 감싸 상태 전이를 이벤트로 변환.
- 이벤트 스키마(req §4.2 준수):
  ```json
  {"run_id","node_id","node_label","status","started_at","ended_at",
   "duration_ms","input_summary","output_summary","artifacts":[],"message","error"}
  ```
- SSE 엔드포인트가 큐를 소비해 `event: node_update\ndata: {...}` 전송.

### 5.4 노드 구현 요약
| 노드 | 핵심 동작 | 사용 서비스 |
| --- | --- | --- |
| fetch | URL/파일 → `raw/` 저장 | parser |
| parse | HTML→텍스트(markdownify 등) | parser |
| normalize | 구조 재구성·노이즈 제거(LLM) | query/LLM |
| chunk | 헤딩+토큰 기반 분할(§7.3) | — |
| embed | 청크 임베딩 → Chroma upsert | embedding, vectordb |
| similarity | 벡터 top-k 후보 + LLM 유사/중복 판정 | vectordb, LLM |
| merge | 자동 통합/신규 생성 + 충돌 표시 | wiki_engine, LLM |
| crossref | 위키링크·edges.jsonl 갱신 | wiki_engine |
| index | index.md + 검색 인덱스 갱신 | wiki_engine, search |
| log | log.md append | wiki_engine |
| lint | (on-demand) 건강 점검 | wiki_engine |

---

## 6. 데이터 모델 · 스키마 (OmegaWiki 차용)

### 6.1 스키마 시스템
- `schema/entities.yaml` — 페이지 타입(deliverable/entity), 필드, 라이프사이클.
- `schema/edges.yaml` — 엣지 타입(references, duplicate_of, merged_from, supersedes, conflicts_with, relates_to).
- `schema/conventions.yaml` — slug 규칙, 위키링크, frontmatter 필수 필드.
- `schema/loader.py` — YAML 로드(OmegaWiki `runtime/loader.py` 개작). Python 수정 없이 스키마 확장.

### 6.2 위키 파일 레이아웃
```
wiki/
  01-requirements/ 02-design/ 03-implementation/ 04-test/ 05-deployment/ 06-operation/
  _entities/
  graph/edges.jsonl        # {from,to,type,confidence,evidence}
  index.md                 # 카탈로그(자동 갱신)
  log.md                   # ## [YYYY-MM-DD] ingest|query|lint | title
```

### 6.3 Frontmatter (req §14.2)
공통: `title, slug, type, sdlc_phase, tags, status, updated, source_count, sources`.
`status` enum: `draft|active|superseded`.

### 6.4 청킹 / 임베딩 / Chroma
- 청킹: 마크다운 헤딩 우선 + 512~1024 토큰, 중첩 ~15%.
- 임베딩: OpenAI `text-embedding-3-small`(1536d). 배치 호출.
- Chroma: 단일 컬렉션 `wiki`, 메타데이터 `{page_slug, chunk_id, sdlc_phase, source, updated}`.
- 동기화: 페이지 생성/변경/삭제 시 청크 벡터 upsert/delete(FR-VDB-3).

---

## 7. 검색 설계 (하이브리드)

```
query → ① BM25 (wiki 청크 전문검색)  ┐
        ② 벡터 검색 (Chroma top-k)    ├→ RRF 결합 → (선택) LLM 재랭킹 → 결과
                                      ┘
```
- **BM25**: `rank_bm25` 등으로 wiki 청크 인덱스 구성(메모리/파일). index 노드에서 갱신.
- **벡터**: Chroma 유사도 검색.
- **결합**: Reciprocal Rank Fusion(RRF)으로 두 랭킹 병합 후 상위 LLM 재랭킹(FR-SRCH-2).
- 결과에 출처·SDLC 단계 표기. 내부 LLM 도구로도 호출 가능(FR-SRCH-4).

---

## 8. 프론트엔드 설계

### 8.1 라우팅 / 화면 (req §13)
| 라우트 | 뷰 | 핵심 |
| --- | --- | --- |
| `/ingest` | IngestView | URL/파일 입력 → run 시작 → WorkflowView 연결 |
| `/runs/:runId` | WorkflowView | React Flow 노드 그래프 + SSE 실시간 상태 |
| `/wiki` | WikiBrowser | 단계별 목록 + 본문 뷰어 + 하이브리드 검색 + 지식그래프(React Flow) |
| `/merges/:id` | DiffView | 충돌/diff 표시 + 수락/되돌리기 |

### 8.2 워크플로우 시각화 (핵심)
- **React Flow** 커스텀 노드: §5.4 노드를 그래프로 배치(고정 레이아웃 + 조건 분기 엣지).
- `useRunEvents(runId)` 훅이 SSE 구독 → 노드 상태 갱신(대기/진행/완료/실패/입력대기 색·아이콘).
- 노드 클릭 → 입력·출력·소요시간·산출물 패널. `awaiting_input` 시 승인 버튼 → `POST approve`.
- run 타임라인/로그 스트림 동반 표시.

### 8.3 상태 관리
- 서버 상태: React Query(목록·페이지·검색·그래프 캐싱).
- 실시간 run 상태: SSE 이벤트를 reducer로 노드 맵에 누적.

---

## 9. 실시간 통신 (SSE)

- `events/bus.py`: `dict[run_id, asyncio.Queue]`. 노드 래퍼가 이벤트 push.
- `GET /api/runs/{run_id}/events`: `StreamingResponse`(text/event-stream)로 큐 소비.
- run 종료 시 `run_completed|run_failed` 발행 후 채널 정리.
- (양방향 제어 필요 시 WebSocket 승격 — 현재는 승인도 별도 POST로 처리하여 SSE 유지.)

---

## 10. 에러 처리 · HITL (req §4.3)

- 외부 호출 노드(fetch·embed·LLM): N회 재시도 → 실패 시 `failed` 이벤트, 이후 노드 `skipped`.
- 부분 실패: 저장된 raw·청크 보존, run은 부분 실패로 종료, `resume`로 재개.
- HITL: merge commit 직전 `awaiting_input` 옵션, 사용자 승인 후 진행(NFR-3).

---

## 11. OmegaWiki 차용 매핑

| 본 설계 모듈 | 차용 원본 | 개작 |
| --- | --- | --- |
| `schema/*.yaml` + `loader.py` | `runtime/schema/*` + `loader.py` | 연구 엔티티 → SDLC deliverable/entity |
| `services/wiki_engine.py` | `tools/research_wiki.py` | index/log/edges CRUD 이식 |
| `nodes/lint.py` | `tools/lint.py` | 깨진 링크·고아·역링크 검사만 |
| `events/bus.py` SSE | `tools/serve.py` `/api/events` | mtime 폴링 → 노드 이벤트 스트림 |
| 지식그래프 뷰 | `app/modules/graph.js` | Cytoscape → React Flow 재작성 |
| similarity 후보·중복 | `tools/discover.py` | TF-IDF → Chroma 벡터 + LLM 판정 |

> 신규 구현(차용 코드 없음): LangGraph 오케스트레이션, Chroma/임베딩, 하이브리드 검색, React UI.
> ⚠️ OmegaWiki 코드 복사 전 **라이선스 확인** 필요.

---

## 12. 데모 시나리오 매핑 (req §15.2)

| 데모 단계 | 동작 경로 |
| --- | --- |
| ① 적재 | IngestView → `POST /ingest` → WorkflowView(노드 점등) → 위키 페이지 생성 |
| ② 병합 | 유사 문서 적재 → similarity 분기 → merge → DiffView 충돌 확인 |
| ③ 검색 | WikiBrowser 검색 → 하이브리드(BM25+벡터) 결과 |
| ④ 질의 | `POST /query` → 인용 답변 → 결과 페이지 누적 |

---

## 13. 구현 마일스톤 (제안)

1. **M1 스키마·위키 엔진**: `schema/*.yaml` + `wiki_engine`(페이지/인덱스/로그 CRUD) — OmegaWiki 차용.
2. **M2 적재 파이프라인(기본)**: fetch→parse→normalize→chunk→index 노드 + `POST /ingest`.
3. **M3 VectorDB·검색**: embedding·vectordb·search(하이브리드) + Chroma 동기화.
4. **M4 유사도·병합**: similarity(벡터+LLM)·merge·crossref + 충돌 표시.
5. **M5 실시간 시각화**: events/bus SSE + WorkflowView(React Flow) — **데모 핵심**.
6. **M6 위키 뷰어·검색·diff·질의 UI**: WikiBrowser·DiffView·query.
7. **M7 린트·다듬기·데모 데이터**: lint + 엔드투엔드 데모 리허설.

---

## 14. 미해결 / 위험

- LangGraph 노드 이벤트 발행 방식(astream vs 커스텀 콜백) — M2에서 PoC로 확정.
- 자동 병합 품질(LLM 판정 오판) — 충돌 표시·사후 검토로 완화(Q14).
- OpenAI 비용 — 임베딩 배치·캐시, `-small` 모델 기본.
- 보안(외부 URL 수집 SSRF) — 사설 IP 차단 등 최소 방어(추후).
- 샘플 데이터셋 준비(중복 사례 포함) — M7 전 확보 필요.
