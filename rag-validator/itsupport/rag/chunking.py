"""Two chunking strategies to compare in the retrieval benchmark.

A) "recursive": fixed-size recursive character splitting (strong generic baseline).
B) "structure": section-aware splitting. Detects headings (Markdown '#', numbered '2.3 Title',
   short ALL-CAPS lines), keeps each troubleshooting section / numbered procedure together,
   and prefixes every chunk with its document title + section path (contextual header).
"""
from __future__ import annotations

import bisect
import hashlib
import re
from dataclasses import dataclass

from .loaders import RawDocument

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
MIN_SECTION = 200


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict


# ------------------------------------------------------------------------------- strategy A
def _recursive_split(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        return RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap).split_text(text)
    except ImportError:  # minimal fallback with the same idea
        return _pack(re.split(r"\n\s*\n", text), size, overlap)


def _pack(pieces: list[str], size: int, overlap: int) -> list[str]:
    out, cur = [], ""
    for p in (x.strip() for x in pieces):
        if not p:
            continue
        while len(p) > size:  # very long paragraph
            head, p = p[:size], p[size - overlap:]
            if cur:
                out.append(cur)
                cur = ""
            out.append(head)
        if len(cur) + len(p) + 2 <= size:
            cur = f"{cur}\n\n{p}" if cur else p
        else:
            if cur:
                out.append(cur)
            cur = (cur[-overlap:] + "\n\n" + p) if cur and overlap else p
    if cur:
        out.append(cur)
    return out


# ------------------------------------------------------------------------------- strategy B
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
_NUM_HEADING = re.compile(r"^(\d+(?:\.\d+){0,3})\.?\s+([A-Z][^\n]{2,80})$")
_CAPS_HEADING = re.compile(r"^[A-Z][A-Z0-9 /&\-:()]{3,70}$")


def _heading(line: str) -> tuple[int, str] | None:
    s = line.strip()
    if not s or len(s) > 100:
        return None
    m = _MD_HEADING.match(s)
    if m:
        return len(m.group(1)), m.group(2).strip()
    m = _NUM_HEADING.match(s)
    if m and not s.endswith((".", ",", ";", ":", "?")):
        number, title = m.group(1), m.group(2)
        if "." in number:  # "2.3 Title" -> always a heading
            return number.count(".") + 1, s
        # "1. Something": heading only if short and Title-Cased, otherwise it's a numbered step
        words = title.split()
        long_words = [w for w in words if len(w) > 3]
        if len(words) <= 6 and long_words and sum(w[0].isupper() for w in long_words) / len(long_words) >= 0.5:
            return 1, s
    if _CAPS_HEADING.match(s) and sum(c.isalpha() for c in s) >= 4:
        return 2, s.title()
    return None


def split_sections(text: str) -> list[tuple[str, str, int]]:
    """Return [(section_path, body, start_offset)]."""
    sections: list[tuple[str, str, int]] = []
    path: list[tuple[int, str]] = []
    body: list[str] = []
    start, pos, in_code = 0, 0, False

    def flush():
        content = "\n".join(body).strip()
        if content:
            sections.append((" > ".join(t for _, t in path), content, start))

    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
        h = None if in_code else _heading(stripped)
        if h:
            flush()
            body = []
            level, title = h
            path = [p for p in path if p[0] < level] + [(level, title)]
            start = pos
        else:
            body.append(line.rstrip("\n"))
        pos += len(line)
    flush()
    return sections


def _merge_small(sections: list[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
    merged: list[tuple[str, str, int]] = []
    for sec in sections:
        if merged and len(merged[-1][1]) < MIN_SECTION:
            p, b, s = merged[-1]
            merged[-1] = (p, f"{b}\n\n{sec[0].split(' > ')[-1]}\n{sec[1]}" if sec[0] else f"{b}\n\n{sec[1]}", s)
        else:
            merged.append(sec)
    return merged


def _structure_split(text: str) -> list[tuple[str, str, int]]:
    out = []
    for path, body, start in _merge_small(split_sections(text)):
        if len(body) <= CHUNK_SIZE:
            out.append((path, body, start))
        else:  # long section: split on paragraphs but never inside a numbered list item
            paragraphs = re.split(r"\n\s*\n(?!\s*(?:\d+[.)]|[-*•])\s)", body)
            for piece in _pack(paragraphs, CHUNK_SIZE, CHUNK_OVERLAP):
                out.append((path, piece, start))
    return out


# ------------------------------------------------------------------------------- public API
def _page_of(doc: RawDocument, offset: int) -> int | None:
    if not doc.page_offsets:
        return None
    return bisect.bisect_right(doc.page_offsets, max(offset, 0))  # 1-based page number


def _cid(doc: RawDocument, strategy: str, i: int, text: str) -> str:
    return hashlib.sha1(f"{strategy}|{doc.source}|{i}|{text[:64]}".encode()).hexdigest()[:20]


def chunk_document(doc: RawDocument, strategy: str) -> list[Chunk]:
    base = {"source": doc.source, "title": doc.title, "category": doc.category, "format": doc.fmt, "strategy": strategy}
    chunks: list[Chunk] = []
    if strategy == "recursive":
        cursor = 0
        for i, piece in enumerate(_recursive_split(doc.text)):
            found = doc.text.find(piece[:80], cursor)
            offset = found if found >= 0 else cursor
            cursor = max(cursor, offset)
            meta = {**base, "section": "", "chunk_index": i}
            page = _page_of(doc, offset)
            if page:
                meta["page"] = page
            chunks.append(Chunk(_cid(doc, strategy, i, piece), piece, meta))
    elif strategy == "structure":
        for i, (path, body, start) in enumerate(_structure_split(doc.text)):
            short = path[len(doc.title):].lstrip(" >") if path.startswith(doc.title) else path
            header = f"{doc.title}" + (f" — {short}" if short else "")
            meta = {**base, "section": path, "chunk_index": i}
            page = _page_of(doc, start)
            if page:
                meta["page"] = page
            text = f"[{header}]\n{body}"
            chunks.append(Chunk(_cid(doc, strategy, i, text), text, meta))
    else:
        raise ValueError(f"unknown chunking strategy {strategy!r} (use 'recursive' or 'structure')")
    return chunks
