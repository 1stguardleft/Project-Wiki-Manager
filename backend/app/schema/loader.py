"""Data-driven schema access (adapted from OmegaWiki's runtime/loader.py, MIT).

Reads the YAML schema files once at import time and exposes the entity/edge/
convention definitions plus a few helpers.  Adding a field or edge type is a
YAML-only change — no code edits here.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from app.config import SCHEMA_DIR


def _load(name: str) -> dict:
    return yaml.safe_load((SCHEMA_DIR / name).read_text(encoding="utf-8"))


ENTITIES = _load("entities.yaml")
EDGES = _load("edges.yaml")
CONVENTIONS = _load("conventions.yaml")

# ── Derived ──────────────────────────────────────────────────────────────
SDLC_PHASES: dict[str, str] = CONVENTIONS["sdlc_phases"]          # phase -> dir
ENTITIES_DIR: str = CONVENTIONS["entities_dir"]
VALID_EDGE_TYPES = set(EDGES["edge_types"].keys())
SYMMETRIC_EDGE_TYPES = {t for t, s in EDGES["edge_types"].items() if s.get("symmetric")}
PHASE_ORDER = list(SDLC_PHASES.keys())

_SLUG_RE = re.compile(CONVENTIONS["slug_pattern"])
_STOP = set(CONVENTIONS.get("stop_words", []))
_MAX_WORDS = CONVENTIONS.get("slug_max_words", 6)
WIKILINK_RE = re.compile(CONVENTIONS["wikilink_pattern"])


def is_valid_slug(slug: str) -> bool:
    return bool(_SLUG_RE.match(slug))


def slugify(title: str) -> str:
    """Title -> lowercase hyphenated slug, stop words removed, max N words."""
    tokens = re.findall(r"[a-z0-9가-힣]+", title.lower())
    kept = [t for t in tokens if t not in _STOP] or tokens
    return "-".join(kept[:_MAX_WORDS]) or "untitled"


def phase_dir(phase: str) -> str:
    """SDLC phase -> wiki subdirectory; entities map to the entities dir."""
    if phase in SDLC_PHASES:
        return SDLC_PHASES[phase]
    return ENTITIES_DIR


def fields_for(page_type: str) -> dict:
    return ENTITIES.get(page_type, ENTITIES["deliverable"])["fields"]


def required_fields(page_type: str) -> list[str]:
    return [f for f, spec in fields_for(page_type).items() if spec.get("required")]
