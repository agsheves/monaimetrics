from __future__ import annotations

import os
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_docs_cache: str | None = None


def _load_reference_docs() -> str:
    global _docs_cache
    if _docs_cache is not None:
        return _docs_cache

    docs_dir = Path(__file__).resolve().parent.parent / "_developer"
    if not docs_dir.exists():
        return "No reference documents found."

    parts = []
    for md_file in sorted(docs_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8", errors="ignore")
        parts.append(f"--- Document: {md_file.name} ---\n{content}\n")

    _docs_cache = "\n".join(parts)
    return _docs_cache


def ask_research(question: str) -> dict:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return {
            "answer": "Groq API key not configured. Please add GROQ_API_KEY to your environment.",
            "error": True,
        }

    docs = _load_reference_docs()

    from groq import Groq

    client = Groq(api_key=api_key)

    system_prompt = (
        "You are a knowledgeable assistant for the Monaimetrics trading system. "
        "Answer the user's question based on the reference documents provided below. "
        "Be concise, accurate, and reference specific frameworks or strategies when relevant. "
        "If the documents don't contain relevant information, say so clearly.\n\n"
        "REFERENCE DOCUMENTS:\n"
        f"{docs}"
    )

    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-4-maverick-17b-128e-instruct",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.3,
            max_tokens=2048,
        )
        answer = response.choices[0].message.content
        return {"answer": answer, "error": False}
    except Exception as e:
        log.error("Groq API error: %s", e)
        return {"answer": f"Error querying Groq: {e}", "error": True}
