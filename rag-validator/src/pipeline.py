from __future__ import annotations

import csv
from pathlib import Path

from src.parsing.markdown_blocks import parse_markdown_blocks
from itsupport.rag.chunking import chunk_document as chunk_recursive
from itsupport.rag.loaders import load_file
from itsupport.rag.block_chunking import chunk_document as chunk_blocks
from src.parsing.pdf_parser import parse_document
from src.parsing.models import ParsedDocument

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CORPUS_DIR = DATA_DIR / "corpus"
MANIFEST_PATH = DATA_DIR / "corpus_manifest.csv"
FIGURE_DIR = DATA_DIR / "processed" / "figures"


def included_sources() -> list[dict[str, str]]:
    with MANIFEST_PATH.open(newline="", encoding="utf-8") as stream:
        rows = [row for row in csv.DictReader(stream) if row.get("status") == "included"]
    sources = {row["source"] for row in rows}
    if len(sources) != len(rows):
        raise ValueError("Manifest contains duplicate included source paths")
    for row in rows:
        path = DATA_DIR / Path(row["source"])
        if not path.is_file():
            raise FileNotFoundError(f"Included manifest source is missing: {path}")
    return rows


def chunks_for_strategy(strategy: str) -> list[dict]:
    if strategy not in {"recursive", "blocks"}:
        raise ValueError(f"Unknown strategy: {strategy}")

    chunks: list[dict] = []
    for row in included_sources():
        path = DATA_DIR / Path(row["source"])
        url = row.get("url") or None
        if strategy == "recursive":
            document = load_file(path, row["category"])
            if document is None:
                raise ValueError(f"No readable content in {path}")
            document.source = row["source"]
            recursive_chunks = chunk_recursive(document, "recursive")
            table_metadata = []
            if path.suffix.lower() in {".md", ".markdown"}:
                markdown = path.read_text(encoding="utf-8", errors="replace")
                parsed_blocks = parse_markdown_blocks(markdown, row["source"])
                for index, block in enumerate(parsed_blocks):
                    if not block.table_raw:
                        continue
                    intro = (
                        parsed_blocks[index - 1].text
                        if index > 0 and parsed_blocks[index - 1].text.rstrip().endswith(":")
                        else None
                    )
                    table_metadata.append((block.block_id, block.table_raw, intro))
            for chunk in recursive_chunks:
                metadata = chunk.metadata
                body = chunk.text
                table_ids = [
                    block_id
                    for block_id, table_raw, _intro in table_metadata
                    if any(line in body for line in table_raw.splitlines() if line.strip())
                ]
                table_intros = []
                for block_id, _table_raw, intro in table_metadata:
                    if intro and block_id in table_ids:
                        table_intros.append({"block_id": block_id, "text": intro})
                chunks.append({
                    "id": chunk.id,
                    "text": chunk.text,
                    "table_raw": None,
                    "image_description": None,
                    "image_path": None,
                    "title": metadata["title"],
                    "section": metadata.get("section", ""),
                    "page": metadata.get("page"),
                    "source": row["source"],
                    "url": url,
                    "category": row["category"],
                    "source_type": row["source_type"],
                    "document_type": row["format"],
                    "strategy": "recursive",
                    "_block_ids": [],
                    "_table_ids": table_ids,
                    "_table_intros": table_intros,
                })
        else:
            document: ParsedDocument = parse_document(
                path,
                category=row["category"],
                source_type=row["source_type"],
                url=url,
                figure_dir=FIGURE_DIR,
            )
            document.source = row["source"]
            chunks.extend(chunk_blocks(document))
    return chunks
