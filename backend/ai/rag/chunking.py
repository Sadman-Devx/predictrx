"""Semantic-ish chunking for drug labels: split on section boundaries first, then by size within long sections.

TODO (lead): replace the size split with embedding-based boundary detection if time allows.
"""
import re

_SECTION_RE = re.compile(r"^\s*(\d{1,2}(\.\d+)?\s+)?[A-Z][A-Z &/,\-]{4,}$", re.MULTILINE)


def split_sections(text: str) -> list[tuple[str, str]]:
    """Return [(section_title, section_text)]. Uppercase heading lines mark section starts."""
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        return [("", text.strip())] if text.strip() else []
    out = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            out.append((m.group(0).strip(), body))
    return out


def chunk_section(body: str, max_words: int = 180, overlap: int = 30) -> list[str]:
    words = body.split()
    if len(words) <= max_words:
        return [body]
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i:i + max_words]))
        i += max_words - overlap
    return chunks


def chunk_document(text: str) -> list[dict]:
    out = []
    for title, body in split_sections(text):
        for piece in chunk_section(body):
            out.append({"section": title, "text": piece, "token_count": len(piece.split())})
    return out
