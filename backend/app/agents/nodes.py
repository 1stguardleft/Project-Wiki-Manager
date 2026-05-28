"""Pipeline node implementations (requirements §4.1, §5.4).

Each node is a plain function taking IngestState and returning a partial update.
Event emission and timing are handled by the graph wrapper (graph.py), so node
bodies stay focused on their single responsibility.  All nodes work offline
(no OPENAI_API_KEY) via services.llm fallbacks.
"""
from __future__ import annotations

import json
import re

from app.agents import merge_store, resolvers
from app.agents.state import IngestState
from app.schema import loader
from app.services import (chunking, llm, parser, titling, vectordb, wiki_engine)

# Node registry: (id, label) in pipeline order. graph.py wires the edges.
# Each node is presented to the user as an "agent" in the multi-agent pipeline.
NODE_SPECS = [
    ("fetch", "수집 Agent"), ("parse", "파싱 Agent"), ("normalize", "정규화 Agent"),
    ("decompose", "도메인 분해 Agent"),
    ("chunk", "청킹 Agent"), ("embed", "임베딩 Agent"), ("similarity", "유사도 Agent"),
    ("conflict", "충돌판정 Agent"), ("merge", "병합 Agent"), ("verify", "누락검토 Agent"),
    ("crossref", "상호참조 Agent"), ("index", "인덱싱 Agent"), ("log", "로깅 Agent"),
]

# Nodes that call the LLM (chat or embeddings) — surfaced as a badge in the UI.
LLM_NODES = {"normalize", "decompose", "embed", "similarity", "conflict", "merge",
             "verify", "crossref"}

# Relationship types the crossref agent may assign (subset of schema edge_types;
# the rest — merged_from/supersedes/conflicts_with — are owned by merge/resolvers).
CROSSREF_EDGE_TYPES = ("implements", "verifies", "refines", "relates_to")

# Korean labels for the auto-rendered '연관 도메인/서브도메인/관계' table in the
# page body. `merged_from` is intentionally excluded — it's page provenance, not
# a reader-facing relation.
EDGE_TYPE_KO = {
    "references": "참조", "relates_to": "연관",
    "implements": "구현", "verifies": "검증", "refines": "구체화",
    "duplicate_of": "중복", "supersedes": "대체", "conflicts_with": "충돌",
}

# HTML-comment markers isolate the crossref-managed section from user edits
# elsewhere in the body. Anything OUTSIDE the markers is left untouched on
# re-runs; anything INSIDE is regenerated from the current edges.jsonl.
CROSSREF_AUTO_START = "<!-- crossref:auto -->"
CROSSREF_AUTO_END = "<!-- /crossref:auto -->"
_CROSSREF_AUTO_RE = re.compile(
    re.escape(CROSSREF_AUTO_START) + r".*?" + re.escape(CROSSREF_AUTO_END),
    re.DOTALL)

