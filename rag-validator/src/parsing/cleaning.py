from __future__ import annotations

import re
from collections import defaultdict
from copy import deepcopy

from .models import Block

_SELECTION_MARKS = re.compile(r"(?i):(?:un)?selected:|[☒☐]")
_PAGE_LABEL = re.compile(r"(?i)^\s*(?:page\s+)?\d+(?:\s+of\s+\d+)?\s*$")
_SENTENCE_END = re.compile(r"""[.!?]["')\]]?\s*$""")


def clean_blocks(blocks: list[Block]) -> list[Block]:
    cleaned = deepcopy(blocks)
    page_heading_counts: dict[str, set[int]] = defaultdict(set)
    furniture_pages: dict[str, set[int]] = defaultdict(set)
    all_pages = {block.page for block in cleaned if block.page is not None}
    page_blocks: dict[int, list[Block]] = defaultdict(list)
    for block in cleaned:
        if block.page is not None:
            page_blocks[block.page].append(block)
        if block.kind == "heading" and block.page is not None:
            page_heading_counts[block.text.casefold()].add(block.page)
        if block.page is not None and (
            block.kind == "furniture" or (block.kind == "paragraph" and _PAGE_LABEL.match(block.text))
        ):
            normalized = re.sub(r"\d+", "#", block.text.casefold()).strip()
            furniture_pages[normalized].add(block.page)

    boundary_pages: dict[str, set[int]] = defaultdict(set)
    for page, page_items in page_blocks.items():
        for block in page_items[:2] + page_items[-2:]:
            if block.kind in {"paragraph", "furniture"} and len(block.text.strip()) <= 120:
                normalized = " ".join(block.text.casefold().split())
                if normalized:
                    boundary_pages[normalized].add(page)
    repeated_boundary_lines = {
        line
        for line, pages in boundary_pages.items()
        if len(pages) >= max(2, (len(all_pages) + 1) // 2)
    }

    kept: list[Block] = []
    for block in cleaned:
        block.text = _SELECTION_MARKS.sub("", block.text).strip()
        if block.table_raw:
            block.table_raw = _SELECTION_MARKS.sub("", block.table_raw).strip()
        if (
            block.page is not None
            and block.kind in {"paragraph", "furniture"}
            and " ".join(block.text.casefold().split()) in repeated_boundary_lines
        ):
            continue
        if block.kind == "heading" and len(page_heading_counts[block.text.casefold()]) >= 3:
            continue
        if block.kind == "furniture" or _PAGE_LABEL.match(block.text):
            normalized = re.sub(r"\d+", "#", block.text.casefold()).strip()
            threshold = (len(all_pages) + 1) // 2
            if all_pages and len(furniture_pages[normalized]) >= threshold:
                continue
            block.kind = "paragraph"
        if block.text or block.table_raw or block.image_path:
            kept.append(block)

    kept = _drop_contents_pages(kept)
    return _join_page_break_paragraphs(kept)


def _drop_contents_pages(blocks: list[Block]) -> list[Block]:
    contents_pages = {
        block.page for block in blocks
        if block.page is not None
        and block.kind == "heading"
        and block.text.strip().casefold() in {"contents", "table of contents"}
    }
    if not contents_pages:
        return blocks
    return [block for block in blocks if block.page not in contents_pages]


def _join_page_break_paragraphs(blocks: list[Block]) -> list[Block]:
    joined: list[Block] = []
    for block in blocks:
        if (
            joined
            and joined[-1].kind == "paragraph"
            and block.kind == "paragraph"
            and joined[-1].page is not None
            and block.page == joined[-1].page + 1
            and joined[-1].text
            and not _SENTENCE_END.search(joined[-1].text)
            and block.text[:1].islower()
        ):
            joined[-1].text = f"{joined[-1].text.rstrip()} {block.text.lstrip()}"
            continue
        joined.append(block)
    return joined
