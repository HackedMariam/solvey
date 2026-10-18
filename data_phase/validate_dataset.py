"""Validation for the Solvey dataset: baseline preservation, taxonomy, uniqueness,
coverage cells, and absence of synthetic records. Run: python validate_dataset.py"""

import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from so_pipeline.taxonomy import (ALL_SUBCATEGORIES, CATEGORY_TAXONOMY,
                                  DIFFICULTY_LEVELS, LEGACY_SUBCATEGORY_ALIASES,
                                  SUBCATEGORY_TO_CATEGORY, TARGET_PER_CELL)

DATASET_CSV = Path("dataset/so_dataset.csv")
DATASET_JSONL = Path("dataset/so_dataset.jsonl")
BASELINE_CSV = Path("with resolution/results.csv")

failures = []
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)
    print(("PASS  " if condition else "FAIL  ") + message)


def main():
    # ---- baseline preserved (git status shows no modification) ----
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain", "--", "with resolution", "so_bug_data"],
            capture_output=True, text=True, check=False)
        dirty = [l for l in out.stdout.splitlines() if l.strip()]
        check(not dirty, f"baseline folders unchanged in git (status: {dirty or 'clean'})")
    except FileNotFoundError:
        print("SKIP  git not available for baseline check")

    with open(BASELINE_CSV, encoding="utf-8") as f:
        baseline = list(csv.DictReader(f))
    check(len(baseline) == 100, f"baseline has 100 rows (got {len(baseline)})")
    st = Counter(r["resolution_status"] for r in baseline)
    check(st.get("top_voted") == 43 and st.get("accepted") == 37 and st.get("none") == 20,
          f"baseline status 43/37/20 (got {dict(st)})")
    check(sum(1 for r in baseline if r.get("resolution", "").strip()) == 80,
          "baseline has 80 non-empty resolutions")

    # ---- dataset exists ----
    check(DATASET_CSV.exists() and DATASET_JSONL.exists(), "dataset CSV + JSONL exist")
    with open(DATASET_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with open(DATASET_JSONL, encoding="utf-8") as f:
        jsonl_rows = [json.loads(line) for line in f if line.strip()]

    check(len(rows) == len(jsonl_rows), f"CSV and JSONL row counts match ({len(rows)})")
    check(len(rows) == 1500, f"dataset has 1500 rows (got {len(rows)})")

    # ---- uniqueness ----
    ids = [r["question_id"] for r in rows]
    dupes = [qid for qid, n in Counter(ids).items() if n > 1]
    check(not dupes, f"no duplicate question_ids (dupes: {dupes[:5]})")

    # ---- taxonomy conformance ----
    allowed_subs = set(ALL_SUBCATEGORIES)
    bad_subs = sorted({r["subcategory"] for r in rows} - allowed_subs)
    check(not bad_subs, f"all subcategories in the 25-name taxonomy (bad: {bad_subs})")
    legacy_left = sorted({r["subcategory"] for r in rows} & set(LEGACY_SUBCATEGORY_ALIASES))
    check(not legacy_left, f"no legacy subcategory names remain ({legacy_left})")
    bad_cats = sorted({r["category"] for r in rows} - set(CATEGORY_TAXONOMY))
    check(not bad_cats, f"all categories valid ({bad_cats})")

    # ---- exactly one difficulty + one subcategory, consistent category ----
    bad_diff = [r["question_id"] for r in rows if r["difficulty"] not in DIFFICULTY_LEVELS]
    check(not bad_diff, f"every record has a valid difficulty ({bad_diff[:5]})")
    mismatched = [r["question_id"] for r in rows
                  if SUBCATEGORY_TO_CATEGORY.get(r["subcategory"]) != r["category"]]
    check(not mismatched, f"category matches subcategory ({mismatched[:5]})")

    # ---- coverage: 75 cells, 20 each ----
    cells = Counter((r["subcategory"], r["difficulty"]) for r in rows)
    check(len(cells) == 75, f"all 75 subcategory/difficulty cells populated (got {len(cells)})")
    not_full = {k: v for k, v in cells.items() if v != TARGET_PER_CELL}
    check(not not_full, f"every cell has exactly {TARGET_PER_CELL} (violations: {not_full})")
    diff_totals = Counter(r["difficulty"] for r in rows)
    check(all(diff_totals[d] == 500 for d in DIFFICULTY_LEVELS),
          f"difficulty totals 500/500/500 (got {dict(diff_totals)})")

    # ---- no synthetic records: every row has a real SO id + URL ----
    bad_url = [r["question_id"] for r in rows
               if not r["question_url"].startswith("https://stackoverflow.com/questions/")]
    check(not bad_url, f"every record links to a real SO question ({bad_url[:5]})")
    check(not any(r["question_id"].startswith("synthetic") or r["source"] == "synthetic"
                  for r in rows), "no synthetic records")

    # ---- baseline rows all reused ----
    baseline_ids = {r["question_id"] for r in baseline}
    missing = baseline_ids - set(ids)
    check(not missing, f"all 100 baseline question_ids present (missing: {sorted(missing)[:5]})")
    baseline_rows = [r for r in rows if r["question_id"] in baseline_ids]
    check(len(baseline_rows) == 100, f"baseline reused exactly once ({len(baseline_rows)})")

    # ---- resolution fields preserved/consistent ----
    res_ok = all(r["resolution_status"] in ("accepted", "top_voted", "none") for r in rows)
    check(res_ok, "resolution_status values follow existing convention")
    resolved = [r for r in rows if r["resolution"].strip()]
    st_all = Counter(r["resolution_status"] for r in rows)
    check(len(resolved) == st_all.get("accepted", 0) + st_all.get("top_voted", 0),
          "non-empty resolution aligns with accepted/top_voted")

    # ---- reports ----
    report_path = Path("dataset/reports/collection_report.json")
    check(report_path.exists(), "collection report exists")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    check(report["dataset"]["synthetic_records"] == 0, "report states 0 synthetic records")
    check(report["coverage"]["complete_cells"] == 75 and report["coverage"]["cells"] == 75,
          "report: 75/75 cells complete")
    check(Path("dataset/reports/duplicates.csv").exists()
          and Path("dataset/reports/exclusions.csv").exists()
          and Path("dataset/reports/coverage_matrix.csv").exists(),
          "duplicate + exclusion + coverage reports exist")

    # coverage matrix CSV totals
    with open("dataset/reports/coverage_matrix.csv", encoding="utf-8") as f:
        cov = list(csv.DictReader(f))
    check(len(cov) == 75, f"coverage matrix has 75 rows (got {len(cov)})")
    check(all(int(r["deficit"]) == 0 for r in cov), "coverage matrix deficits all 0")

    print()
    if failures:
        print(f"{len(failures)}/{checks} checks FAILED:")
        for m in failures:
            print("  -", m)
        return 1
    print(f"All {checks} checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