# 작성자가 소스 마크다운에 직접 박아 둔 "## N. 연관 (서브)도메인 | 도메인 | 기능 …"
# 섹션을 잡아내는 패턴. crossref Agent는 적재 시 이 섹션을 *흡수*해서 자동 표로
# 치환한다(별도 섹션이 2개로 떠 있는 노이즈 제거). 매칭 종료는 다음 H2 또는 EOF.
# 패턴이 너무 넓으면 무관한 "## N. 연관 …" 도 잡힐 수 있으므로, 데모/템플릿에서
# 실제로 쓰는 단어(서브도메인 / 도메인 / 기능)로 한정한다.
_LEGACY_RELATED_SECTION_RE = re.compile(
    r"^##\s+\d+\.\s*연관\s+(?:서브도메인|도메인|기능)[^\n]*\n.*?(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)

# Max corrective re-merges the 누락검토 loop will trigger before giving up.
MAX_MERGE_RETRIES = 1

_PHASE_KEYWORDS = {
    "requirements": ["요구사항", "유스케이스", "requirement", "scope", "범위"],
    "design": ["설계", "아키텍처", "architecture", "design", "api", "db", "화면"],
    "implementation": ["구현", "코드", "implementation", "convention", "컨벤션", "guide"],
    "test": ["테스트", "test", "qa", "케이스", "검증"],
    "deployment": ["배포", "deploy", "release", "릴리스", "환경"],
    "operation": ["운영", "operation", "모니터링", "트러블", "monitor"],
}

# Unambiguous stage markers used in a document's *title* (its authoritative
# self-description). A title that names its SDLC stage decides the phase
# outright — body keyword frequency is only a fallback, because domain
# vocabulary collides with phase keywords (e.g. an SKU '코드' requirement counts
# as 'implementation', 화면/api in a requirement counts as 'design') and can
# outvote the real stage. Order = priority when a title names more than one.
_PHASE_TITLE_MARKERS = {
    "requirements": ["요구사항", "유스케이스"],
    "design": ["설계", "아키텍처"],
    "implementation": ["구현", "컨벤션"],
    "test": ["테스트", "qa"],
    "deployment": ["배포", "릴리스"],
    "operation": ["운영", "모니터링"],
}


# ── Nodes ──────────────────────────────────────────────────────────────────
def fetch(state: IngestState) -> dict:
    source = state["source"]
    title, md = parser.parse_source(source)
    raw_path = parser.save_raw(source.get("ref", title), md)
    return {"raw_path": str(raw_path), "parsed_text": md, "title": title}


def parse_node(state: IngestState) -> dict:
    # parse_source already produced markdown; here we strip residual noise.
    text = state.get("parsed_text") or ""
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return {"parsed_text": text}


def normalize(state: IngestState) -> dict:
    text = state.get("parsed_text") or ""
    title = state.get("title") or "Untitled"
    system = ("Reformat the document into clean markdown for a software project "
              "wiki: keep a single H1 title, use sections, remove boilerplate. "
              "Write the H1 as a clean, natural document title; do NOT include "
              "round/version markers such as (1차), (2차), 1차, 2차 in it. "
              "PRESERVE verbatim any HTML comment markers like "
              "'<!-- crossref:auto -->' and '<!-- /crossref:auto -->' and ALL "
              "content between them — they are a machine-managed section. "
              "Return only markdown.")
    normalized = llm.chat(text[:8000], system=system) or text
    phase = _classify_phase(normalized, title=title)
    slug = loader.slugify(title)
    return {"normalized_md": normalized, "sdlc_phase": phase, "slug": slug}


def decompose(state: IngestState) -> dict:
    """도메인 분해 Agent — split a composite document into domain > sub-domain units.

    Uses existing wiki pages as a self-organizing domain/sub-domain catalog. A
    cohesive single-topic doc yields one unit and the pipeline continues normally.
    A doc bundling separate sub-domains fans out into one child run per sub-domain,
    each routed to its page (graph._decompose_router sends the parent to END).
    Child units (already split) and offline mode never re-split.
    """
    from app.services import runs

    src = state.get("source") or {}
    # a child unit is already one sub-domain → don't re-decompose, just tag it
    if src.get("unit_title"):
        return {"units": [], "domain": src.get("domain"),
                "subdomain": src.get("subdomain")}

    text = state.get("normalized_md") or ""
    units = _judge_decompose(text, loader.DOMAIN_MAP["domains"], wiki_engine.list_pages())

    # single unit → keep the original normalized_md, just record domain/sub-domain
    if len(units) <= 1:
        u = units[0] if units else {}
        return {"units": units, "domain": u.get("domain"),
                "subdomain": u.get("subdomain")}

    # composite → one child run per sub-domain unit; this (parent) run ends here
    origin = src.get("path") or src.get("ref")
    spawned = []
    for u in units:
        child = {"type": "file", "content": u["body"],
                 "ref": f"{src.get('ref', '')} — {u['title']}"[:120],
                 "origin": origin, "unit_title": u["title"],
                 "domain": u.get("domain"), "subdomain": u.get("subdomain"),
                 "target_slug": u.get("target_slug")}
        if src.get("conflict_policy"):
            child["conflict_policy"] = src["conflict_policy"]
        spawned.append(runs.new_run(child))
    return {"units": units, "spawned_runs": spawned}


def chunk(state: IngestState) -> dict:
    chunks = chunking.chunk_markdown(
        state.get("normalized_md") or "", state["slug"], state.get("sdlc_phase"))
    return {"chunks": chunks}


def embed(state: IngestState) -> dict:
    ids = vectordb.upsert_chunks(state.get("chunks") or [])
    return {"vector_ids": ids}


def similarity(state: IngestState) -> dict:
    """Vector candidates -> LLM judgment of duplicate/similar (FR-SIM)."""
    from app import config

    text = (state.get("normalized_md") or "")[:2000]
    slug = state["slug"]
    hits = vectordb.query(text, k=6)
    candidates = [h for h in hits if h["page_slug"] and h["page_slug"] != slug]
    # dedupe by page
    seen, cands = set(), []
    for h in candidates:
        if h["page_slug"] in seen:
            continue
        seen.add(h["page_slug"])
        cands.append(h)

    # domain decomposition routed this unit to an explicit page → merge there
    hint = (state.get("source") or {}).get("target_slug")
    if hint and hint != slug and wiki_engine.find_page_path(hint):
        return {"similar_candidates": cands,
                "merge_decision": {"action": "merge", "target_slug": hint,
                                   "reason": "도메인 라우팅"}}

    # A pre-existing page with the same slug is a strong duplicate — merge to
    # avoid silently overwriting it.
    if wiki_engine.find_page_path(slug):
        decision = {"action": "merge", "target_slug": slug,
                    "reason": "동일 slug 기존 페이지 존재"}
    else:
        # The wiki keys a page by (domain, sub-domain, SDLC phase) — each lands in
        # its own numbered folder; different phases/sub-domains are separate pages
        # linked by crossref edges, never merged. The taxonomy (not vector
        # distance) is therefore the authority on "is this the same page?":
        #
        #  • classified unit → only candidates in the SAME (domain, sub-domain,
        #    phase) slot may merge, and they go to the judge REGARDLESS of vector
        #    distance — a revised 2차/버전 of one doc can drift past any distance
        #    threshold yet is still the same page. (False merges like 고객 검색 →
        #    공통 응답 differ in sub-domain, so they never reach the judge.)
        #  • unclassified unit (no taxonomy) → fall back to a vector distance gate
        #    so we don't blindly merge on shared template vocabulary.
        in_dom = (state.get("domain") or "").strip()
        in_sub = (state.get("subdomain") or "").strip()
        in_phase = (state.get("sdlc_phase") or "").strip()

        if in_sub:
            same_slot = [c for c in cands
                         if _page_taxonomy_key(c["page_slug"]) == (in_dom, in_sub, in_phase)]
            if same_slot:
                decision = _judge_similarity(text, same_slot)
            else:
                decision = {"action": "create",
                            "reason": "동일 (도메인·서브도메인·단계) 페이지 없음 — 별개 페이지로 생성"}
        else:
            near = [c for c in cands if c.get("distance") is not None
                    and c["distance"] <= config.SIMILARITY_MAX_DISTANCE]
            if near:
                decision = _judge_similarity(text, near)
            elif cands:
                decision = {"action": "create",
                            "reason": f"최근접 후보 거리 {cands[0]['distance']:.3f} > "
                                      f"{config.SIMILARITY_MAX_DISTANCE} — 별개 페이지로 생성"}
            else:
                decision = {"action": "create", "reason": "no similar page found"}
    return {"similar_candidates": cands, "merge_decision": decision}


def conflict(state: IngestState) -> dict:
    """LLM judges the semantic relationship between the incoming document and the
    existing page it would merge into: contradiction / augmentation / duplicate.

    Runs only when `similarity` chose `merge`; otherwise there is nothing to
    compare against. Its `conflict_report` becomes the authoritative conflict
    source consumed by the `merge` node (FR-MERGE).
    """
    decision = state.get("merge_decision") or {}
    target = decision.get("target_slug")
    if decision.get("action") != "merge" or not target:
        return {"conflict_report": {"relation": "none", "conflicts": [],
                                    "summary": "신규 페이지 — 비교 대상 없음"}}
    existing = wiki_engine.read_page(target)
    if not existing:
        return {"conflict_report": {"relation": "none", "conflicts": [],
                                    "summary": "기존 페이지를 찾지 못함"}}
    report = _judge_conflict(existing["body"], state.get("normalized_md") or "")
    return {"conflict_report": report}


def merge(state: IngestState) -> dict:
    from app import config

    # ── corrective re-merge: the 누락검토 Agent looped us back with omissions ──
    audit = state.get("merge_audit") or {}
    omissions = (state.get("coverage_report") or {}).get("omissions") or []
    if audit.get("mode") == "reconciled" and omissions:
        target = audit["target"]
        patched = _remerge_with_omissions(
            audit["before"], audit["incoming"], audit["merged"], omissions)
        existing = wiki_engine.read_page(target)
        fm = dict(existing["frontmatter"]) if existing else {"slug": target}
        wiki_engine.write_page(target, fm, patched)
        if state.get("merge_id"):
            merge_store.update(state["merge_id"], after=patched)
        return {"page_slug": target,
                "merge_audit": {**audit, "merged": patched},
                "merge_retries": (state.get("merge_retries") or 0) + 1}

    decision = state.get("merge_decision") or {"action": "create"}
    slug = state["slug"]
    title = state.get("title") or slug
    phase = state.get("sdlc_phase")
    body = state.get("normalized_md") or ""
    sources = [state.get("raw_path") or state["source"].get("ref", "")]

    if decision.get("action") == "merge" and decision.get("target_slug"):
        target = decision["target_slug"]
        existing = wiki_engine.read_page(target)
        if existing:
            before = existing["body"]
            report = state.get("conflict_report") or {}
            relation = report.get("relation", "")
            report_conflicts = report.get("conflicts") or []

            # A contradiction is handed to the configured resolution strategy (a
            # per-source override falls back to the global default). A same-slug
            # collision can't coexist as two pages, so it always merges instead.
            if relation == "contradiction" and slug != target:
                strategy = (state["source"].get("conflict_policy")
                            or config.CONFLICT_STRATEGY)
                ctx = resolvers.ConflictContext(
                    slug=slug, target=target, title=title, phase=phase,
                    body=body, before=before, existing=existing,
                    conflicts=report_conflicts, report=report, sources=sources)
                return resolvers.resolve(strategy, ctx)

            merged_body, change_notes = _merge_bodies(before, body)
            # the conflict node's semantic judgment is authoritative; otherwise
            # fall back to the '변경' notes the merge produced while reconciling.
            conflicts = report_conflicts or change_notes
            fm = dict(existing["frontmatter"])
            fm["source_count"] = fm.get("source_count", 1) + 1
            fm["sources"] = list(dict.fromkeys((fm.get("sources") or []) + sources))
            if state.get("domain") and not fm.get("domain"):
                fm["domain"] = state["domain"]
            if state.get("subdomain") and not fm.get("subdomain"):
                fm["subdomain"] = state["subdomain"]
            # accumulated page → LLM retitles from the merged content (slug fixed)
            fm["title"] = titling.suggest_title(merged_body, fm.get("title"))
            wiki_engine.write_page(target, fm, merged_body)
            # 충돌 없는 자동 병합. 이 경로는 사람 개입이 없으므로 status를
            # 명시해 둔다(기본값 'pending'을 그대로 두면 KPI/머지 뷰가 수동
            # 검토 대기로 오인한다 — 데이터 정정의 단일 소스).
            mid = merge_store.create(target, before, merged_body, conflicts,
                                     sources, relation=relation,
                                     policy="auto_merge", status="auto_merged")
            return {"page_slug": target, "merge_id": mid,
                    "edges": [{"from": target, "to": slug, "type": "merged_from"}],
                    "merge_audit": {"mode": "reconciled", "target": target,
                                    "before": before, "incoming": body,
                                    "merged": merged_body}}

    # create new page — let the LLM titler set a clean display title (drops the
    # source H1's round markers like '(1차)'); slug keeps the original identity.
    fm = {"title": titling.suggest_title(body, title), "slug": slug,
          "type": "deliverable", "sdlc_phase": phase, "domain": state.get("domain"),
          "subdomain": state.get("subdomain"), "status": "active",
          "source_count": 1, "sources": sources}
    wiki_engine.write_page(slug, fm, body)
    return {"page_slug": slug, "edges": [], "merge_audit": {"mode": "created"}}


def verify(state: IngestState) -> dict:
    """누락검토 Agent — verify the reconciled page didn't drop info from either
    source. Only meaningful when `merge` produced a single reconciled page; for
    split (manual/prefer_*) or newly-created pages there is nothing to compare.

    Its `coverage_report.omissions` drives the graph loop back to `merge` (see
    graph._verify_router) for one bounded corrective re-merge.
    """
    audit = state.get("merge_audit") or {}
    if audit.get("mode") != "reconciled":
        return {"coverage_report": {"coverage": 1.0, "omissions": [],
                                    "summary": "검증 불필요 (단일 병합 아님)"}}
    report = _check_omissions(audit["before"], audit["incoming"], audit["merged"])
    if state.get("merge_id"):
        merge_store.update(state["merge_id"], coverage=report.get("coverage"),
                           omissions=report.get("omissions") or [])
    return {"coverage_report": report}


def crossref(state: IngestState) -> dict:
    """상호참조 Agent — link the new page to genuinely related ones.

    Cosine vector search is only the *candidate retriever* (cheap recall); the
    LLM is the *judge* (precision) that confirms each link and writes the
    human-readable 근거. This mirrors the similarity→_judge_similarity pattern.
    Offline (no LLM) it falls back to a cosine-distance gate.
    """
    from app import config

    edges = state.get("edges") or []
    page = state.get("page_slug")
    # don't add a generic relates_to where a stronger edge (merged_from,
    # conflicts_with) already connects the same pair
    linked = {(e["from"], e["to"]) for e in edges}
    linked |= {(e["to"], e["from"]) for e in edges}
    cands = [c for c in (state.get("similar_candidates") or [])
             if c["page_slug"] != page and (page, c["page_slug"]) not in linked]

    # Guard: 초기 적재 시 LLM이 빈약한 컨텍스트로 억지 관계를 만들지 않도록,
    # 위키 페이지 수가 임계값 미만이면 LLM 호출과 엣지 추가를 모두 건너뛴다.
    # 본문의 자동 섹션도 비워서 "아직 생성되지 않음" 상태를 명확히 한다.
    # 누적된 코퍼스 기준 재생성은 `POST /api/wiki/rebuild-crossref` 사용.
    wiki_size = len(wiki_engine.list_pages())
    if wiki_size < config.MIN_PAGES_FOR_CROSSREF:
        if page:
            page_obj = wiki_engine.read_page(page)
            if page_obj:
                new_body = _inject_crossref_section(page_obj["body"], "")
                if new_body != page_obj["body"]:
                    wiki_engine.write_page(page, page_obj["frontmatter"], new_body)
        return {"edges": edges}

    if config.LLM_ENABLED and cands:
        # LLM is the gatekeeper: it rejects cosine false-positives (pages that
        # only share vocabulary) and names *why* the rest are related.
        verdicts = _judge_crossref(state.get("normalized_md") or "", cands)
        for cand in cands:
            tgt = cand["page_slug"]
            v = verdicts.get(tgt)
            if not v or not v.get("related"):
                continue
            dist = cand.get("distance")
            conf = v.get("confidence")
            confidence = conf if conf in ("high", "medium", "low") \
                else _distance_confidence(dist)
            rel = v.get("relation")
            etype = rel if rel in CROSSREF_EDGE_TYPES else "relates_to"
            edges.append({"from": page, "to": tgt, "type": etype,
                          "confidence": confidence,
                          "evidence": _relates_evidence(cand, v.get("rationale"))})
            linked.add((page, tgt))
    else:
        # offline: no LLM to judge, so gate on cosine distance instead. Without
        # a gate the top-k search links every page to every other one.
        for cand in cands:
            tgt = cand["page_slug"]
            dist = cand.get("distance")
            if dist is not None and dist > config.RELATES_MAX_DISTANCE:
                continue
            edges.append({"from": page, "to": tgt, "type": "relates_to",
                          "confidence": _distance_confidence(dist),
                          "evidence": _relates_evidence(cand)})
            linked.add((page, tgt))

    for e in edges:
        try:
            wiki_engine.add_edge(e["from"], e["to"], e["type"],
                                 confidence=e.get("confidence", "medium"),
                                 evidence=e.get("evidence"))
        except ValueError:
            pass

    # 본문의 '## N. 연관 도메인/서브도메인/관계' 섹션을 edges.jsonl 기반으로 자동
    # 갱신. 마커(CROSSREF_AUTO_*) 안만 다시 쓰고 바깥 본문은 그대로 보존. 본문이
    # 정말 변할 때만 write_page를 호출해 frontmatter.updated가 무의미하게 갱신
    # 되는 것을 피한다. 도메인 분해의 부모 run처럼 page_slug 가 없으면 스킵.
    if page:
        page_obj = wiki_engine.read_page(page)
        if page_obj:
            body = page_obj["body"]
            section = _render_crossref_section(page, _next_section_num(body))
            new_body = _inject_crossref_section(body, section)
            if new_body != body:
                wiki_engine.write_page(page, page_obj["frontmatter"], new_body)
    return {"edges": edges}


def _judge_crossref(text: str, candidates: list[dict]) -> dict:
    """LLM decides, for each cosine candidate, whether it is genuinely related to
    the new document, what *kind* of relationship it is, and *why*. Returns
    {page_slug: {related, relation, confidence, rationale}}; empty on parse
    failure so the caller keeps the cosine fallback.
    """
    cand_list = "\n".join(
        f"{i}. [[{c['page_slug']}]]: {c['text'][:400]}"
        for i, c in enumerate(candidates))
    system = (
        "You build a software-project knowledge graph by linking a NEW document "
        "to EXISTING wiki pages a reader would meaningfully benefit from. Mark "
        "related=false for pages that merely share vocabulary but address a "
        "different feature.\n"
        "\n"
        "Pick the directed `relation` FROM the NEW document TO the candidate:\n"
        '  "implements" — the NEW doc implements/realizes the candidate (design → requirement)\n'
        '  "verifies"   — the NEW doc tests/validates the candidate (test → design or requirement)\n'
        '  "refines"    — the NEW doc elaborates/refines the candidate within the same phase\n'
        '  "relates_to" — generically related; none of the above fits\n'
        "\n"
        "For each RELATED page, fill `rationale` IN KOREAN with concrete content "
        "grounded in the actual texts (no vague phrasing like '관련이 있음'):\n"
        '  summary : 한 줄(15-35자) — 무엇이 어떻게 연결되는지 핵심.\n'
        '  why     : 2-4문장. 공유 주제·인접 단계·인터페이스/데이터 흐름·전제/결과 등\n'
        "            구체적 연결 사유. 추상적 어휘 금지.\n"
        '  anchors : [{"side":"new"|"existing","quote":"해당 문서의 핵심 문장·섹션을 짧게 인용"}]\n'
        "            new·existing 각 1-2개씩, 어느 부분이 연결되는지 가리킬 것.\n"
        '  shared  : ["공유 핵심 개념", ...]  3-6개 명사구 (예: "PG 연동", "결제 응답 코드").\n'
        '  usage   : 한 줄(20-50자) — 두 문서를 함께 봐야 하는 구체 상황 가이드.\n'
        "\n"
        'Return JSON: {"links":[{"page_slug":string, "related":bool, '
        '"relation":"implements"|"verifies"|"refines"|"relates_to", '
        '"confidence":"high"|"medium"|"low", '
        '"rationale":{"summary":string,"why":string,'
        '"anchors":[{"side":"new"|"existing","quote":string}],'
        '"shared":[string],"usage":string}}]}.')
    prompt = f"NEW document:\n{text[:3500]}\n\nCandidates:\n{cand_list}"
    try:
        data = json.loads(llm.chat(prompt, system=system, json_mode=True))
        out: dict = {}
        for item in data.get("links") or []:
            slug = item.get("page_slug")
            if not slug:
                continue
            # backward-tolerant: accept either the new dict shape or the legacy
            # single-string rationale and normalize to a dict downstream.
            rat = item.get("rationale")
            if isinstance(rat, str):
                rat = {"summary": rat.strip()} if rat.strip() else {}
            elif not isinstance(rat, dict):
                rat = {}
            out[slug] = {"related": bool(item.get("related")),
                         "relation": item.get("relation"),
                         "confidence": item.get("confidence"),
                         "rationale": rat}
        return out
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
        return {}


def _distance_confidence(dist: float | None) -> str:
    """Bucket a cosine distance into the edge-confidence labels the UI shows."""
    if dist is None:
        return "medium"
    if dist <= 0.35:
        return "high"
    if dist <= 0.5:
        return "medium"
    return "low"


# ── '연관 도메인/서브도메인/관계' 자동 섹션 렌더 ─────────────────────────────
def _next_section_num(body: str) -> int:
    """현재 본문의 마지막 '## N.' 헤딩 번호 + 1을 반환. 자동 섹션과 작성자가 박은
    레거시 "## N. 연관 …" 섹션은 셈에서 제외해, 자동 표가 8번 자리에서 9번으로
    밀려나지 않게 한다(레거시 섹션은 곧 자동 표로 치환되므로 자리를 비워 둔다).
    """
    cleaned = _CROSSREF_AUTO_RE.sub("", body)
    cleaned = _LEGACY_RELATED_SECTION_RE.sub("", cleaned)
    nums = [int(m.group(1)) for m in re.finditer(r"^##\s+(\d+)\.", cleaned, re.MULTILINE)]
    return (max(nums) + 1) if nums else 1


def _cell(s: str, limit: int) -> str:
    """마크다운 표 셀에 들어가도 안전하게: 줄바꿈/파이프 escape + 길이 cap."""
    s = (s or "").replace("|", "\\|").replace("\n", " ").strip()
    return (s[:limit] + "…") if len(s) > limit else s


def _render_crossref_section(page_slug: str, num: int) -> str:
    """이 페이지(page_slug)에서 *나가는* 모든 엣지를 도메인/서브도메인/관계 표로
    렌더링한다. evidence 가 dict(신규 구조화)면 summary+usage 사용, 문자열(레거시)
    이면 그 자체를 사유로 노출. merged_from 은 provenance라 제외(EDGE_TYPE_KO 미포함)."""
    rows: list[str] = []
    seen: set = set()
    for e in wiki_engine.get_edges():
        if e.get("from") != page_slug:
            continue
        tgt, etype = e.get("to"), e.get("type")
        if not tgt or tgt == page_slug or etype not in EDGE_TYPE_KO:
            continue
        key = (tgt, etype)
        if key in seen:
            continue
        seen.add(key)
        page = wiki_engine.read_page(tgt)
        fm = (page or {}).get("frontmatter") or {}
        domain = (fm.get("domain") or "").strip() or "—"
        subdomain = (fm.get("subdomain") or "").strip() or "—"
        rel = EDGE_TYPE_KO.get(etype, "연관")
        ev = e.get("evidence")
        reason, usage = "", ""
        if isinstance(ev, dict):
            reason = (ev.get("summary") or ev.get("why") or "").strip()
            usage = (ev.get("usage") or "").strip()
        elif isinstance(ev, str):
            reason = ev.strip()
        rows.append(
            f"| {_cell(domain, 30)} | {_cell(subdomain, 40)} [[{tgt}]] "
            f"| {rel} | {_cell(reason, 220) or '—'} | {_cell(usage, 120) or '—'} |")
    if not rows:
        return ""
    return (
        f"## {num}. 연관 도메인 / 서브도메인 / 관계\n\n"
        "_이 표는 상호참조 Agent가 자동으로 유지합니다 — 직접 편집한 내용은 다음 적재 시 덮어쓰여집니다._\n\n"
        "| 도메인 | 서브도메인 (페이지) | 관계 | 핵심 사유 | 함께 볼 때 |\n"
        "|---|---|---|---|---|\n"
        + "\n".join(rows) + "\n"
    )


def _inject_crossref_section(body: str, section_md: str) -> str:
    """본문 안의 자동 관리 블록(마커 사이)을 갱신/삽입한다.

    소스 마크다운에 작성자가 직접 박아 둔 "## N. 연관 (서브)도메인/도메인/기능 …"
    섹션은 자동 표와 의미가 겹쳐 페이지에 두 표가 따로 떠 있는 노이즈가 된다.
    그래서 (1) 마커 블록을 제거하고 (2) 레거시 연관 섹션을 제거한 뒤 (3) 자동
    블록을 본문 끝에 한 번만 붙인다. 마커 바깥의 *다른* 섹션은 그대로 보존된다.
    """
    # (1) 기존 자동 블록 먼저 제거 — 안쪽 헤딩이 레거시 패턴과 겹칠 수 있으므로 선행.
    body = _CROSSREF_AUTO_RE.sub("", body)
    # (2) 작성자가 박은 레거시 "## N. 연관 …" 섹션 흡수.
    body = _LEGACY_RELATED_SECTION_RE.sub("", body)
    # (3) 이전 자동 블록 앞에 붙여 뒀던 '---' 구분선이 본문 끝에 남으면 누적되므로 정리.
    body = re.sub(r"\n+---\s*$", "", body.rstrip()).rstrip()
    if not section_md:
        # 자동 표를 만들 거리가 없으면(엣지 0건/임계값 미만) 본문만 깨끗이 유지.
        return body + "\n"
    block = f"{CROSSREF_AUTO_START}\n{section_md.rstrip()}\n{CROSSREF_AUTO_END}"
    sep = "\n\n---\n\n" if body else ""
    return body + sep + block + "\n"


def _relates_evidence(cand: dict, rationale=None) -> dict:
    """Structured 근거 for a relates_to edge — surfaced section-by-section in
    the graph's edge-detail panel. Returns a JSON-serializable dict.

    The LLM rationale (dict from `_judge_crossref`) leads; cosine signals are
    appended as a supplementary signal. Offline / candidate-only paths still
    produce a dict (just lacking the LLM-written fields) so the UI's renderer
    sees one consistent shape. Legacy string evidence in old `edges.jsonl`
    rows remains valid — the frontend handles both.
    """
    dist = cand.get("distance")
    sim = round(max(0.0, 1.0 - dist), 3) if isinstance(dist, (int, float)) else None
    out: dict = {
        "similarity": sim,
        "distance": round(dist, 3) if isinstance(dist, (int, float)) else None,
    }
    snippet = " ".join((cand.get("text") or "").split())[:140]
    if snippet:
        out["snippet"] = snippet
    if isinstance(rationale, dict) and rationale:
        for k in ("summary", "why", "usage"):
            v = (rationale.get(k) or "").strip()
            if v:
                out[k] = v
        anchors = [a for a in (rationale.get("anchors") or [])
                   if isinstance(a, dict) and (a.get("quote") or "").strip()]
        if anchors:
            out["anchors"] = [{"side": a.get("side") or "",
                               "quote": str(a.get("quote", "")).strip()[:280]}
                              for a in anchors[:4]]
        shared = [str(s).strip() for s in (rationale.get("shared") or []) if str(s).strip()]
        if shared:
            out["shared"] = shared[:8]
    elif isinstance(rationale, str) and rationale.strip():
        out["summary"] = rationale.strip()
    return out


def index(state: IngestState) -> dict:
    wiki_engine.rebuild_index()
    return {}


def log(state: IngestState) -> dict:
    action = (state.get("merge_decision") or {}).get("action", "create")
    relation = (state.get("conflict_report") or {}).get("relation", "")
    rel = f" relation={relation}" if relation and relation != "none" else ""
    wiki_engine.append_log("ingest", state.get("title") or state["slug"],
                           f"action={action}{rel} page=[[{state.get('page_slug')}]]")
    return {}


# ── Helpers ────────────────────────────────────────────────────────────────
def _page_taxonomy_key(slug: str) -> tuple[str, str, str]:
    """(domain, subdomain, sdlc_phase) of an existing wiki page from its
    frontmatter, used by the similarity merge guards. '' for any missing part."""
    pg = wiki_engine.read_page(slug)
    fm = (pg or {}).get("frontmatter") or {}
    return ((fm.get("domain") or "").strip(),
            (fm.get("subdomain") or "").strip(),
            (fm.get("sdlc_phase") or "").strip())


def _classify_phase(text: str, title: str = "") -> str:
    # 1) Authoritative: an explicit stage word in the title wins outright.
    low_title = title.lower()
    for phase, markers in _PHASE_TITLE_MARKERS.items():
        if any(m.lower() in low_title for m in markers):
            return phase
    # 2) Fallback (title gives no stage): body keyword-frequency vote.
    low = text.lower()
    best, score = "requirements", 0
    for phase, kws in _PHASE_KEYWORDS.items():
        s = sum(low.count(k.lower()) for k in kws)
        if s > score:
            best, score = phase, s
    return best


def _judge_decompose(text: str, taxonomy: list[dict], pages: list[dict]) -> list[dict]:
    """LLM splits a doc into domain > sub-domain units, classifying against the
    confirmed domain_map taxonomy (so units align with the numbered folders).
    Returns [{domain, subdomain, title, body, target_slug}]. A cohesive
    single-topic doc returns one unit; offline / parse failure also return a
    single whole-doc unit (current one-page behaviour)."""
    from app import config
    whole = [{"domain": None, "subdomain": None, "title": "", "body": text,
              "target_slug": None}]
    if not config.LLM_ENABLED or not text.strip():
        return whole

    tax = "\n".join(f"- {d['name']}: {', '.join(d.get('subdomains') or [])}"
                    for d in taxonomy) or "(없음)"
    cat = "\n".join(
        f"- {p['title']} (slug={p['slug']}, domain={p.get('domain') or '—'}, "
        f"subdomain={p.get('subdomain') or '—'})"
        for p in pages) or "(아직 페이지 없음)"
    system = (
        "You organize software-project documents into a two-level wiki: "
        "DOMAIN (business area: 고객/주문/상품/대시보드/직원/부서 …) > SUB-DOMAIN "
        "(one coherent topic / page). Return JSON: {\"units\":[{\"domain\":string, "
        "\"subdomain\":string, \"title\":string, \"body\":string, "
        "\"target_slug\":string|null}]}.\n"
        "DECISION — first identify how many DOMAINS the document covers:\n"
        "• ONE domain → return EXACTLY ONE unit (the whole document), no matter how "
        "many requirements / CRUD operations / sections / tables / rules it lists. "
        "Those are the CONTENT of one page, not separate units. (e.g. '상품 관리 "
        "요구사항' with 상품 등록/조회/수정/삭제/재고 → 1 unit: domain=상품, subdomain=상품 관리.)\n"
        "• MULTIPLE domains → SPLIT: emit one unit per (domain, sub-domain). The "
        "document is a bundle/collection covering different domains (e.g. '추가 "
        "요구사항 모음' mixing 대시보드 위젯 + 고객 검색 + 상품 통계 + 고객 변경 이력). Within the "
        "same domain, keep clearly-distinct topics as separate units (고객 검색 and "
        "고객 변경 이력 → two units, both domain=고객).\n"
        "Rules: cover all substantive content, never drop or invent; `title` = the "
        "sub-domain name; `body` = clean Korean markdown with its own H1.\n"
        "CLASSIFY each unit's `domain`/`subdomain` using this confirmed taxonomy — "
        "reuse the EXACT names when the unit fits one; only when nothing fits, give "
        "a concise new name:\n"
        f"{tax}\n"
        "Set `target_slug` to an EXISTING page slug below when the unit clearly "
        "continues it, else null:\n"
        f"{cat}")
    try:
        data = json.loads(llm.chat(text[:6000], system=system, json_mode=True))
        units = []
        for u in (data.get("units") or []):
            body = (u.get("body") or "").strip()
            if not body:
                continue
            units.append({"domain": (u.get("domain") or "").strip() or None,
                          "subdomain": (u.get("subdomain") or "").strip() or None,
                          "title": (u.get("title") or "").strip(),
                          "body": body,
                          "target_slug": (u.get("target_slug") or None)})
        return units[:12] if units else whole
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
        return whole


def _judge_similarity(text: str, candidates: list[dict]) -> dict:
    from app import config
    cand_list = "\n".join(
        f"{i}. [[{c['page_slug']}]] (distance={c['distance']:.3f}): {c['text'][:200]}"
        for i, c in enumerate(candidates))
    if not config.LLM_ENABLED:
        # offline: treat very-close vector match as duplicate
        top = candidates[0]
        if top["distance"] < 0.25:
            return {"action": "merge", "target_slug": top["page_slug"],
                    "reason": f"vector distance {top['distance']:.3f} < 0.25 (offline)"}
        return {"action": "create", "reason": "no close vector match (offline)"}

    system = (
        "You decide whether a NEW software-wiki document should be MERGED into an "
        "EXISTING page or kept as its OWN new page.\n"
        "Merge ONLY when the new document is about the SAME sub-feature/topic as a "
        "candidate — i.e. they would legitimately be the SAME wiki page: a newer "
        "version, a near-duplicate, or a direct elaboration of that exact feature.\n"
        "Do NOT merge merely because they share the same domain area (예: 둘 다 "
        "고객 관리), the same SDLC artifact type (둘 다 요구사항), or the same section "
        "template / vocabulary. Different sub-features — e.g. 고객 검색 vs 공통 응답 "
        "vs 예외 처리 vs SKU 식별 — are SEPARATE pages → action=create.\n"
        "When you DO merge, target_slug MUST be one of the candidate page slugs "
        "listed below — never invent a slug and never echo the new document's own "
        "slug.\n"
        "Return JSON: {\"action\":\"merge\"|\"create\", \"target_slug\":string|null, "
        "\"reason\":string}.")
    prompt = f"New document:\n{text}\n\nCandidates:\n{cand_list}"
    valid_targets = {c["page_slug"] for c in candidates}
    try:
        data = json.loads(llm.chat(prompt, system=system, json_mode=True,
                                   temperature=0))
        if (data.get("action") == "merge"
                and data.get("target_slug") in valid_targets):
            return data
    except (json.JSONDecodeError, KeyError):
        pass
    return {"action": "create", "reason": "LLM judged distinct"}


def _judge_conflict(existing: str, incoming: str) -> dict:
    """Classify the incoming doc vs an existing page at the semantic level."""
    from app import config
    if not config.LLM_ENABLED:
        # offline heuristic: how much of the incoming content is genuinely new
        ex_lines = {ln.strip() for ln in existing.splitlines() if ln.strip()}
        in_lines = [ln.strip() for ln in incoming.splitlines() if ln.strip()]
        new = [ln for ln in in_lines if ln not in ex_lines]
        relation = "duplicate" if not new else "augmentation"
        return {"relation": relation, "conflicts": [],
                "summary": f"offline 휴리스틱: 신규 {len(new)}/{len(in_lines) or 1} 라인"}

    system = (
        "You compare an INCOMING document against an EXISTING wiki page and judge "
        "their semantic relationship. Classify `relation` as exactly one of: "
        '"contradiction" (states facts that conflict with the existing page), '
        '"augmentation" (adds new information without conflicting), or '
        '"duplicate" (substantially the same content). List each concrete '
        "contradiction as a short Korean string in `conflicts` (empty list if "
        'none). Return JSON: {"relation":..., "conflicts":[...], "summary":...}.')
    prompt = f"EXISTING:\n{existing[:4000]}\n\nINCOMING:\n{incoming[:4000]}"
    try:
        data = json.loads(llm.chat(prompt, system=system, json_mode=True))
        relation = data.get("relation")
        if relation not in ("contradiction", "augmentation", "duplicate"):
            relation = "augmentation"
        conflicts = data.get("conflicts") or []
        return {"relation": relation,
                "conflicts": [str(c) for c in conflicts],
                "summary": str(data.get("summary", ""))}
    except (json.JSONDecodeError, KeyError, TypeError):
        return {"relation": "augmentation", "conflicts": [],
                "summary": "LLM 응답 파싱 실패 — 보강으로 처리"}


def _merge_bodies(before: str, incoming: str) -> tuple[str, list[str]]:
    """Merge an incoming doc into an existing page, *resolving* any conflicts.

    Mirrors resolvers._reconcile: the LLM keeps one coherent page and, where the
    two sources disagree, picks the more recent / authoritative value (dropping
    the stale one) with a short '> ℹ️ 변경:' note — it never leaves both sides
    marked as an unresolved conflict. Returns (merged_body, change_notes).
    """
    from app import config
    if not config.LLM_ENABLED:
        marker = "\n\n> ℹ️ 병합: 아래는 추가 출처의 내용입니다.\n\n"
        return before + marker + incoming, []

    system = ("Merge the INCOMING document into the EXISTING wiki page as ONE "
              "coherent Korean markdown page. When the two sources state "
              "CONFLICTING facts, RESOLVE the conflict by keeping the more recent "
              "/ authoritative value and dropping the stale one; add a short "
              "'> ℹ️ 변경: ...' note explaining what changed. Never keep both "
              "conflicting values side by side, and never invent facts. "
              "PRESERVE verbatim any HTML comment markers like "
              "'<!-- crossref:auto -->' / '<!-- /crossref:auto -->' and the "
              "content between them — they are auto-managed elsewhere. "
              "Return only the merged markdown.")
    merged = llm.chat(f"EXISTING:\n{before}\n\nINCOMING:\n{incoming}", system=system)
    changes = re.findall(r"> ℹ️ 변경:.*", merged)
    return merged or before, changes


def _check_omissions(before: str, incoming: str, merged: str) -> dict:
    """Did the merged page keep the info from both sources? Returns
    {coverage 0..1, omissions: list[str], summary}."""
    from app import config
    if not config.LLM_ENABLED:
        # offline heuristic: substantial source lines absent from the merged text
        src = [ln.strip() for ln in (before + "\n" + incoming).splitlines()
               if len(ln.strip()) > 12]
        missing = [ln for ln in src if ln not in merged][:5]
        coverage = round(1 - len(missing) / max(len(src), 1), 2)
        return {"coverage": coverage, "omissions": missing,
                "summary": f"offline 휴리스틱: 누락 후보 {len(missing)}건"}

    system = (
        "You verify that a MERGED wiki page preserved the information from its two "
        "SOURCES (EXISTING + INCOMING). List every concrete fact, requirement, or "
        "section that is present in either source but MISSING from the merged page "
        "as short Korean strings in `omissions` (empty list if nothing is missing). "
        "`coverage` is the fraction 0..1 of source information retained. Ignore "
        "intentionally superseded values. Return JSON: "
        '{"coverage": <0..1>, "omissions": [...], "summary": "<Korean>"}.')
    prompt = (f"EXISTING:\n{before[:3500]}\n\nINCOMING:\n{incoming[:3500]}\n\n"
              f"MERGED:\n{merged[:5000]}")
    try:
        data = json.loads(llm.chat(prompt, system=system, json_mode=True))
        omissions = [str(o) for o in (data.get("omissions") or [])]
        coverage = float(data.get("coverage", 1.0))
        return {"coverage": max(0.0, min(1.0, coverage)), "omissions": omissions,
                "summary": str(data.get("summary", ""))}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {"coverage": 1.0, "omissions": [],
                "summary": "누락검토 응답 파싱 실패 — 통과 처리"}


def _remerge_with_omissions(before: str, incoming: str, merged: str,
                            omissions: list[str]) -> str:
    """Patch the merged page so it includes the items the check found missing."""
    from app import config
    miss = "\n".join(f"- {o}" for o in omissions)
    if not config.LLM_ENABLED:
        return merged + "\n\n> ℹ️ 누락 보완\n\n" + miss
    system = ("Add the MISSING items into the MERGED markdown page without removing "
              "any existing content. Keep it one coherent Korean wiki page, place "
              "each item in the most relevant section. Return only the merged markdown.")
    prompt = f"MERGED:\n{merged}\n\nMISSING ITEMS (must all be present):\n{miss}"
    out = llm.chat(prompt, system=system)
    return out or (merged + "\n\n" + miss)
