"""Download the Stack Overflow screenshots referenced by the Solvey dataset.

Standalone companion to ``collect_dataset.py``: it reads ``dataset/so_dataset.csv``,
fetches every image that is not on disk yet into ``dataset/images/`` and records
the result back into the dataset (``image_files`` / ``image_dir`` / ``image_count``).
The images stay local-only: ``dataset/images/`` is git-ignored.

It deliberately does not import or modify the collection pipeline, the API cache
or the baseline folders, so a run cannot clobber anything else in ``dataset/``.

Usage:
  python download_images.py                 # fetch every missing image
  python download_images.py --dry-run       # only report what would be fetched
  python download_images.py --limit 5       # first 5 rows that need work
  python download_images.py --help
"""

import argparse
import csv
import json
import os
import shutil
import sys
import time
from pathlib import Path

import requests

ALLOWED_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
DEFAULT_CSV = "dataset/so_dataset.csv"
DEFAULT_JSONL = "dataset/so_dataset.jsonl"
DEFAULT_IMAGES_DIR = "dataset/images"
USER_AGENT = "solvey-dataset-images/1.0"


def split_semi(value):
    return [v for v in (value or "").split(";") if v]


def image_ext(url):
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    return ext if ext in ALLOWED_EXTS else ".png"


def image_filename(question_id, index, url):
    """Same convention as the baseline scraper: so_<question_id>_<index>.<ext>"""
    return f"so_{question_id}_{index}{image_ext(url)}"


def expected_files(row):
    """(index, url, filename) for every image URL of a row, in order."""
    qid = str(row.get("question_id", ""))
    return [(i, url, image_filename(qid, i, url))
            for i, url in enumerate(split_semi(row.get("image_urls")))]


def plan_row(row, images_dir, root=Path(".")):
    """Work needed so every image of ``row`` lives under ``images_dir``.

    Relative ``image_dir`` values are resolved against ``root`` so the script
    behaves the same regardless of the working directory.

    Returns ``None`` when the row needs nothing (no image URLs, or all files
    already present under its current ``image_dir``), otherwise a dict with:
      copies     - local files to bring into ``images_dir`` (no download)
      downloads  - (index, url, filename) still to fetch
      expected   - final (index, url, filename) list in row order
    """
    expected = expected_files(row)
    if not expected:
        return None
    row_dir = Path(row["image_dir"]) if row.get("image_dir") else None
    if row_dir is not None and not row_dir.is_absolute():
        row_dir = root / row_dir
    if row_dir is not None and all((row_dir / name).is_file() for _, _, name in expected):
        return None
    copies, downloads = [], []
    for i, url, name in expected:
        if (images_dir / name).is_file():
            continue
        if row_dir is not None and (row_dir / name).is_file():
            copies.append((name, row_dir / name))
        else:
            downloads.append((i, url, name))
    if not downloads and not copies and row_dir is not None \
            and row_dir.resolve() == images_dir.resolve():
        return None
    return {"copies": copies, "downloads": downloads, "expected": expected}


