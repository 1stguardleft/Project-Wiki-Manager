# OmegaWiki 분석 & 차용 전략

> [requirement-draft.md](./requirement-draft.md) 5번 항목에 따라, 같은 워크스페이스의
> **OmegaWiki**(`/Users/lstguardleft/workspace/OmegaWiki`)를 분석하여 본 프로젝트
> (Project Wiki Manager)에서 차용 가능한 부분을 정리한다. 목적은 **개발 비용·시간 절감**이다.
> 우리 프로젝트 결정 사항은 [requirements.md](./requirements.md) §10~11 참조.

---

## 1. OmegaWiki 개요

- **정체**: Karpathy의 "LLM-Wiki" 비전을 연구(논문) 도메인에 완전 구현한 프로젝트. 영구·구조화된
  지식 그래프 위키(RAG가 아님). PKU DAIR Lab 제작, 24개 슬래시 스킬, 한/영(중) 이중 언어.
- **핵심 차별점**: 질의마다 재검색하는 RAG와 달리, **9종 타입드 엔티티 + 타입드 그래프 엣지**로
  지식을 한 번 컴파일해 영구 유지. 양방향 위키링크, 명시적 gap 추적, 누적 산출물.
- **워크플로**: ingestion → 지식 그래프 → gap 탐지 → 아이디어 생성 → 실험 설계 → 논문 작성 → 동료 검토.

---

## 2. 스택 대조 (가장 중요)

| 영역 | OmegaWiki | 우리 결정 (requirements.md) | 차용 판단 |
| --- | --- | --- | --- |
| 백엔드 | 순수 Python (stdlib `ThreadingHTTPServer`) | Python (FastAPI 권장) | 개념·도구 모듈 차용, 서버는 FastAPI로 재작성 |
| 오케스트레이션 | **Claude Code 스킬**(외부 프레임워크 없음) | **LangGraph** 멀티 에이전트 | ❌ 직접 차용 불가 — 워크플로 *패턴*만 참고 |
| VectorDB | **없음**(그래프+위키링크 기반) | **Chroma** 필수 | ❌ 없음 — 우리가 신규 구현 |
| 검색 | BM25/임베딩 없음 (위키링크+그래프 이웃+TF-IDF) | **BM25+벡터 하이브리드** | ⚠️ 부분 — 후보 랭킹 로직만 참고 |
| LLM | Anthropic(Claude Code), 선택적 OpenAI 호환 | **OpenAI** | ⚠️ 클라이언트 교체 필요 |
| 프론트엔드 | Vanilla JS ES모듈 + Cytoscape (빌드 없음) | **React** | ⚠️ 그래프 뷰 로직 참고, React로 재작성 |
| 실시간 | SSE (`/api/events`, mtime 폴링) | SSE/WebSocket | ✅ SSE 라이브 리로드 패턴 차용 |
| 분류 체계 | 9종 연구 엔티티(papers/concepts/…) | **SDLC 단계**(요구/설계/…) | ⚠️ 스키마 *구조*는 차용, 타입은 교체 |

> **요약**: OmegaWiki의 **데이터 모델·스키마 시스템·검증·위키 규약**은 도메인만 바꿔 적극
> 차용할 가치가 매우 높다. 반면 **오케스트레이션·VectorDB·프론트엔드 프레임워크**는 우리 스택과
> 달라 직접 차용이 어렵고, 패턴/로직 참고 수준이다.

---

## 3. 차용 등급별 분류

### 🟢 적극 차용 (도메인만 교체)
| 자산 | 경로 | 설명 |
| --- | --- | --- |
| **스키마 시스템(왕관 보석)** | `runtime/schema/entities.yaml`, `edges.yaml`, `xref.yaml`, `conventions.yaml` | 데이터 주도 YAML 스키마. Python 수정 없이 엔티티/엣지/교차참조 규칙 정의. 엔티티를 SDLC 산출물 타입으로 교체해 재사용 |
| **스키마 로더** | `runtime/loader.py` (~250줄) | YAML 스키마를 단일 진실원천으로 로드. 코드 중복 없이 엔티티 추가 |
| **위키 엔진** | `tools/research_wiki.py` (2578줄) | 엔티티/그래프/인덱스/로그 CRUD, 컨텍스트 컴파일, 체크포인트. 20개 명령 |
| **린트 검증기** | `tools/lint.py` (1165줄) | 깨진 링크/고아 페이지/필드/엣지 비대칭 등 10개 검사 + 자동수정 |
| **페이지 템플릿** | `runtime/templates/*.md.tmpl` (8개) | 엔티티별 본문 섹션 스켈레톤 |
| **위키 규약** | index.md/log.md 구조, frontmatter, `[[slug]]` 위키링크, 양방향 xref | §4 상세 참고 |

