from __future__ import annotations

import html
import os
import logging
import re
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


def _simple_markdown_to_html(text: str) -> str:
    """Convert basic markdown to HTML for display. No external dependency."""
    # Escape HTML first
    text = html.escape(text)

    # Code blocks (```)
    text = re.sub(
        r'```(\w*)\n(.*?)```',
        r'<pre><code>\2</code></pre>',
        text,
        flags=re.DOTALL,
    )

    # Inline code
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    # Italic
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)

    # Headers
    text = re.sub(r'^### (.+)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)

    # Bullet lists
    text = re.sub(r'^[*-] (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
    text = re.sub(r'(<li>.*?</li>(?:\n<li>.*?</li>)*)', r'<ul>\1</ul>', text, flags=re.DOTALL)

    # Numbered lists
    text = re.sub(r'^\d+\. (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)

    # Paragraphs (double newlines)
    text = re.sub(r'\n\n+', '</p><p>', text)
    text = f'<p>{text}</p>'

    # Clean up empty paragraphs
    text = re.sub(r'<p>\s*</p>', '', text)

    return text


def ask_research(question: str) -> dict:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return {
            "answer": "Groq API key not configured. Please add GROQ_API_KEY to your environment.",
            "answer_html": "Groq API key not configured. Please add GROQ_API_KEY to your environment.",
            "error": True,
        }

    docs = _load_reference_docs()

    from groq import Groq

    client = Groq(api_key=api_key)

    system_prompt = (
        "You are a knowledgeable assistant for the Monaimetrics trading system. "
        "Answer the user's question based on the reference documents provided below. "
        "Be concise, accurate, and reference specific frameworks or strategies when relevant. "
        "Use markdown formatting for structure (headers, bullets, bold, code). "
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
        return {
            "answer": answer,
            "answer_html": _simple_markdown_to_html(answer),
            "error": False,
        }
    except Exception as e:
        log.error("Groq API error: %s", e)
        error_msg = f"Error querying Groq: {e}"
        return {
            "answer": error_msg,
            "answer_html": html.escape(error_msg),
            "error": True,
        }