def fetch_image(url, dest, session, timeout=30, retries=3, delay=0.15):
    """Stream ``url`` to ``dest`` atomically. Returns (ok, error_message)."""
    part = dest.with_name(dest.name + ".part")
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=timeout, stream=True)
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "")
            if "image" not in ctype.lower():
                raise ValueError(f"unexpected content type: {ctype or 'none'}")
            with open(part, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
            part.replace(dest)
            return True, None
        except Exception as exc:  # noqa: BLE001 - retry then record
            last_error = exc
            if part.exists():
                part.unlink()
            if attempt < retries:
                time.sleep(delay * attempt)
    return False, str(last_error)


def process_rows(rows, images_dir, images_dir_label, fetcher,
                 delay=0.15, limit=None, dry_run=False, root=Path("."), log=print):
    """Fetch missing images for every row that needs them.

    Mutates the affected rows in place and returns
    ``(stats, changed_rows)``; ``changed_rows`` is empty in dry-run mode.
    """
    stats = {"rows": 0, "copied": 0, "downloaded": 0,
             "failed": 0, "failures": []}
    changed = []
    for row in rows:
        plan = plan_row(row, images_dir, root=root)
        if plan is None:
            continue
        if limit is not None and stats["rows"] >= limit:
            break
        stats["rows"] += 1
        if dry_run:
            for name, src in plan["copies"]:
                log(f"  copy   {src} -> {images_dir / name}")
            for _, url, name in plan["downloads"]:
                log(f"  get    {url} -> {images_dir / name}")
            continue

        images_dir.mkdir(parents=True, exist_ok=True)
        for name, src in plan["copies"]:
            shutil.copy2(src, images_dir / name)
            stats["copied"] += 1

        files = []
        for _, url, name in plan["expected"]:
            dest = images_dir / name
            if not dest.is_file():
                ok, err = fetcher(url, dest)
                if not ok:
                    stats["failed"] += 1
                    stats["failures"].append((row.get("question_id"), url, err))
                    log(f"  FAIL   {url}: {err}")
                    continue
                stats["downloaded"] += 1
                time.sleep(delay)
            files.append(name)

        if not files:
            continue
        row["image_files"] = ";".join(files)
        row["image_dir"] = images_dir_label
        row["image_count"] = len(files)
        changed.append(row)
    return stats, changed


def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def write_jsonl(path, updates):
    """Update only the image fields of the affected rows, keep everything else."""
    lines = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            record = json.loads(line)
            upd = updates.get(str(record.get("question_id")))
            if upd:
                record.update(upd)
            lines.append(json.dumps(record, ensure_ascii=False))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def build_parser():
    p = argparse.ArgumentParser(
        prog="download_images",
        description="Download dataset screenshots into dataset/images (local-only)")
    p.add_argument("--root", default=".", help="repository root (default: .)")
    p.add_argument("--csv", default=DEFAULT_CSV, help=f"dataset CSV (default {DEFAULT_CSV})")
    p.add_argument("--jsonl", default=DEFAULT_JSONL,
                   help=f"dataset JSONL (default {DEFAULT_JSONL})")
    p.add_argument("--images-dir", default=DEFAULT_IMAGES_DIR,
                   help=f"image folder, relative to root (default {DEFAULT_IMAGES_DIR})")
    p.add_argument("--limit", type=int, default=None,
                   help="stop after this many rows needing work")
    p.add_argument("--delay", type=float, default=0.15,
                   help="seconds between downloads (default 0.15)")
    p.add_argument("--timeout", type=int, default=30, help="per-request timeout")
    p.add_argument("--dry-run", action="store_true",
                   help="report the work without downloading or writing")
    return p


def run(args, fetcher=None):
    root = Path(args.root)
    csv_path = root / args.csv
    jsonl_path = root / args.jsonl
    images_dir_label = Path(args.images_dir).as_posix()
    images_dir = Path(args.images_dir)
    if not images_dir.is_absolute():
        images_dir = root / images_dir

    if not csv_path.exists():
        raise SystemExit(f"dataset CSV not found: {csv_path}")

    with open(csv_path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if fetcher is None:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})

        def fetcher(url, dest):  # noqa: F811 - intentional factory default
            return fetch_image(url, dest, session, timeout=args.timeout)

    if args.dry_run:
        print(f"would fetch images for rows under {images_dir}")

    stats, changed = process_rows(rows, images_dir, images_dir_label, fetcher,
                                  delay=args.delay, limit=args.limit,
                                  dry_run=args.dry_run, root=root)

    if changed:
        write_csv(csv_path, fieldnames, rows)
        updates = {str(r["question_id"]): {
            "image_files": r["image_files"],
            "image_dir": r["image_dir"],
            "image_count": r["image_count"],
            "has_images": True,
        } for r in changed}
        if jsonl_path.exists():
            write_jsonl(jsonl_path, updates)

    print(f"rows updated     : {len(changed) if not args.dry_run else stats['rows']}")
    print(f"images copied    : {stats['copied']}")
    print(f"images downloaded: {stats['downloaded']}")
    print(f"images failed    : {stats['failed']}")
    for qid, url, err in stats["failures"]:
        print(f"  {qid} {url}: {err}")
    return 1 if stats["failed"] else 0


def main(argv=None, fetcher=None):
    args = build_parser().parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    return run(args, fetcher=fetcher)


if __name__ == "__main__":
    raise SystemExit(main())
