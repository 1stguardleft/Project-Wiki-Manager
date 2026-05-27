"""Pipeline node implementations (requirements §4.1, §5.4).

Each node is a plain function taking IngestState and returning a partial update.
Event emission and timing are handled by the graph wrapper (graph.py), so node
bodies stay focused on their single responsibility.  All nodes work offline
(no OPENAI_API_KEY) via services.llm fallbacks.
"""
from __future__ import annotations

import json
import re

from app.agents import merge_store
from app.agents.state import IngestState
from app.schema import loader
from app.services import (chunking, llm, parser, vectordb, wiki_engine)

# Node registry: (id, label) in pipeline order. graph.py wires the edges.
NODE_SPECS = [
    ("fetch", "수집"), ("parse", "파싱"), ("normalize", "정규화"),
    ("chunk", "청킹"), ("embed", "임베딩"), ("similarity", "유사도"),
    ("conflict", "충돌판정"), ("merge", "병합"),
    ("crossref", "상호참조"), ("index", "인덱싱"), ("log", "로깅"),
]

_PHASE_KEYWORDS = {
    "requirements": ["요구사항", "유스케이스", "requirement", "scope", "범위"],
    "design": ["설계", "아키텍처", "architecture", "design", "api", "db", "화면"],
    "implementation": ["구현", "코드", "implementation", "convention", "컨벤션", "guide"],
    "test": ["테스트", "test", "qa", "케이스", "검증"],
    "deployment": ["배포", "deploy", "release", "릴리스", "환경"],
    "operation": ["운영", "operation", "모니터링", "트러블", "monitor"],
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
              "Return only markdown.")
    normalized = llm.chat(text[:8000], system=system) or text
    phase = _classify_phase(title + "\n" + normalized)
    slug = loader.slugify(title)
    return {"normalized_md": normalized, "sdlc_phase": phase, "slug": slug}


def chunk(state: IngestState) -> dict:
    chunks = chunking.chunk_markdown(
        state.get("normalized_md") or "", state["slug"], state.get("sdlc_phase"))
    return {"chunks": chunks}


def embed(state: IngestState) -> dict:
    ids = vectordb.upsert_chunks(state.get("chunks") or [])
    return {"vector_ids": ids}


def similarity(state: IngestState) -> dict:
    """Vector candidates -> LLM judgment of duplicate/similar (FR-SIM)."""
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

    # A pre-existing page with the same slug is a strong duplicate — merge to
    # avoid silently overwriting it.
    if wiki_engine.find_page_path(slug):
        decision = {"action": "merge", "target_slug": slug,
                    "reason": "동일 slug 기존 페이지 존재"}
    elif cands:
        decision = _judge_similarity(text, cands)
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

            # A contradiction is resolved by the configured policy (a per-source
            # override falls back to the global default). A same-slug collision
            # can't coexist as two pages, so it always merges instead.
            if relation == "contradiction" and slug != target:
                policy = (state["source"].get("conflict_policy")
                          or config.CONFLICT_POLICY)
                return _resolve_contradiction(
                    policy, slug, target, title, phase, body, before,
                    existing, report, report_conflicts, sources)

            merged_body, marker_conflicts = _merge_bodies(before, body)
            # The conflict node's semantic judgment is authoritative; the merge
            # prompt's inline `⚠️ CONFLICT:` markers are a fallback.
            conflicts = report_conflicts or marker_conflicts
            fm = dict(existing["frontmatter"])
            fm["source_count"] = fm.get("source_count", 1) + 1
            fm["sources"] = list(dict.fromkeys((fm.get("sources") or []) + sources))
            wiki_engine.write_page(target, fm, merged_body)
            mid = merge_store.create(target, before, merged_body, conflicts,
                                     sources, relation=relation)
            return {"page_slug": target, "merge_id": mid,
                    "edges": [{"from": target, "to": slug, "type": "merged_from"}]}

    # create new page
    fm = {"title": title, "slug": slug, "type": "deliverable",
          "sdlc_phase": phase, "status": "active",
          "source_count": 1, "sources": sources}
    wiki_engine.write_page(slug, fm, body)
    return {"page_slug": slug, "edges": []}


