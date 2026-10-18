"""CLI for the Solvey dataset pipeline.

Usage:
  python -m so_pipeline --pilot              # small pilot run (first 2 subcategories)
  python -m so_pipeline                      # full collection
  python -m so_pipeline --subcats "Account locked|Driver problem"
  python -m so_pipeline --download-images    # also download screenshots for new records
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def build_parser():
    p = argparse.ArgumentParser(prog="so_pipeline",
                                description="Extend the Solvey Stack Overflow dataset")
    p.add_argument("--project-root", default=".", help="repository root (default: .)")
    p.add_argument("--output-dir", default="dataset", help="output directory (default: dataset)")
    p.add_argument("--pilot", action="store_true", help="pilot run: first 2 subcategories only")
    p.add_argument("--fill-gaps", action="store_true",
                   help="keep the existing dataset, target only empty subcategory/difficulty "
                        "cells with difficulty-biased queries")
    p.add_argument("--pilot-subcats", type=int, default=2, help="subcategories in pilot mode")
    p.add_argument("--subcats", default=None,
                   help="'|'-separated subcategory names to target")
    p.add_argument("--target-per-cell", type=int, default=20,
                   help="questions per subcategory x difficulty cell (default 20)")
    p.add_argument("--max-pages-per-spec", type=int, default=2,
                   help="search pages per search spec (default 2)")
    p.add_argument("--max-candidates-per-subcat", type=int, default=150,
                   help="stop collecting for a subcategory after this many candidates")
    p.add_argument("--specs-limit", type=int, default=None,
                   help="use only the first N search specs per subcategory")
    p.add_argument("--min-quota", type=int, default=50,
                   help="stop collecting when API quota drops below this")
    p.add_argument("--pause", type=float, default=0.5,
                   help="seconds between API requests")
    p.add_argument("--refresh-cache", action="store_true", help="bypass the API response cache")
    p.add_argument("--download-images", action="store_true",
                   help="download screenshots for newly collected records")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None):
    load_dotenv()
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    os.chdir(args.project_root)
    from so_pipeline.pipeline import run_pipeline  # deferred: needs chdir first
    report = run_pipeline(args)
    ds = report["dataset"]
    cov = report["coverage"]
    print()
    print("=" * 60)
    print(f"Dataset rows      : {ds['rows']} "
          f"({ds['baseline_reused']} baseline + {ds['new_selected']} new)")
    print(f"Unique question IDs: {ds['unique_question_ids']}")
    print(f"Difficulty        : {ds['difficulty_counts']}")
    print(f"Resolution        : {ds['resolution_status_counts']}")
    print(f"Coverage          : {cov['total_actual']}/{cov['total_target']} "
          f"({cov['complete_cells']}/{cov['cells']} cells complete)")
    print(f"Report            : {report['outputs']['collection_report_json']}")
    return 0 if cov["complete_cells"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
