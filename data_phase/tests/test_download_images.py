import csv
import json
from pathlib import Path

import download_images as di

FIELDNAMES = ["question_id", "title", "has_images", "image_count",
              "image_urls", "image_files", "image_dir", "source"]


def write_dataset(root, rows):
    ds = root / "dataset"
    ds.mkdir(parents=True, exist_ok=True)
    with open(ds / "so_dataset.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    with open(ds / "so_dataset.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def read_csv(root):
    with open(root / "dataset" / "so_dataset.csv", encoding="utf-8", newline="") as f:
        return {r["question_id"]: r for r in csv.DictReader(f)}


def read_jsonl(root):
    with open(root / "dataset" / "so_dataset.jsonl", encoding="utf-8") as f:
        return {str(r["question_id"]): r for r in map(json.loads, f)}


def test_image_filename_conventions():
    assert di.image_filename("71404275", 0, "https://i.sstatic.net/l9aOA.png") == \
        "so_71404275_0.png"
    assert di.image_filename("1", 2, "https://i.sstatic.net/a.jpg?raw=1") == "so_1_2.jpg"
    assert di.image_filename("1", 0, "https://i.sstatic.net/a.bmp") == "so_1_0.png"


def test_plan_row_skips_rows_that_are_already_local(tmp_path):
    images = tmp_path / "dataset" / "images"
    (images / "so_7_0.png").parent.mkdir(parents=True)
    (images / "so_7_0.png").write_bytes(b"png")
    row = {"question_id": "7", "image_urls": "https://i.sstatic.net/x.png",
           "image_files": "so_7_0.png", "image_dir": "dataset/images"}
    assert di.plan_row(row, images, root=tmp_path) is None


def test_plan_row_copies_local_files_and_flags_missing_downloads(tmp_path):
    baseline = tmp_path / "with resolution" / "images"
    baseline.mkdir(parents=True)
    (baseline / "so_9_0.png").write_bytes(b"png")
    row = {"question_id": "9",
           "image_urls": "https://i.sstatic.net/x.png;https://i.sstatic.net/y.png",
           "image_files": "so_9_0.png", "image_dir": "with resolution/images"}
    plan = di.plan_row(row, tmp_path / "dataset" / "images", root=tmp_path)
    assert [name for name, _ in plan["copies"]] == ["so_9_0.png"]
    assert [name for _, _, name in plan["downloads"]] == ["so_9_1.png"]


def test_run_downloads_missing_images_and_updates_dataset(tmp_path):
    write_dataset(tmp_path, [
        {"question_id": "111", "title": "api row", "has_images": "True",
         "image_count": "2",
         "image_urls": "https://img/one.png;https://img/two.png",
         "image_files": "", "image_dir": "", "source": "api"},
        {"question_id": "222", "title": "baseline row", "has_images": "True",
         "image_count": "1", "image_urls": "https://img/base.png",
         "image_files": "so_222_0.png", "image_dir": "with resolution/images",
         "source": "baseline"},
    ])
    baseline = tmp_path / "with resolution" / "images"
    baseline.mkdir(parents=True)
    (baseline / "so_222_0.png").write_bytes(b"png")

    calls = []

    def fetcher(url, dest):
        calls.append(url)
        dest.write_bytes(b"img")
        return True, None

    code = di.main(["--root", str(tmp_path)], fetcher=fetcher)

    assert code == 0
    assert calls == ["https://img/one.png", "https://img/two.png"]
    images = tmp_path / "dataset" / "images"
    assert (images / "so_111_0.png").read_bytes() == b"img"
    assert (images / "so_111_1.png").read_bytes() == b"img"

    rows = read_csv(tmp_path)
    assert rows["111"]["image_files"] == "so_111_0.png;so_111_1.png"
    assert rows["111"]["image_dir"] == "dataset/images"
    assert rows["111"]["image_count"] == "2"
    assert rows["222"]["image_dir"] == "with resolution/images"

    record = read_jsonl(tmp_path)["111"]
    assert record["image_dir"] == "dataset/images"
    assert record["image_files"] == "so_111_0.png;so_111_1.png"
    assert record["has_images"] is True
    assert record["title"] == "api row"


def test_run_reports_failures_and_leaves_row_untouched(tmp_path):
    write_dataset(tmp_path, [
        {"question_id": "5", "title": "broken", "has_images": "True",
         "image_count": "1", "image_urls": "https://img/gone.png",
         "image_files": "", "image_dir": "", "source": "api"},
    ])

    def fetcher(url, dest):
        return False, "404"

    code = di.main(["--root", str(tmp_path)], fetcher=fetcher)

    assert code == 1
    row = read_csv(tmp_path)["5"]
    assert row["image_files"] == ""
    assert row["image_dir"] == ""


def test_dry_run_fetches_nothing(tmp_path):
    write_dataset(tmp_path, [
        {"question_id": "5", "title": "pending", "has_images": "True",
         "image_count": "1", "image_urls": "https://img/x.png",
         "image_files": "", "image_dir": "", "source": "api"},
    ])

    def fetcher(url, dest):
        raise AssertionError("dry run must not download")

    code = di.main(["--root", str(tmp_path), "--dry-run"], fetcher=fetcher)

    assert code == 0
    assert not (tmp_path / "dataset" / "images").exists()
    assert read_csv(tmp_path)["5"]["image_files"] == ""
