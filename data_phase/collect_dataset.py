"""Entry point for the Solvey dataset pipeline (thin wrapper around so_pipeline).

Usage:
  python collect_dataset.py --pilot     # pilot: 2 subcategories, small limits
  python collect_dataset.py             # full collection toward the 1,500 target
  python collect_dataset.py --help
"""

from so_pipeline.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
