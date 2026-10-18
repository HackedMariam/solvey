from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .models import Block

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_LIST = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
_TABLE_RULE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_MS_IMAGE = re.compile(r"^:::image\b(.*?):::\s*$")
_MS_IMAGE_SOURCE = re.compile(r'\bsource="([^"]+)"')
_MS_IMAGE_ALT = re.compile(r'\balt-text="([^"]*)"')


def _block_id(source: str, index: int, text: str) -> str:
    value = f"{source}|{index}|{text[:96]}"
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def parse_markdown_blocks(text: str, source: str, page: int | None = None) -> list[Block]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[Block] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        value = "\n".join(paragraph).strip()
        paragraph.clear()
        if value:
            blocks.append(Block("paragraph", value, page, _block_id(source, len(blocks), value)))

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush_paragraph()
            fence = stripped[:3]
            code_lines = [line]
            i += 1
            while i < len(lines):
                code_lines.append(lines[i])
                if lines[i].strip().startswith(fence):
                    i += 1
                    break
                i += 1
            code = "\n".join(code_lines)
            blocks.append(Block("code", code, page, _block_id(source, len(blocks), code)))
            continue
        heading = _HEADING.match(stripped)
        if heading:
            flush_paragraph()
            value = heading.group(2).strip()
            blocks.append(Block("heading", value, page, _block_id(source, len(blocks), value),
                                heading_level=len(heading.group(1))))
            i += 1
            continue
        if stripped.startswith("|") and i + 1 < len(lines) and _TABLE_RULE.match(lines[i + 1].strip()):
            flush_paragraph()
            table_lines = [stripped, lines[i + 1].strip()]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            table = "\n".join(table_lines)
            blocks.append(Block("table", table, page, _block_id(source, len(blocks), table), table_raw=table))
            continue
        microsoft_image = _MS_IMAGE.match(stripped)
        if microsoft_image:
            source_match = _MS_IMAGE_SOURCE.search(microsoft_image.group(1))
            if source_match:
                flush_paragraph()
                alt_match = _MS_IMAGE_ALT.search(microsoft_image.group(1))
                alt_text = alt_match.group(1).strip() if alt_match else ""
                image_path = source_match.group(1).strip()
                blocks.append(Block(
                    "figure",
                    alt_text,
                    page,
                    _block_id(source, len(blocks), image_path),
                    image_path=image_path,
                ))
                i += 1
                continue
        if _IMAGE.search(stripped):
            flush_paragraph()
            for image in _IMAGE.finditer(stripped):
                text_value = image.group(1).strip()
                path_value = image.group(2).strip()
                blocks.append(Block("figure", text_value, page, _block_id(source, len(blocks), path_value),
                                    image_path=path_value))
            i += 1
            continue
        if not stripped:
            flush_paragraph()
            i += 1
            continue
        if _LIST.match(line):
            flush_paragraph()
            blocks.append(Block("list_item", stripped, page, _block_id(source, len(blocks), stripped)))
            i += 1
            continue
        paragraph.append(line.rstrip())
        i += 1
    flush_paragraph()
    return blocks


def title_from_markdown(text: str, fallback: str) -> str:
    for line in text.splitlines():
        match = _HEADING.match(line.strip())
        if match:
            return match.group(2).strip()
    for line in text.splitlines():
        if line.lower().startswith("title:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return Path(fallback).stem.replace("-", " ").strip()


def html_to_markdown(path: Path) -> str:
    from bs4 import BeautifulSoup
    from markdownify import markdownify

    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    content = soup.find("main") or soup.find("article") or soup.body or soup
    return markdownify(str(content), heading_style="ATX", bullets="-").strip()
