"""Query the wiki: hybrid-search for context, synthesize a cited answer.

requirements FR-OPS-2 / UC-4.  In offline mode the answer is an extractive
summary of the top snippets; with OpenAI it is a synthesized answer.
"""
from __future__ import annotations

from app.services import llm, search

_SYSTEM = (
    "You are a wiki assistant. Answer the question using ONLY the provided wiki "
    "excerpts. Cite sources inline as [[slug]]. If the excerpts are insufficient, "
    "say so. Answer in the user's language."
)


def answer(question: str, k: int = 6) -> dict:
    hits = search.hybrid_search(question, k=k)
    if not hits:
        return {"answer": "관련 위키 페이지를 찾지 못했습니다.", "citations": []}
    context = "\n\n".join(f"[[{h['slug']}]] ({h['sdlc_phase']}):\n{h['snippet']}" for h in hits)
    prompt = f"질문: {question}\n\n위키 발췌:\n{context}"
    text = llm.chat(prompt, system=_SYSTEM)
    return {
        "answer": text,
        "citations": [{"slug": h["slug"], "title": h["title"],
                       "sdlc_phase": h["sdlc_phase"]} for h in hits],
    }
