"""OpenAI client wrapper with deterministic offline fallbacks.

When OPENAI_API_KEY is missing (config.LLM_ENABLED is False) every call returns
a sensible heuristic result so the full pipeline — and its live visualization —
still runs end to end in demo/offline mode.
"""
from __future__ import annotations

import hashlib
import json
import re

from app import config

_client = None


def _openai():
    global _client
    if _client is None:
        if config.LLM_PROVIDER == "azure":
            from openai import AzureOpenAI
            _client = AzureOpenAI(
                azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
                api_key=config.AZURE_OPENAI_API_KEY,
                api_version=config.AZURE_OPENAI_API_VERSION,
            )
        else:
            from openai import OpenAI
            kwargs = {"api_key": config.OPENAI_API_KEY}
            if config.OPENAI_BASE_URL:
                kwargs["base_url"] = config.OPENAI_BASE_URL
            _client = OpenAI(**kwargs)
    return _client


def chat(prompt: str, system: str = "", *, json_mode: bool = False) -> str:
    if not config.LLM_ENABLED:
        return _fallback_chat(prompt, json_mode=json_mode)
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    kwargs = {"model": config.OPENAI_CHAT_MODEL, "messages": msgs, "temperature": 0.2}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = _openai().chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def embed(texts: list[str]) -> list[list[float]]:
    if not config.LLM_ENABLED:
        return [_fallback_embed(t) for t in texts]
    resp = _openai().embeddings.create(model=config.OPENAI_EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


# ── Offline fallbacks ──────────────────────────────────────────────────────
def _fallback_chat(prompt: str, *, json_mode: bool) -> str:
    if json_mode:
        return json.dumps({"offline": True})
    # echo a trimmed, de-noised version of the input
    return re.sub(r"\n{3,}", "\n\n", prompt).strip()[:2000]


def _fallback_embed(text: str, dim: int = config.EMBED_DIM) -> list[float]:
    """Deterministic pseudo-embedding: hashed bag-of-words bucketed into `dim`."""
    vec = [0.0] * dim
    for tok in re.findall(r"[\w가-힣]+", text.lower()):
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]
