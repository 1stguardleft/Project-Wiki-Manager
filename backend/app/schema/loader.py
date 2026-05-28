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
DOMAIN_MAP = _load("domain_map.yaml")

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


# ── Numbered domain / sub-domain taxonomy (domain_map.yaml) ─────────────────
_PHASES = DOMAIN_MAP["phases"]
_DOMAINS = DOMAIN_MAP["domains"]
_FALLBACK = DOMAIN_MAP.get("fallback", {"domain_tens": 9, "subdomain_unit": 9})
# domain name -> {tens, subs: {subname: unit}}
_DOMAIN_BY_NAME = {
    d["name"]: {"tens": d["tens"],
                "subs": {s: i + 1 for i, s in enumerate(d.get("subdomains") or [])}}
    for d in _DOMAINS
}


def _san(name: str) -> str:
    """Folder-safe label: '/' is a path separator, collapse to a space."""
    return " ".join((name or "").replace("/", " ").split())


def phase_num(phase: str) -> int:
    p = _PHASES.get(phase)
    return p["num"] if p else 900


def resolve_domain(name: str | None) -> str | None:
    """Best-match a (possibly loose) domain name to a catalog domain, else None."""
    if not name:
        return None
    if name in _DOMAIN_BY_NAME:
        return name
    for canon in _DOMAIN_BY_NAME:
        if name in canon or canon in name:  # e.g. '고객' ↔ '고객 관리'
            return canon
    return None


def resolve_subdomain(domain_canon: str | None, name: str | None) -> str | None:
    if not domain_canon or not name:
        return name
    subs = _DOMAIN_BY_NAME.get(domain_canon, {}).get("subs", {})
    if name in subs:
        return name
    for canon in subs:
        if name in canon or canon in name:
            return canon
    return name


def domain_dir(phase: str, domain: str | None) -> str | None:
    """'130 고객 관리' style folder for (phase, domain). None if no domain."""
    if not domain:
        return None
    canon = resolve_domain(domain)
    tens = _DOMAIN_BY_NAME[canon]["tens"] if canon else _FALLBACK["domain_tens"]
    num = phase_num(phase) + tens * 10
    return f"{num} {_san(canon or domain)}"


def subdomain_dir(phase: str, domain: str | None, subdomain: str | None) -> str | None:
    """'132 고객 검색' style folder. None when no sub-domain given."""
    if not domain or not subdomain:
        return None
    canon = resolve_domain(domain)
    tens = _DOMAIN_BY_NAME[canon]["tens"] if canon else _FALLBACK["domain_tens"]
    sub_canon = resolve_subdomain(canon, subdomain)
    subs = _DOMAIN_BY_NAME.get(canon, {}).get("subs", {})
    unit = subs.get(sub_canon, _FALLBACK["subdomain_unit"])
    num = phase_num(phase) + tens * 10 + unit
    return f"{num} {_san(sub_canon or subdomain)}"


def taxonomy_tree() -> list[dict]:
    """Full numbered tree for the wiki browser: phase > domain > sub-domain."""
    out = []
    for phase, p in _PHASES.items():
        domains = []
        for d in _DOMAINS:
            subs = [{"name": s, "dir": subdomain_dir(phase, d["name"], s)}
                    for s in (d.get("subdomains") or [])]
            domains.append({"name": d["name"], "dir": domain_dir(phase, d["name"]),
                            "subdomains": subs})
        out.append({"phase": phase, "num": p["num"], "label": p["label"],
                    "dir": phase_dir(phase), "domains": domains})
    return out


def skeleton_dirs() -> list[str]:
    """Every phase/domain/sub-domain folder path (relative) for pre-creation."""
    out = []
    for phase in _PHASES:
        for d in _DOMAINS:
            dd = domain_dir(phase, d["name"])
            out.append(f"{phase_dir(phase)}/{dd}")
            for s in d.get("subdomains") or []:
                sd = subdomain_dir(phase, d["name"], s)
                out.append(f"{phase_dir(phase)}/{dd}/{sd}")
    return out


def fields_for(page_type: str) -> dict:
    return ENTITIES.get(page_type, ENTITIES["deliverable"])["fields"]


def required_fields(page_type: str) -> list[str]:
    return [f for f, spec in fields_for(page_type).items() if spec.get("required")]