### 🟡 적응 차용 (로직·패턴 참고 후 재작성)
| 자산 | 경로 | 우리 적용 |
| --- | --- | --- |
| SSE 라이브 리로드 | `tools/serve.py` (847줄) `/api/events` | FastAPI + SSE/WebSocket으로 에이전트 진행 이벤트 스트리밍에 응용 |
| 그래프 시각화 | `app/modules/graph.js` (Cytoscape, BFS, 필터) | React + 그래프 라이브러리로 재작성. 색/엣지 설정(`config/visualize.json`) 참고 |
| 후보 랭킹/중복 탐지 | `tools/discover.py` (TF-IDF, `_candidate_key()` 중복키) | 유사도 후보 추리기·중복 판정에 참고 (우리는 Chroma 벡터 + LLM 판단) |
| 소스 정규화/적재 플래너 | `tools/init_discovery.py`, `prepare_paper_source.py` | 단건 URL/로컬 md 수집·정규화 흐름 참고 |
| 웹 API 구조 | `serve.py` 라우팅(read/write 엔드포인트) | FastAPI 엔드포인트 설계 참고 |

### 🔴 미차용 (스택 불일치 / 도메인 특화)
- **오케스트레이션**: Claude Code 스킬 기반 → 우리는 LangGraph 신규 구현. 워크플로 단계 *순서*만 참고.
- **VectorDB / 임베딩**: OmegaWiki에 없음 → Chroma + OpenAI 임베딩 신규 구현.
- **논문/실험 특화**: arXiv/Semantic Scholar 연동, TeX/PDF 파싱, 실험 원격 실행(`remote.py`), 포스터(`poster.py`) 등은 도메인 불일치로 제외.

---

## 4. 위키 파일 규약 (차용 상세)

OmegaWiki의 규약은 도메인만 바꿔 그대로 적용 가능하다.

**디렉토리(연구 → SDLC로 매핑)**
```
OmegaWiki: wiki/{papers,concepts,topics,people,ideas,experiments,methods,Summary,foundations}/
우리:       wiki/{01-requirements,02-design,03-implementation,04-test,05-deployment,06-operation,_entities}/
공통:       wiki/graph/{edges.jsonl, citations→refs.jsonl, context_brief.md, open_questions.md}
            wiki/index.md (자동 재생성 카탈로그), wiki/log.md (append-only 로그)
```

**Frontmatter** (YAML): `title`, `slug`, `tags`, `importance`, `tldr`, `source_type`, 라이프사이클 `status` 등.
→ 우리는 `sdlc_phase`, `updated`, `source_count`, `status` 등으로 조정.

**Slug 규칙**: 소문자·하이픈, `^[a-z0-9]+(-[a-z0-9]+)*$`, 제목 키워드에서 불용어 제거 후 최대 6단어.

**위키링크**: `[[slug]]` — 엔티티 디렉토리를 순회하며 `wiki/{kind}/{slug}.md` 매칭. 네임스페이스 불필요.

**양방향 교차참조**: `xref.yaml`이 정방향 링크 작성 시 역링크를 `lint --fix`로 자동 보강. 우리 FR-MERGE-3 상호참조 갱신에 직접 활용 가능.

**그래프 엣지**: `edges.jsonl`에 `{from, to, type, confidence, evidence}` 기록. 타입드 관계로 유사/중복/충돌 표현 가능 → FR-SIM/FR-MERGE에 활용.

---

## 5. 우리 요구사항(FR) ↔ OmegaWiki 자산 매핑

