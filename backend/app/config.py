"""Central configuration and filesystem paths.

Resolves the repository layout (raw/, wiki/) and OpenAI settings from the
environment.  Everything degrades gracefully when OPENAI_API_KEY is absent so
the pipeline and its live visualization still run in a demo/offline mode.
"""
from __future__ import annotations

import os
from pathlib import Path

# Repo root = parent of backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


def _load_dotenv() -> None:
    """Minimal .env loader (no extra dependency).

    Reads backend/.env then repo-root/.env; existing os.environ wins so an
    explicitly exported var always overrides the file.  Lines: KEY=VALUE,
    '#' comments and blank lines ignored; surrounding quotes stripped.
    """
    for env_path in (BACKEND_DIR / ".env", REPO_ROOT / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


_load_dotenv()

RAW_DIR = REPO_ROOT / "raw"
WIKI_DIR = REPO_ROOT / "wiki"

# Root directory browsed by the ingest file picker. Relative paths resolve
# under the repo root; an absolute SOURCES_DIR is used as-is.
_sources = os.environ.get("SOURCES_DIR", "demo")
SOURCES_DIR = Path(_sources) if os.path.isabs(_sources) else REPO_ROOT / _sources
GRAPH_DIR = WIKI_DIR / "graph"
INDEX_FILE = WIKI_DIR / "index.md"
LOG_FILE = WIKI_DIR / "log.md"
EDGES_FILE = GRAPH_DIR / "edges.jsonl"
# Manifest of already-ingested source files (rel-path -> {page_slug, at}). Lives
# under GRAPH_DIR so a full graph/data reset clears it alongside the wiki.
INGESTED_FILE = GRAPH_DIR / "ingested.json"
# Persisted merge records (id -> before/after/conflicts/policy/status/coverage/...).
# Survives process restarts so the KPI page can aggregate coverage / auto-resolve
# ratios across sessions. Cleared by /api/wiki/reset together with the other
# graph artifacts.
MERGES_FILE = GRAPH_DIR / "merges.json"
CHROMA_DIR = REPO_ROOT / ".chroma"

SCHEMA_DIR = Path(__file__).resolve().parent / "schema"

# ── LLM provider ────────────────────────────────────────────────────────
# Standard OpenAI (OPENAI_BASE_URL optionally points at a proxy/gateway)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "").strip()

# Azure OpenAI gateway (e.g. SKAX AI TalentLab — see docs/azure-openapi-call.md).
# Kept on separate vars so it never collides with a shell OPENAI_API_KEY.
AZURE_OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview").strip()

# model / deployment names (Azure uses these as deployment names directly)
OPENAI_CHAT_MODEL = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENAI_EMBED_MODEL = os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-small")
EMBED_DIM = 1536

# Azure takes precedence when configured; then plain OpenAI; else offline fallback.
if AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT:
    LLM_PROVIDER = "azure"
elif OPENAI_API_KEY:
    LLM_PROVIDER = "openai"
else:
    LLM_PROVIDER = "offline"

# When offline, LLM/embedding calls use deterministic fallbacks.
LLM_ENABLED = LLM_PROVIDER != "offline"

# How a document judged to *contradict* an existing page is resolved. Each
# value names a resolver in app.agents.resolvers.REGISTRY, so the active
# behaviour is a one-line switch and adding a new one needs no pipeline edits.
# This is the global default; an ingest request may override it per source.
#   llm_merge       — (default) the LLM reconciles both into ONE page, keeping
#                     the more recent/authoritative claim with a change note;
#                     fully automatic (no human), recorded as `auto_resolved`.
#   manual          — keep both pages, link with `conflicts_with`, leave the
#                     merge record `pending` for a human to accept/revert.
#   prefer_incoming — the newer doc wins: it becomes an active page, the older
#                     one is marked `superseded` and linked via `supersedes`.
#   prefer_existing — the existing page wins: the incoming doc is parked as a
#                     `rejected` page, linked with `conflicts_with`.
CONFLICT_STRATEGIES = ("llm_merge", "manual", "prefer_incoming", "prefer_existing")
CONFLICT_STRATEGY = os.environ.get("CONFLICT_STRATEGY", "llm_merge").strip().lower()
if CONFLICT_STRATEGY not in CONFLICT_STRATEGIES:
    CONFLICT_STRATEGY = "llm_merge"

# Auto-apply the llm_merge result unless the model's self-reported confidence is
# below this. 0 = always auto-apply (never route to a human); raise it later to
# turn on a confidence-gated manual review without any code change.
try:
    CONFLICT_AUTO_THRESHOLD = float(os.environ.get("CONFLICT_AUTO_THRESHOLD", "0"))
except ValueError:
    CONFLICT_AUTO_THRESHOLD = 0.0

# Back-compat aliases (older callers / the health endpoint referenced these).
CONFLICT_POLICIES = CONFLICT_STRATEGIES
CONFLICT_POLICY = CONFLICT_STRATEGY

# Offline fallback gate for `relates_to` edges: when no LLM is available the
# crossref node can't *judge* relatedness, so it keeps a link only when the
# nearest matching chunk is within this cosine distance (Chroma uses
# distance = 1 - cosine_similarity, so 0 = identical, 0.6 ≈ cosine similarity
# 0.4). When the LLM is enabled it is the gatekeeper instead and this is unused.
try:
    RELATES_MAX_DISTANCE = float(os.environ.get("RELATES_MAX_DISTANCE", "0.6"))
except ValueError:
    RELATES_MAX_DISTANCE = 0.6

# Crossref Agent는 위키에 비교할 페이지가 거의 없을 때(초기 적재) LLM이 억지로
# 관계를 만들어내는 경향이 있어 노이즈가 잘 생긴다. 위키 전체 페이지 수가 이
# 임계값 미만이면 crossref 단계는 LLM 호출을 건너뛰고 자동 섹션을 비워둔다.
# 이후 `POST /api/wiki/rebuild-crossref` 로 누적된 코퍼스 기준으로 일괄 재생성.
try:
    MIN_PAGES_FOR_CROSSREF = int(os.environ.get("MIN_PAGES_FOR_CROSSREF", "5"))
except ValueError:
    MIN_PAGES_FOR_CROSSREF = 5

# Merge gate for the `similarity` node: a vector candidate is only offered to the
# merge judge when its cosine distance is within this bound. Template-shaped
# requirement/design docs share headings + vocabulary, so unrelated pages still
# land at ~0.4; a true duplicate / same-feature version sits well below this.
# Stricter than RELATES_MAX_DISTANCE because merging is destructive (it rewrites
# an existing page) whereas a relates_to edge is additive.
try:
    SIMILARITY_MAX_DISTANCE = float(os.environ.get("SIMILARITY_MAX_DISTANCE", "0.30"))
except ValueError:
    SIMILARITY_MAX_DISTANCE = 0.30

# Artificial per-node pause (seconds) so the live workflow view is watchable —
# the offline pipeline otherwise finishes in milliseconds. 0 disables it.
try:
    STEP_DELAY_SEC = float(os.environ.get("STEP_DELAY_SEC", "1.0"))
except ValueError:
    STEP_DELAY_SEC = 1.0


def ensure_dirs() -> None:
    for d in (RAW_DIR, WIKI_DIR, GRAPH_DIR, CHROMA_DIR):
        d.mkdir(parents=True, exist_ok=True)
