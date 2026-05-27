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

# How a document judged to *contradict* an existing page is resolved. The
# global default; an ingest request may override it per source.
#   manual          — keep both pages, link with `conflicts_with`, leave the
#                     merge record `pending` for a human to accept/revert.
#   prefer_incoming — the newer doc wins: it becomes an active page, the older
#                     one is marked `superseded` and linked via `supersedes`.
#   prefer_existing — the existing page wins: the incoming doc is parked as a
#                     `rejected` page, linked with `conflicts_with`.
CONFLICT_POLICIES = ("manual", "prefer_incoming", "prefer_existing")
CONFLICT_POLICY = os.environ.get("CONFLICT_POLICY", "manual").strip().lower()
if CONFLICT_POLICY not in CONFLICT_POLICIES:
    CONFLICT_POLICY = "manual"


def ensure_dirs() -> None:
    for d in (RAW_DIR, WIKI_DIR, GRAPH_DIR, CHROMA_DIR):
        d.mkdir(parents=True, exist_ok=True)
