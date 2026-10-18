from __future__ import annotations

from src.parsing.cleaning import clean_blocks
from src.parsing.markdown_blocks import parse_markdown_blocks
from src.parsing.models import Block, ParsedDocument
from src.parsing.pdf_parser import parse_document
from itsupport.rag.block_chunking import chunk_document


def test_markdown_parser_preserves_headings_lists_tables_and_figures():
    blocks = parse_markdown_blocks(
        "# Network guide\n\nConnect to Wi-Fi:\n\n| Error | Fix |\n| --- | --- |\n| 1 | Retry |\n\n- Check signal\n\n```powershell\nGet-NetAdapter\n```\n\n:::image type=\"content\" source=\"media/map.png\" alt-text=\"Network adapter dialog\":::\n\n![Network map](map.png)",
        "guide.md",
    )
    assert [block.kind for block in blocks] == [
        "heading", "paragraph", "table", "list_item", "code", "figure", "figure",
    ]
    assert blocks[2].table_raw == "| Error | Fix |\n| --- | --- |\n| 1 | Retry |"
    assert blocks[4].text == "```powershell\nGet-NetAdapter\n```"
    assert blocks[5].text == "Network adapter dialog"
    assert blocks[5].image_path == "media/map.png"
    assert blocks[6].image_path == "map.png"


def test_large_code_blocks_split_at_lines_and_keep_fences():
    lines = [f"Write-Output 'diagnostic line {index}'" for index in range(40)]
    code = "```powershell\n" + "\n".join(lines) + "\n```"
    document = ParsedDocument(
        title="Command guide",
        source="commands.md",
        url=None,
        category="system_os",
        source_type="official_doc",
        document_type="md",
        blocks=[Block("code", code, None, "code-1")],
    )

    chunks = chunk_document(document, max_tokens=60)
    code_parts = [chunk["text"].split("\n\n", 1)[1] for chunk in chunks]
    assert len(code_parts) > 1
    assert all(part.startswith("```powershell\n") and part.endswith("\n```") for part in code_parts)
    assert [line for part in code_parts for line in part.splitlines()[1:-1]] == lines


def test_pdf_parser_preserves_page_and_markdown_table(tmp_path, monkeypatch):
    import pymupdf4llm

    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"test")
    monkeypatch.setattr(
        pymupdf4llm,
        "to_markdown",
        lambda *_args, **_kwargs: [{
            "text": (
                "# Remote access guide\n\nUse the following table:\n\n"
                "| Type | Access |\n| --- | --- |\n| VPN | Allowed |"
            ),
            "metadata": {"page_number": 2, "title": "Remote access guide"},
        }],
    )

    document = parse_document(pdf_path, "network_vpn")

    table = next(block for block in document.blocks if block.kind == "table")
    assert document.title == "Remote access guide"
    assert table.page == 2
    assert table.table_raw == "| Type | Access |\n| --- | --- |\n| VPN | Allowed |"


def test_cleaning_removes_repeated_furniture_and_joins_page_continuation():
    blocks = [
        Block("paragraph", "Repeated guide title", 1, "t1"),
        Block("furniture", "Internal guide v1", 1, "h1"),
        Block("paragraph", "The client connection was interrupted because", 1, "p1"),
        Block("paragraph", "Repeated guide title", 2, "t2"),
        Block("paragraph", "the device changed networks.", 2, "p2"),
        Block("furniture", "Internal guide v2", 2, "h2"),
        Block("paragraph", "Repeated guide title", 3, "t3"),
        Block("paragraph", "Unique page text.", 3, "p3"),
    ]
    cleaned = clean_blocks(blocks)
    assert not any(block.text == "Repeated guide title" for block in cleaned)
    assert not any(block.kind == "furniture" for block in cleaned)
    assert any(block.text == "The client connection was interrupted because the device changed networks." for block in cleaned)
    assert any(block.text == "Unique page text." for block in cleaned)


def test_block_chunker_keeps_table_intro_and_never_crosses_page_or_section():
    document = ParsedDocument(
        title="Windows guide",
        source="guide.pdf",
        url=None,
        category="system_os",
        source_type="official_doc",
        document_type="pdf",
        blocks=[
            Block("heading", "Update errors", 1, "h1", heading_level=1),
            Block("paragraph", "Use the following table:", 1, "p1"),
            Block("table", "| Error | Action |\n| --- | --- |\n| 1 | Retry |", 1, "t1",
                  table_raw="| Error | Action |\n| --- | --- |\n| 1 | Retry |"),
            Block("paragraph", "A separate page procedure.", 2, "p2"),
            Block("heading", "Network errors", 2, "h2", heading_level=1),
            Block("paragraph", "Check the network.", 2, "p3"),
        ],
    )
    chunks = chunk_document(document)
    table_chunk = next(chunk for chunk in chunks if chunk["table_raw"])
    assert "Use the following table:" in table_chunk["text"]
    assert table_chunk["page"] == 1
    assert table_chunk["_table_ids"] == ["t1"]
    assert table_chunk["_table_intros"] == [{"block_id": "t1", "text": "Use the following table:"}]
    assert all(chunk["page"] is None or chunk["page"] in {1, 2} for chunk in chunks)
    assert any(chunk["section"] == "Update errors" for chunk in chunks)
    assert any(chunk["section"] == "Network errors" for chunk in chunks)
    assert len({chunk["id"] for chunk in chunks}) == len(chunks)
