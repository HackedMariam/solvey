from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BlockKind = Literal["heading", "paragraph", "list_item", "table", "figure", "furniture", "code"]


@dataclass
class Block:
    kind: BlockKind
    text: str
    page: int | None
    block_id: str
    heading_level: int | None = None
    table_raw: str | None = None
    image_path: str | None = None


@dataclass
class ParsedDocument:
    title: str
    source: str
    url: str | None
    category: str
    source_type: str
    document_type: str
    blocks: list[Block]