def crossref(state: IngestState) -> dict:
    edges = state.get("edges") or []
    page = state.get("page_slug")
    # don't add a generic relates_to where a stronger edge (merged_from,
    # conflicts_with) already connects the same pair
    linked = {(e["from"], e["to"]) for e in edges}
    linked |= {(e["to"], e["from"]) for e in edges}
    # record remaining similar pages as relates_to edges
    for cand in state.get("similar_candidates") or []:
        tgt = cand["page_slug"]
        if tgt != page and (page, tgt) not in linked:
            edges.append({"from": page, "to": tgt, "type": "relates_to"})
    for e in edges:
        try:
            wiki_engine.add_edge(e["from"], e["to"], e["type"],
                                 confidence="medium", evidence=e.get("evidence"))
        except ValueError:
            pass
    return {"edges": edges}


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
def _classify_phase(text: str) -> str:
    low = text.lower()
    best, score = "requirements", 0
    for phase, kws in _PHASE_KEYWORDS.items():
        s = sum(low.count(k.lower()) for k in kws)
        if s > score:
            best, score = phase, s
    return best


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

    system = ("Decide whether the new document duplicates/strongly overlaps an "
              "existing wiki page. Return JSON: {\"action\":\"merge\"|\"create\", "
              "\"target_slug\":string|null, \"reason\":string}.")
    prompt = f"New document:\n{text}\n\nCandidates:\n{cand_list}"
    try:
        data = json.loads(llm.chat(prompt, system=system, json_mode=True))
        if data.get("action") == "merge" and data.get("target_slug"):
            return data
    except (json.JSONDecodeError, KeyError):
        pass
    return {"action": "create", "reason": "LLM judged distinct"}


def _resolve_contradiction(policy: str, slug: str, target: str, title: str,
                           phase, body: str, before: str, existing: dict,
                           report: dict, conflicts: list[str],
                           sources: list[str]) -> dict:
    """Apply the conflict-resolution policy to a judged contradiction.

    All policies keep an auditable merge record (before=existing, after=incoming)
    so the diff view shows both versions; they differ in which page stays
    authoritative and the edge/status that records the decision.
    """
    evidence = report.get("summary") or "; ".join(conflicts)

    def _new_page(status: str) -> None:
        wiki_engine.write_page(slug, {
            "title": title, "slug": slug, "type": "deliverable",
            "sdlc_phase": phase, "status": status,
            "source_count": 1, "sources": sources}, body)

    def _record(status: str) -> str:
        return merge_store.create(target, before, body, conflicts, sources,
                                  relation="contradiction", policy=policy,
                                  status=status)

    if policy == "prefer_incoming":
        # newer doc wins; the existing page is demoted to `superseded`
        _new_page("active")
        fm = dict(existing["frontmatter"])
        fm["status"] = "superseded"
        wiki_engine.write_page(target, fm, before)
        mid = _record("accepted")
        return {"page_slug": slug, "merge_id": mid,
                "edges": [{"from": slug, "to": target, "type": "supersedes",
                           "evidence": evidence}]}

    if policy == "prefer_existing":
        # existing page wins; the incoming doc is parked as a `rejected` page
        _new_page("rejected")
        mid = _record("rejected")
        return {"page_slug": slug, "merge_id": mid,
                "edges": [{"from": slug, "to": target, "type": "conflicts_with",
                           "evidence": evidence}]}

    # manual (default): keep both, leave the decision to a human
    _new_page("active")
    mid = _record("pending")
    return {"page_slug": slug, "merge_id": mid,
            "edges": [{"from": slug, "to": target, "type": "conflicts_with",
                       "evidence": evidence}]}


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
    from app import config
    if not config.LLM_ENABLED:
        marker = "\n\n> ⚠️ 병합된 추가 출처 내용 (충돌 가능, 검토 필요)\n\n"
        return before + marker + incoming, ["offline merge: appended incoming content"]

    system = ("Merge the incoming document into the existing wiki page. Keep one "
              "coherent markdown page. Where they conflict, keep both and mark with "
              "a '> ⚠️ CONFLICT:' blockquote. Return only the merged markdown.")
    merged = llm.chat(f"EXISTING:\n{before}\n\nINCOMING:\n{incoming}", system=system)
    conflicts = re.findall(r"> ⚠️ CONFLICT:.*", merged)
    return merged or before, conflicts
