from so_pipeline.coverage import (build_coverage, coverage_to_rows,
                                  difficulty_counts, render_markdown,
                                  resolution_by_difficulty, resolution_counts)
from so_pipeline.taxonomy import ALL_SUBCATEGORIES, DIFFICULTY_LEVELS


def make_record(sub, diff, status="none"):
    return {"subcategory": sub, "difficulty": diff, "resolution_status": status}


def test_empty_coverage_has_75_cells_and_full_deficit():
    cells = build_coverage([], target_per_cell=20)
    assert len(cells) == 75
    assert all(c.actual == 0 for c in cells)
    assert all(c.deficit == 20 for c in cells)
    assert sum(c.target for c in cells) == 1500


def test_counts_and_deficits():
    records = []
    sub = ALL_SUBCATEGORIES[0]
    records += [make_record(sub, "easy")] * 20
    records += [make_record(sub, "medium")] * 5
    records += [make_record(ALL_SUBCATEGORIES[1], "hard", "accepted")] * 3
    cells = build_coverage(records, target_per_cell=20)
    by_key = {(c.subcategory, c.difficulty): c for c in cells}
    assert by_key[(sub, "easy")].actual == 20
    assert by_key[(sub, "easy")].deficit == 0
    assert by_key[(sub, "medium")].actual == 5
    assert by_key[(sub, "medium")].deficit == 15
    assert by_key[(ALL_SUBCATEGORIES[1], "hard")].deficit == 17
    rows = coverage_to_rows(cells)
    assert len(rows) == 75
    assert set(rows[0]) == {"category", "subcategory", "difficulty", "target", "actual", "deficit"}


def test_resolution_and_difficulty_reported_separately():
    records = [
        make_record(ALL_SUBCATEGORIES[0], "easy", "accepted"),
        make_record(ALL_SUBCATEGORIES[0], "easy", "none"),
        make_record(ALL_SUBCATEGORIES[0], "hard", "top_voted"),
    ]
    assert resolution_counts(records)["accepted"] == 1
    assert resolution_counts(records)["none"] == 1
    assert difficulty_counts(records)["easy"] == 2
    cross = resolution_by_difficulty(records)
    assert cross[("easy", "accepted")] == 1
    assert cross[("hard", "top_voted")] == 1


def test_markdown_renders_with_totals():
    records = [make_record(ALL_SUBCATEGORIES[0], "easy", "none")]
    cells = build_coverage(records)
    md = render_markdown(cells, resolution_counts(records),
                         difficulty_counts(records),
                         resolution_by_difficulty(records))
    assert "500" in md
    assert ALL_SUBCATEGORIES[0] in md
    assert "accepted" in md


def test_every_difficulty_level_valid():
    for d in DIFFICULTY_LEVELS:
        assert d in ("easy", "medium", "hard")
