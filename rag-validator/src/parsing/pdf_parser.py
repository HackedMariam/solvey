from __future__ import annotations

import re
from pathlib import Path

from .markdown_blocks import html_to_markdown, parse_markdown_blocks, title_from_markdown
from .models import Block, ParsedDocument


def parse_document(
    path: Path,
    category: str,
    source_type: str = "official_doc",
    url: str | None = None,
    figure_dir: Path | None = None,
) -> ParsedDocument:
    suffix = path.suffix.lower()
    source = str(path)
    document_type = suffix.lstrip(".")

    if suffix in {".md", ".markdown", ".txt"}:
        markdown = path.read_text(encoding="utf-8", errors="replace")
        blocks = parse_markdown_blocks(markdown, source)
        title = title_from_markdown(markdown, path.name)
    elif suffix in {".html", ".htm"}:
        markdown = html_to_markdown(path)
        blocks = parse_markdown_blocks(markdown, source)
        title = title_from_markdown(markdown, path.name)
    elif suffix == ".pdf":
        blocks, title = _parse_pdf(path, figure_dir)
    else:
        raise ValueError(f"Unsupported document format: {path.suffix}")

    if not blocks:
        raise ValueError(f"No readable content found in {path}")
    return ParsedDocument(title, source, url, category, source_type, document_type, blocks)


def _parse_pdf(path: Path, figure_dir: Path | None) -> tuple[list[Block], str]:
    from pymupdf4llm import to_markdown

    pages = to_markdown(
        str(path),
        page_chunks=True,
        write_images=figure_dir is not None,
        image_path=str(figure_dir) if figure_dir is not None else "",
    )
    if not pages:
        raise ValueError(f"No readable pages found in {path}")

    blocks: list[Block] = []
    title = ""
    for index, page_chunk in enumerate(pages):
        if not isinstance(page_chunk, dict) or not isinstance(page_chunk.get("text"), str):
            raise TypeError(f"Unexpected PyMuPDF4LLM page chunk at index {index} in {path}")
        metadata = page_chunk.get("metadata") or {}
        page = metadata.get("page_number")
        if not isinstance(page, int):
            page = index + 1
        markdown = page_chunk["text"]
        if not title:
            title = metadata.get("title") or title_from_markdown(markdown, path.name)
        blocks.extend(parse_markdown_blocks(markdown, str(path), page))

    return _clean_selection_marks(blocks), title or path.stem


def _clean_selection_marks(blocks: list[Block]) -> list[Block]:
    marks = re.compile(r"(?i):(?:un)?selected:|[☒☐]")
    for block in blocks:
        block.text = marks.sub("", block.text).strip()
        if block.table_raw:
            block.table_raw = marks.sub("", block.table_raw).strip()
    return [block for block in blocks if block.text or block.table_raw or block.image_path]