| 우리 FR | 차용 자산 | 비고 |
| --- | --- | --- |
| FR-ING (수집) | `init_discovery.py`, `prepare_*` | 소스 정규화 흐름 참고. arXiv 특화 제거 |
| FR-NORM (정규화/청킹) | (없음) | OmegaWiki는 페이지=엔티티, 청킹 없음 → 우리가 신규(임베딩 청크 단위) |
| FR-SIM (유사도) | `discover.py` 랭킹·중복키 | 후보 추리기 참고. 최종 판정은 LLM(우리 결정) |
| FR-MERGE (통합) | `xref.yaml` + `lint.py` 역링크 | 자동 병합 후 표시: lint 검사로 충돌·비대칭 표시 활용 |
| FR-OUT (출력) | `templates/*.md.tmpl` | 페이지 본문 스켈레톤 |
| FR-IDX/LOG | `research_wiki.py` index/log 명령 | index.md/log.md 생성·갱신 로직 차용 |
| FR-SRCH (하이브리드 검색) | (BM25/벡터 없음) | 신규 구현. 랭킹 결합 로직만 discover.py 참고 |
| FR-VDB (Chroma/임베딩) | (없음) | 전부 신규 |
| FR-AGT (LangGraph) | 스킬 워크플로 *순서* | 단계 분해 패턴만 참고, 코드 미차용 |
| FR-VIZ (노드 그래프 시각화) | `graph.js` + `serve.py` SSE | 그래프 UI/실시간 패턴 참고, React+SSE로 재작성 |

---

## 6. 리스크 & 주의

- **스택 미스매치가 가장 큰 비용**: 오케스트레이션(LangGraph)·VectorDB·React는 OmegaWiki에서 가져올 코드가 없다. "차용으로 시간 절감"이 크게 적용되는 곳은 **스키마/위키 엔진/린트/규약** 영역에 한정된다.
- **라이선스 확인 필요**: OmegaWiki 코드를 직접 복사·재배포하기 전 라이선스(예: MIT/Apache) 확인.
- **Python 버전·의존성**: stdlib 위주라 이식성은 좋으나, FastAPI 도입 시 서버 코드는 사실상 재작성.
- **엔티티 과설계 주의**: OmegaWiki는 9종 엔티티로 정교하다. 우리는 교육 실습·시연 목적이므로 SDLC 6단계 + 최소 엔티티로 단순화 권장.

---

## 7. 권장 액션 (개발 착수 시)

1. `runtime/schema/*.yaml` + `runtime/loader.py`를 복사해 **SDLC 엔티티 스키마**로 개작 → 데이터 모델 즉시 확보.
2. `research_wiki.py`의 index/log/엣지 CRUD 로직을 FastAPI 서비스 계층으로 이식.
3. `lint.py` 검사 항목 중 도메인 무관(깨진 링크·고아·역링크)만 가져와 위키 건강 점검(FR-OPS-3)에 사용.
4. `serve.py`의 SSE 라이브 리로드 패턴을 **에이전트 진행 이벤트 스트리밍**(FR-VIZ-3)으로 확장.
5. `graph.js` Cytoscape 로직을 React 그래프 컴포넌트(FR-VIZ-1) 설계 시 레퍼런스로 활용.
6. VectorDB(Chroma)·임베딩(OpenAI)·LangGraph 오케스트레이션·하이브리드 검색은 **신규 구현**으로 일정 산정.

---

## 부록: OmegaWiki 디렉토리 맵

```
OmegaWiki/
├── wiki/                # LLM 유지 지식 베이스 (9종 엔티티 + graph/)
├── raw/                 # 원본 소스
├── runtime/             # schema/ + templates/ + loader.py (단일 진실원천) ★차용
├── tools/               # ~15개 Python 도구 (research_wiki, lint, discover, serve …) ★차용
├── app/                 # Vanilla JS SPA + Cytoscape 그래프 ⚠️참고
├── .claude/skills/      # Claude Code 슬래시 스킬(오케스트레이션) 🔴패턴만
├── mcp-servers/         # 교차 모델 리뷰 MCP(OpenAI 호환)
├── config/              # visualize.json, daily-arxiv 등
├── i18n/                # en/ + zh/ 이중 언어
└── setup.sh             # 크로스플랫폼 셋업
```
