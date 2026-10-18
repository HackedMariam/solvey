"""Corpus loaders: Markdown, text, HTML, PDF, and CSV knowledge-base rows.

Expected layout: data/corpus/<category_id>/<files>   (category_id from taxonomy.yaml, or 'general')
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED = {".md", ".markdown", ".txt", ".html", ".htm", ".pdf"}


@dataclass
class RawDocument:
    text: str
    source: str
    title: str
    category: str
    fmt: str
    page_offsets: list[int] = field(default_factory=list)  # PDF: char offset where each page starts


def _title_from(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip().lstrip("#").strip()
        if 3 <= len(line) <= 120:
            return line
    return fallback


def load_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def load_html(path: Path) -> str:
    """HTML -> Markdown-like text (headings kept as '#', code blocks kept)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    for level in range(1, 5):
        for h in soup.find_all(f"h{level}"):
            h.replace_with(f"\n\n{'#' * level} {h.get_text(' ', strip=True)}\n\n")
    for pre in soup.find_all("pre"):
        pre.replace_with(f"\n```\n{pre.get_text()}\n```\n")
    for li in soup.find_all("li"):
        li.insert_before("\n- ")
    text = (soup.find("main") or soup.find("article") or soup.body or soup).get_text()
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def load_pdf(path: Path) -> tuple[str, list[int]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts, offsets, pos = [], [], 0
    for page in reader.pages:
        txt = (page.extract_text() or "").strip()
        offsets.append(pos)
        parts.append(txt)
        pos += len(txt) + 2
    return "\n\n".join(parts), offsets


def load_file(path: Path, category: str) -> RawDocument | None:
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        return None
    offsets: list[int] = []
    if ext in {".md", ".markdown", ".txt"}:
        text = load_markdown(path)
    elif ext in {".html", ".htm"}:
        text = load_html(path)
    else:
        text, offsets = load_pdf(path)
    if not text.strip():
        return None
    return RawDocument(text=text, source=str(path), title=_title_from(text, path.stem), category=category,
                       fmt=ext.lstrip("."), page_offsets=offsets)


def load_corpus(corpus_dir: str | Path) -> list[RawDocument]:
    root = Path(corpus_dir)
    docs = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root)
            category = rel.parts[0] if len(rel.parts) > 1 else "general"
            doc = load_file(path, category)
            if doc:
                docs.append(doc)
    return docs


def load_csv_kb(path: str | Path, title_col: str, category_col: str | None = None,
                category_map: dict[str, str] | None = None, max_rows: int | None = None) -> list[RawDocument]:
    """One knowledge-base article per CSV row (e.g. the HF 'IT-Troubleshooting-Dataset').

    Every non-empty column becomes a '**Column:** value' line; the row's category is mapped to a
    taxonomy id with category_map (unmapped -> 'general')."""
    docs = []
    with open(path, newline="", encoding="utf-8", errors="ignore") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if max_rows and i >= max_rows:
                break
            title = (row.get(title_col) or f"row {i}").strip()
            raw_cat = (row.get(category_col) or "").strip() if category_col else ""
            category = (category_map or {}).get(raw_cat, "general")
            body = "\n".join(f"**{k}:** {v.strip()}" for k, v in row.items() if k and v and v.strip() and k != title_col)
            docs.append(RawDocument(text=f"# {title}\n\n{body}", source=f"{Path(path).name}#row{i}", title=title,
                                    category=category, fmt="csv"))
    return docs
