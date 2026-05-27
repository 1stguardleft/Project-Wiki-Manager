"""Parse and serialize YAML frontmatter + markdown body."""
from __future__ import annotations

import yaml

_DELIM = "---"


def parse(text: str) -> tuple[dict, str]:
    """Split a markdown document into (frontmatter dict, body)."""
    if text.startswith(_DELIM):
        end = text.find("\n" + _DELIM, len(_DELIM))
        if end != -1:
            fm_block = text[len(_DELIM):end].strip("\n")
            body = text[end + len("\n" + _DELIM):].lstrip("\n")
            data = yaml.safe_load(fm_block) or {}
            return (data if isinstance(data, dict) else {}), body
    return {}, text


def dump(frontmatter: dict, body: str) -> str:
    fm = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    return f"{_DELIM}\n{fm}\n{_DELIM}\n\n{body.strip()}\n"
