# Project Wiki Manager

소규모 개발 프로젝트의 산출물 문서를 **LLM이 지속적으로 구축·유지하는 위키**로 통합하는
교육용 풀스택 애플리케이션. 핵심 작업(적재)은 **LangGraph 멀티 에이전트 파이프라인**으로
처리되며, 그 진행 과정을 **React Flow로 실시간 시각화**한다.

설계 문서: [`.claude/docs/requirements.md`](.claude/docs/requirements.md) ·
[`.claude/docs/design.md`](.claude/docs/design.md)

## 스택
- **백엔드**: Python · FastAPI · LangGraph · Chroma(VectorDB) · OpenAI
- **프론트엔드**: React · React Flow · Vite
- **위키**: 마크다운 파일(`wiki/`) + 그래프(`edges.jsonl`) + `index.md`/`log.md`

## 아키텍처
```
React(워크플로우/위키/diff) ──HTTP·SSE──▶ FastAPI
                                          ├─ agents/  LangGraph 파이프라인 (10 노드)
                                          ├─ services/ wiki_engine·parser·embedding·
                                          │            vectordb·search·query·lint
                                          └─ schema/  entities·edges·conventions(YAML)
   raw/(원본 불변)   wiki/(LLM 생성)   .chroma/(벡터)
```
적재 파이프라인: `fetch → parse → normalize → chunk → embed → similarity → merge →
crossref → index → log`. 유사도는 **벡터 후보 + LLM 판정**, 병합은 **자동 + 충돌 표시**.

## 실행

### 1) 백엔드
```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e .
export OPENAI_API_KEY=sk-...        # 없으면 오프라인 폴백 모드로 동작
.venv/bin/uvicorn app.main:app --reload --port 8000
```

### 2) 프론트엔드
```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

### 3) 데모 데이터 시드(선택)
```bash
cd backend
.venv/bin/python -m scripts.seed_demo
```
`demo/*.md` 4개 문서를 적재한다 — 로그인 v1/v2는 **중복 감지 후 병합**되고,
나머지는 SDLC 단계(requirements/design/test)별로 분류된다.

## 데모 시나리오 (엔드투엔드)
1. **적재**: `/ingest`에서 md 입력 → 워크플로우 뷰에서 노드가 순차 점등
2. **병합**: 유사 문서 적재 → similarity가 중복 판정 → merge → `/merges`에서 충돌 확인
3. **검색**: `/wiki`에서 하이브리드(BM25+벡터) 검색
4. **질의**: 위키에 질문 → 인용 기반 답변

## 오프라인 모드
`OPENAI_API_KEY`가 없으면 LLM/임베딩이 결정적 폴백(요약=정제, 해시 임베딩)으로 대체되어
**전체 파이프라인과 시각화가 그대로 동작**한다. 데모/개발에 유용.

## 참고
- 위키 패턴 출처: `.claude/docs/references/llm-wiki.md`
- 차용 참조 구현(OmegaWiki, MIT) 분석: `.claude/docs/omegawiki-reuse.md`
