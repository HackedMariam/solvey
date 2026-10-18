from __future__ import annotations

import re
import uuid
from collections import defaultdict

from src.parsing.cleaning import clean_blocks
from src.parsing.models import Block, ParsedDocument

CHUNK_TOKENS = 450
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def _token_count(text: str) -> int:
    import tiktoken

    return len(tiktoken.get_encoding("cl100k_base").encode(text))


def _split_oversized(block: Block, budget: int) -> list[Block]:
    if block.kind == "code" and _token_count(block.text) > budget:
        lines = block.text.splitlines()
        opening = lines[0] if lines and lines[0].strip().startswith(("```", "~~~")) else ""
        fence = opening.strip()[:3]
        has_closing = bool(opening and len(lines) > 1 and lines[-1].strip().startswith(fence))
        closing = lines[-1] if has_closing else ""
        content = lines[1:-1] if has_closing else lines[1:] if opening else lines

        def format_part(part: list[str]) -> str:
            return "\n".join(([opening] if opening else []) + part + ([closing] if closing else []))

        parts: list[str] = []
        current: list[str] = []
        for line in content:
            candidate = format_part(current + [line])
            if current and _token_count(candidate) > budget:
                parts.append(format_part(current))
                current = []
            current.append(line)
        if current:
            parts.append(format_part(current))
        if len(parts) > 1:
            return [
                Block("code", part, block.page, f"{block.block_id}-part-{index + 1}")
                for index, part in enumerate(parts)
            ]
        return [block]
    if block.kind not in {"paragraph", "list_item"} or _token_count(block.text) <= budget:
        return [block]
    sentences = _SENTENCE_BREAK.split(block.text)
    parts: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and _token_count(candidate) > budget:
            parts.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        parts.append(current)
    if len(parts) == 1:
        return [block]
    return [
        Block(block.kind, part, block.page, f"{block.block_id}-part-{index + 1}",
              heading_level=block.heading_level, table_raw=block.table_raw, image_path=block.image_path)
        for index, part in enumerate(parts)
    ]


def _body_text(blocks: list[Block]) -> str:
    return "\n\n".join(block.text or block.table_raw or "" for block in blocks if block.text or block.table_raw).strip()


def _record(
    document: ParsedDocument,
    section: str,
    page: int | None,
    index_on_page: int,
    blocks: list[Block],
) -> dict:
    prefix = f"Document: {document.title}\nSection: {section or 'General'}"
    body = _body_text(blocks)
    text = f"{prefix}\n\n{body}" if body else prefix
    page_key = str(page) if page is not None else "unknown"
    stable = f"{document.source}|{page_key}|{index_on_page}"
    tables = [block.table_raw for block in blocks if block.table_raw]
    images = [block.image_path for block in blocks if block.image_path]
    table_intros = []
    for index, block in enumerate(blocks):
        if (
            block.table_raw
            and index > 0
            and blocks[index - 1].text.rstrip().endswith(":")
        ):
            table_intros.append({"block_id": block.block_id, "text": blocks[index - 1].text})
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, stable)),
        "text": text,
        "table_raw": "\n\n".join(tables) or None,
        "image_description": None,
        "image_path": images or None,
        "title": document.title,
        "section": section,
        "page": page,
        "source": document.source,
        "url": document.url,
        "category": document.category,
        "source_type": document.source_type,
        "document_type": document.document_type,
        "strategy": "blocks",
        "_block_ids": [block.block_id for block in blocks],
        "_table_ids": [block.block_id for block in blocks if block.table_raw],
        "_table_intros": table_intros,
    }


def chunk_document(document: ParsedDocument, max_tokens: int = CHUNK_TOKENS) -> list[dict]:
    cleaned = clean_blocks(document.blocks)
    sections: list[tuple[int, str]] = []
    groups: list[tuple[str, int | None, list[Block]]] = []
    for block in cleaned:
        if block.kind == "heading":
            level = block.heading_level or 1
            sections = [(depth, name) for depth, name in sections if depth < level]
            sections.append((level, block.text))
            continue
        section = " > ".join(name for _depth, name in sections)
        if groups and groups[-1][0] == section and groups[-1][1] == block.page:
            groups[-1][2].append(block)
        else:
            groups.append((section, block.page, [block]))

    counts_by_page: dict[int | None, int] = defaultdict(int)
    chunks: list[dict] = []
    for section, page, blocks in groups:
        prefix = f"Document: {document.title}\nSection: {section or 'General'}"
        budget = max(1, max_tokens - _token_count(prefix) - 8)
        units: list[list[Block]] = []
        for block in blocks:
            if (
                block.kind == "table"
                and units
                and units[-1][-1].kind in {"paragraph", "list_item"}
                and units[-1][-1].text.rstrip().endswith(":")
            ):
                units[-1].append(block)
            else:
                units.append([block])

        current: list[Block] = []
        for unit in units:
            if current and _token_count(_body_text(current + unit)) > budget:
                chunks.append(_record(document, section, page, counts_by_page[page], current))
                counts_by_page[page] += 1
                current = []
            if len(unit) == 1:
                split = _split_oversized(unit[0], budget)
                if len(split) > 1:
                    for part in split:
                        if current and _token_count(_body_text(current + [part])) > budget:
                            chunks.append(_record(document, section, page, counts_by_page[page], current))
                            counts_by_page[page] += 1
                            current = []
                        current.append(part)
                    continue
            current.extend(unit)
        if current:
            chunks.append(_record(document, section, page, counts_by_page[page], current))
            counts_by_page[page] += 1

    return chunks
