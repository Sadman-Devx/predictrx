"""Semantic chunking for drug labels.

Three layers, cheapest first:

1. Section split. Uppercase heading lines mark label sections (WARNINGS, DRUG INTERACTIONS, ...).
2. Sentence-aware packing. Sentences are packed into chunks of at most `max_words`; a chunk never ends in the
   middle of a sentence. The last sentence(s) of a chunk (up to `overlap` words) are repeated at the start of the
   next one, so a statement that straddles a boundary can still be retrieved. A single sentence longer than
   `max_words` (label text with no punctuation, long lists) falls back to overlapping word windows.
3. Optional meaning-based boundaries. Pass `embed_fn` (texts -> vectors) and the packer also prefers to start a new
   chunk where the topic changes (adjacent-sentence similarity drops). This costs one embedding per sentence, so it
   is off by default; `data/pipeline/load.py --semantic-boundaries` turns it on.

Limits (say so in the pitch): sentence splitting is rule-based, tuned for English openFDA text. Abbreviations that
are not in `_ABBREVIATIONS` can cause a false split, and a missed split only means a longer chunk.
Changing anything here changes what gets retrieved: re-run the evaluation afterwards (docs/rule.md §2).
"""
import math
import re
from typing import Callable, Sequence

_SECTION_RE = re.compile(r"^\s*(\d{1,2}(\.\d+)?\s+)?[A-Z][A-Z &/,\-]{4,}$", re.MULTILINE)

# A sentence ends at . ! ? followed by whitespace and something that looks like a sentence start.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[\"'])")
_ABBREVIATIONS = ("e.g.", "i.e.", "vs.", "approx.", "fig.", "dr.", "mr.", "cf.", "et al.")

EmbedFn = Callable[[Sequence[str]], "list[list[float]]"]


# ----------------------------------------------------------------------------------------------------------
# 1. Sections
# ----------------------------------------------------------------------------------------------------------
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


# ----------------------------------------------------------------------------------------------------------
# 2. Sentences and packing
# ----------------------------------------------------------------------------------------------------------
def split_sentences(text: str) -> list[str]:
    """Split text into sentences (whitespace collapsed). Known abbreviations do not end a sentence."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    out: list[str] = []
    for piece in _SENT_SPLIT_RE.split(text):
        piece = piece.strip()
        if not piece:
            continue
        if out and out[-1].lower().endswith(_ABBREVIATIONS):
            out[-1] = f"{out[-1]} {piece}"
        else:
            out.append(piece)
    return out


def _word_windows(words: list[str], max_words: int, overlap: int) -> list[str]:
    """Overlapping windows of at most `max_words` words that together cover every word."""
    step = max(1, max_words - overlap)
    out: list[str] = []
    i = 0
    while i < len(words):
        out.append(" ".join(words[i:i + max_words]))
        if i + max_words >= len(words):
            break
        i += step
    return out


def _carry(sentences: list[str], overlap: int) -> tuple[list[str], int]:
    """Trailing sentences whose total length is at most `overlap` words (repeated at the start of the next chunk)."""
    kept: list[str] = []
    total = 0
    for s in reversed(sentences):
        n = len(s.split())
        if total + n > overlap:
            break
        kept.append(s)
        total += n
    kept.reverse()
    return kept, total


def _pack(sentences: list[str], breaks: set[int], max_words: int, overlap: int, min_words: int) -> list[str]:
    """Greedy packing. `breaks` = indexes of sentences that start a new topic (see `semantic_breaks`)."""
    chunks: list[str] = []
    cur: list[str] = []
    cur_words = 0
    for i, s in enumerate(sentences):
        n = len(s.split())
        if n > max_words:
            # One over-long sentence: window-split it together with whatever is already buffered, so a short
            # sentence in front of it does not end up as a tiny chunk of its own.
            windows = _word_windows(" ".join([*cur, s]).split(), max_words, overlap)
            chunks.extend(windows[:-1])
            cur, cur_words = [windows[-1]], len(windows[-1].split())
            continue
        if cur:
            if i in breaks and cur_words >= min_words:
                # topic change and the chunk is big enough: start fresh, no overlap needed
                chunks.append(" ".join(cur))
                cur, cur_words = [], 0
            elif cur_words + n > max_words:
                chunks.append(" ".join(cur))
                cur, cur_words = _carry(cur, overlap)
                if cur_words + n > max_words:  # the carried tail leaves no room: drop the overlap
                    cur, cur_words = [], 0
        cur.append(s)
        cur_words += n
    if cur:
        chunks.append(" ".join(cur))
    return chunks


# ----------------------------------------------------------------------------------------------------------
# 3. Meaning-based boundaries (optional)
# ----------------------------------------------------------------------------------------------------------
def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q / 100.0
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def semantic_breaks(sentences: list[str], embed_fn: EmbedFn, percentile: float = 85.0) -> set[int]:
    """Indexes i (>= 1) where sentence i starts a new topic: the gap to sentence i-1 is among the largest
    `100 - percentile` percent of gaps in this section (gap = 1 - cosine similarity of the two sentences)."""
    if len(sentences) < 4:
        return set()
    vectors = embed_fn(sentences)
    if len(vectors) != len(sentences):
        raise ValueError("embed_fn must return one vector per sentence")
    gaps = [1.0 - _cosine(vectors[i], vectors[i + 1]) for i in range(len(sentences) - 1)]
    cutoff = _percentile(gaps, percentile)
    return {i + 1 for i, gap in enumerate(gaps) if gap > cutoff}


# ----------------------------------------------------------------------------------------------------------
# Public API (signatures used by data/pipeline/load.py and tests)
# ----------------------------------------------------------------------------------------------------------
def chunk_section(
    body: str,
    max_words: int = 180,
    overlap: int = 30,
    *,
    embed_fn: EmbedFn | None = None,
    min_words: int | None = None,
    breakpoint_percentile: float = 85.0,
) -> list[str]:
    """Chunk one section body. Chunks are at most `max_words` words and end on a sentence boundary
    (except inside a single sentence that is longer than `max_words`)."""
    body = (body or "").strip()
    if not body:
        return []
    max_words = max(1, max_words)
    overlap = max(0, min(overlap, max_words // 2))
    if len(body.split()) <= max_words:
        return [body]
    sentences = split_sentences(body)
    breaks = semantic_breaks(sentences, embed_fn, breakpoint_percentile) if embed_fn is not None else set()
    floor = min_words if min_words is not None else max_words // 3
    return _pack(sentences, breaks, max_words, overlap, floor)


def chunk_document(text: str, max_words: int = 180, overlap: int = 30, embed_fn: EmbedFn | None = None) -> list[dict]:
    out = []
    for title, body in split_sections(text):
        for piece in chunk_section(body, max_words, overlap, embed_fn=embed_fn):
            out.append({"section": title, "text": piece, "token_count": len(piece.split())})
    return out