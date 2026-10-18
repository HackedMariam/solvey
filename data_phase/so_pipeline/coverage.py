"""Coverage matrix: target vs actual vs deficit for all 75 subcategory/difficulty cells."""

from collections import Counter
from dataclasses import dataclass

from .taxonomy import (ALL_SUBCATEGORIES, CATEGORY_TAXONOMY, DIFFICULTY_LEVELS,
                       TARGET_PER_CELL)


@dataclass
class CoverageCell:
    category: str
    subcategory: str
    difficulty: str
    target: int
    actual: int

    @property
    def deficit(self):
        return max(0, self.target - self.actual)


def build_coverage(records, target_per_cell=TARGET_PER_CELL):
    """One cell per (subcategory, difficulty); ``actual`` counts records in the dataset."""
    counts = Counter((r["subcategory"], r["difficulty"]) for r in records)
    cells = []
    for category, subcats in CATEGORY_TAXONOMY.items():
        for sub in subcats:
            for diff in DIFFICULTY_LEVELS:
                cells.append(CoverageCell(category, sub, diff,
                                          target_per_cell, counts.get((sub, diff), 0)))
    return cells


def resolution_counts(records):
    return Counter(r.get("resolution_status", "none") for r in records)


def difficulty_counts(records):
    return Counter(r.get("difficulty", "") for r in records)


def resolution_by_difficulty(records):
    cross = Counter((r.get("difficulty", ""), r.get("resolution_status", "none"))
                    for r in records)
    return cross


def coverage_to_rows(cells):
    return [
        {
            "category": c.category,
            "subcategory": c.subcategory,
            "difficulty": c.difficulty,
            "target": c.target,
            "actual": c.actual,
            "deficit": c.deficit,
        }
        for c in cells
    ]


def render_markdown(cells, res_counts, diff_counts, res_cross):
    lines = []
    lines.append("# Solvey dataset coverage matrix")
    lines.append("")
    lines.append("Target: 20 questions per subcategory x difficulty cell (25 x 3 = 75 cells, 1,500 total).")
    lines.append("")
    lines.append("| Category | Subcategory | Easy | Medium | Hard | Total |")
    lines.append("|---|---|---:|---:|---:|---:|")
    by_sub = {}
    for c in cells:
        by_sub.setdefault(c.subcategory, {})[c.difficulty] = c
    for category, subcats in CATEGORY_TAXONOMY.items():
        for sub in subcats:
            row = by_sub[sub]
            e, m, h = row["easy"], row["medium"], row["hard"]
            lines.append(
                f"| {category} | {sub} | {e.actual}/{e.target} | "
                f"{m.actual}/{m.target} | {h.actual}/{h.target} | "
                f"{e.actual + m.actual + h.actual}/60 |")
    totals = {d: sum(c.actual for c in cells if c.difficulty == d) for d in DIFFICULTY_LEVELS}
    lines.append(f"| **Overall** | **25 subcategories** | "
                 f"**{totals['easy']}/500** | **{totals['medium']}/500** | "
                 f"**{totals['hard']}/500** | "
                 f"**{sum(totals.values())}/1500** |")
    lines.append("")
    lines.append("## Deficits (actual < target)")
    lines.append("")
    lines.append("| Subcategory | Difficulty | Target | Actual | Deficit |")
    lines.append("|---|---|---:|---:|---:|")
    deficits = [c for c in cells if c.deficit > 0]
    if deficits:
        for c in deficits:
            lines.append(f"| {c.subcategory} | {c.difficulty} | {c.target} | {c.actual} | {c.deficit} |")
    else:
        lines.append("| - | - | - | - | 0 |")
    lines.append("")
    lines.append("## Resolution status (reported separately from difficulty)")
    lines.append("")
    lines.append("| Resolution status | Count |")
    lines.append("|---|---:|")
    for status in ("accepted", "top_voted", "none"):
        lines.append(f"| {status} | {res_counts.get(status, 0)} |")
    lines.append("")
    lines.append("| Difficulty | accepted | top_voted | none |")
    lines.append("|---|---:|---:|---:|")
    for d in DIFFICULTY_LEVELS:
        lines.append(f"| {d} | {res_cross.get((d, 'accepted'), 0)} | "
                     f"{res_cross.get((d, 'top_voted'), 0)} | {res_cross.get((d, 'none'), 0)} |")
    lines.append("")
    return "\n".join(lines)
