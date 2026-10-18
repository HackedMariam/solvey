"""Solvey dataset pipeline: reuse baseline, collect, classify, balance, export.

Never writes into the baseline folders (``so_bug_data/``, ``with resolution/``);
all new artifacts go under the output directory (default ``dataset/``).
"""

import csv
import json
import logging
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .apiclient import QuotaExceededError, StackExchangeClient
from .classify import classify_difficulty, relevance_score
from .coverage import (build_coverage, coverage_to_rows, difficulty_counts,
                       render_markdown, resolution_by_difficulty, resolution_counts)
from .dedupe import DedupeRegistry
from .taxonomy import (ALL_SUBCATEGORIES, CATEGORY_TAXONOMY, DIFFICULTY_LEVELS,
                       LEGACY_SUBCATEGORY_ALIASES, SUBCATEGORY_TO_CATEGORY,
                       TARGET_PER_CELL, all_specs_for, gap_fill_specs_for)
from .textutils import extract_images_from_html, html_to_text, unescape_title

log = logging.getLogger("so_pipeline")

BASELINE_CSV = os.path.join("with resolution", "results.csv")
BASELINE_IMAGE_DIR = os.path.join("with resolution", "images")

FIELDNAMES = [
    "question_id", "question_url", "link", "title", "description", "body_html",
    "tags", "category", "subcategory",
    "difficulty", "difficulty_confidence", "difficulty_evidence",
    "difficulty_hard_score", "difficulty_easy_score", "needs_review",
    "resolution_status", "has_answer", "answer_id", "answer_score", "answer_link",
    "answer_owner", "answer_creation_date", "resolution", "answer_body_html",
    "has_images", "image_count", "image_urls", "image_files", "image_dir",
    "source", "relevance_score", "relevance_signals", "collection_specs",
    "score", "view_count", "answer_count", "creation_date",
]


def pick_resolution(answers):
    """Same convention as the baseline scraper: accepted first, else top-voted."""
    if not answers:
        return None, "none"
    for ans in answers:
        if ans.get("is_accepted"):
            return ans, "accepted"
    return answers[0], "top_voted"


def load_baseline(baseline_csv, project_root="."):
    """Load the preserved baseline dataset and classify difficulties for it."""
    path = Path(project_root) / baseline_csv
    records = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            subcat = LEGACY_SUBCATEGORY_ALIASES.get(row["subcategory"], row["subcategory"])
            if subcat not in SUBCATEGORY_TO_CATEGORY:
                log.warning("baseline subcategory not in taxonomy, skipped: %s", row["subcategory"])
                continue
            diff = classify_difficulty(row.get("title"), row.get("description"),
                                       _split_tags(row.get("tags")),
                                       row.get("resolution", ""))
            rel, rel_signals = relevance_score(subcat, row.get("title"),
                                               row.get("description"),
                                               _split_tags(row.get("tags")))
            image_urls = _split_semi(row.get("image_urls"))
            image_files = _split_semi(row.get("image_files"))
            records.append({
                "question_id": str(row["question_id"]),
                "question_url": row.get("link", ""),
                "link": row.get("link", ""),
                "title": row.get("title", ""),
                "description": row.get("description", ""),
                "body_html": row.get("body_html", ""),
                "tags": row.get("tags", ""),
                "category": SUBCATEGORY_TO_CATEGORY[subcat],
                "subcategory": subcat,
                "difficulty": diff.label,
                "difficulty_confidence": diff.confidence,
                "difficulty_evidence": ";".join(diff.evidence),
                "difficulty_hard_score": diff.hard_score,
                "difficulty_easy_score": diff.easy_score,
                "needs_review": diff.needs_review,
                "resolution_status": row.get("resolution_status", "none"),
                "has_answer": _as_bool(row.get("has_answer")),
                "answer_id": row.get("answer_id", ""),
                "answer_score": row.get("answer_score", ""),
                "answer_link": row.get("answer_link", ""),
                "answer_owner": row.get("answer_owner", ""),
                "answer_creation_date": row.get("answer_creation_date", ""),
                "resolution": row.get("resolution", ""),
                "answer_body_html": row.get("answer_body_html", ""),
                "has_images": bool(image_urls) or bool(image_files),
                "image_count": int(row.get("image_count") or 0),
                "image_urls": ";".join(image_urls),
                "image_files": ";".join(image_files),
                "image_dir": BASELINE_IMAGE_DIR if image_files else "",
                "source": "baseline",
                "relevance_score": rel,
                "relevance_signals": ";".join(rel_signals),
                "collection_specs": "baseline",
                "score": row.get("score", 0),
                "view_count": row.get("view_count", 0),
                "answer_count": row.get("answer_count", 0),
                "creation_date": row.get("creation_date", 0),
            })
    return records


def _split_tags(value):
    return [t for t in (value or "").split(";") if t]


def _split_semi(value):
    return [v for v in (value or "").split(";") if v]


def _as_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def _coerce_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coerce_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _coerce_kept_row(row):
    """Restore native types on rows re-read from a previous CSV export."""
    row["has_images"] = _as_bool(row.get("has_images"))
    row["needs_review"] = _as_bool(row.get("needs_review"))
    row["question_id"] = str(row.get("question_id", ""))
    for key in ("image_count", "difficulty_hard_score", "difficulty_easy_score"):
        row[key] = _coerce_int(row.get(key))
    row["difficulty_confidence"] = _coerce_float(row.get("difficulty_confidence"))
    return row


def _read_csv_rows(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _merge_report_rows(previous, current, key_fields):
    """Union of prior + current audit rows, preserving order and dropping repeats."""
    merged = list(previous)
    seen = {tuple(str(r.get(k, "")) for k in key_fields) for r in previous}
    for row in current:
        key = tuple(str(row.get(k, "")) for k in key_fields)
        if key not in seen:
            seen.add(key)
            merged.append(row)
    return merged


def candidate_from_api_item(item, subcat, spec_label, rel, rel_signals):
    """Normalize one raw API question item into a pipeline candidate record."""
    qid = str(item.get("question_id"))
    title = unescape_title(item.get("title"))
    body_html = item.get("body", "") or ""
    image_urls = [url for url, _ in extract_images_from_html(body_html, qid)]
    return {
        "question_id": qid,
        "question_url": item.get("link", ""),
        "link": item.get("link", ""),
        "title": title,
        "description": html_to_text(body_html),
        "body_html": body_html,
        "tags": ";".join(item.get("tags", []) or []),
        "category": SUBCATEGORY_TO_CATEGORY[subcat],
        "subcategory": subcat,
        "resolution_status": "none",
        "has_answer": False,
        "answer_id": "", "answer_score": "", "answer_link": "", "answer_owner": "",
        "answer_creation_date": "", "resolution": "", "answer_body_html": "",
        "has_images": bool(image_urls),
        "image_count": len(image_urls),
        "image_urls": ";".join(image_urls),
        "image_files": "",
        "image_dir": "",
        "source": "api",
        "relevance_score": rel,
        "relevance_signals": ";".join(rel_signals),
        "collection_specs": spec_label,
        "score": item.get("score", 0),
        "view_count": item.get("view_count", 0),
        "answer_count": item.get("answer_count", 0),
        "creation_date": item.get("creation_date", 0),
    }


def attach_resolution(candidate, answers):
    ans, status = pick_resolution(answers)
    candidate["resolution_status"] = status
    candidate["has_answer"] = bool(ans)
    if ans:
        candidate["answer_id"] = ans.get("answer_id", "")
        candidate["answer_score"] = ans.get("score", "")
        candidate["answer_link"] = (ans.get("link")
                                    or f"https://stackoverflow.com/a/{ans.get('answer_id')}")
        candidate["answer_owner"] = ans.get("owner", {}).get("display_name", "")
        candidate["answer_creation_date"] = ans.get("creation_date", "")
        candidate["resolution"] = html_to_text(ans.get("body", ""))
        candidate["answer_body_html"] = ans.get("body", "") or ""


def classify_candidate(candidate):
    diff = classify_difficulty(candidate.get("title"), candidate.get("description"),
                               _split_tags(candidate.get("tags")),
                               candidate.get("resolution", ""))
    candidate["difficulty"] = diff.label
    candidate["difficulty_confidence"] = diff.confidence
    candidate["difficulty_evidence"] = ";".join(diff.evidence)
    candidate["difficulty_hard_score"] = diff.hard_score
    candidate["difficulty_easy_score"] = diff.easy_score
    candidate["needs_review"] = diff.needs_review


def select_for_subcategory(baseline_counts, candidates, target=TARGET_PER_CELL):
    """Fill each difficulty cell up to ``target``; prioritize resolution_status=none
    (60% of each need) but keep resolved questions as comparison examples.

    Returns (selected, leftover, mix_stats).
    """
    selected, leftover = [], []
    mix_stats = {"none": 0, "accepted": 0, "top_voted": 0}
    by_diff = defaultdict(list)
    for c in candidates:
        by_diff[c["difficulty"]].append(c)

    for diff in DIFFICULTY_LEVELS:
        pool = by_diff.get(diff, [])
        need = max(0, target - baseline_counts.get(diff, 0))
        if need == 0 or not pool:
            leftover.extend(pool)
            continue
        nones = sorted((c for c in pool if c["resolution_status"] == "none"),
                       key=lambda c: (-c["difficulty_confidence"], -int(c["score"] or 0)))
        resolved = sorted(
            (c for c in pool if c["resolution_status"] != "none"),
            key=lambda c: (0 if c["resolution_status"] == "accepted" else 1,
                           -c["difficulty_confidence"], -int(c["score"] or 0)))
        if nones and resolved:
            need_none = min(len(nones), max(1, round(need * 0.6)))
        else:
            need_none = min(len(nones), need)
        chosen = nones[:need_none] + resolved[:need - need_none]
        if len(chosen) < need:
            chosen_ids = {c["question_id"] for c in chosen}
            rest = sorted((c for c in pool if c["question_id"] not in chosen_ids),
                          key=lambda c: (-c["difficulty_confidence"], -int(c["score"] or 0)))
            chosen += rest[:need - len(chosen)]
        chosen_ids = {c["question_id"] for c in chosen}
        leftover.extend(c for c in pool if c["question_id"] not in chosen_ids)
        for c in chosen:
            mix_stats[c["resolution_status"]] = mix_stats.get(c["resolution_status"], 0) + 1
        selected.extend(chosen)
    return selected, leftover, mix_stats


def download_images_for_records(client, records, images_dir):
    """Download screenshot URLs for the given records (existing design of the
    baseline scraper). Returns number of files written."""
    images_dir = Path(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    session = client.session
    for rec in records:
        urls = _split_semi(rec.get("image_urls"))
        if not urls:
            continue
        files = []
        for idx, url in enumerate(urls):
            ext = os.path.splitext(url.split("?")[0])[1].lower()
            if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                ext = ".png"
            fname = f"so_{rec['question_id']}_{idx}{ext}"
            fpath = images_dir / fname
            if fpath.exists():
                files.append(fname)
                continue
            try:
                resp = session.get(url, timeout=30, stream=True)
                resp.raise_for_status()
                if "image" not in resp.headers.get("Content-Type", "").lower():
                    continue
                with open(fpath, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                files.append(fname)
                written += 1
            except Exception as e:  # noqa: BLE001 - record and continue
                log.warning("image download failed %s: %s", url, e)
            time.sleep(0.1)
        rec["image_files"] = ";".join(files)
        rec["image_dir"] = str(images_dir)
        rec["image_count"] = len(files) if files else rec.get("image_count", 0)
    return written


def run_pipeline(args):
    """End-to-end pipeline. Returns dict with paths and summary stats."""
    started = datetime.now(timezone.utc)
    project_root = Path(args.project_root)
    out = project_root / args.output_dir
    raw_dir = out / "raw"
    reports_dir = out / "reports"
    cache_dir = raw_dir / "api_cache"
    for d in (out, raw_dir, reports_dir, cache_dir):
        d.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get("API_KEY")
    if not api_key:
        raise SystemExit("API_KEY not set. Add API_KEY=... to your .env file.")

    client = StackExchangeClient(api_key, cache_dir, refresh=args.refresh_cache,
                                 min_quota=args.min_quota)

    # ------------------------------------------------------------------ baseline
    baseline = load_baseline(BASELINE_CSV, project_root)
    baseline_ids = {r["question_id"] for r in baseline}
    log.info("baseline loaded: %d records from %s", len(baseline), BASELINE_CSV)

    registry = DedupeRegistry()
    for r in baseline:
        registry.add(r["question_id"], r["link"], r["title"])

    # In fill-gaps mode, keep the previously exported API rows and never re-collect
    # them. Baseline rows stay the canonical copy of the 100 seed records.
    records_existing_api = []   # previously collected API rows (fill-gaps mode only)
    baseline_ids_from_csv = set(baseline_ids)
    if args.fill_gaps:
        existing_csv = out / "so_dataset.csv"
        kept_existing = 0
        if existing_csv.exists():
            with open(existing_csv, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row.get("source") != "api":
                        continue
                    qid = str(row.get("question_id", ""))
                    if not qid or qid in registry.by_id:
                        continue
                    registry.add(qid, row.get("link", ""), row.get("title", ""))
                    records_existing_api.append(_coerce_kept_row(row))
                    kept_existing += 1
        log.info("fill-gaps: keeping %d existing API rows, registry size %d",
                 kept_existing, len(registry))

    # In fill-gaps mode, carry forward the audit trail so a no-op rerun does not
    # erase the exclusions/duplicates recorded by the original collection runs.
    prev_api_cumulative = {"calls": 0, "cache_hits": 0, "duplicates": 0}
    prev_dup_report = []
    prev_exclusions = []
    if args.fill_gaps:
        prev_report_path = reports_dir / "collection_report.json"
        if prev_report_path.exists():
            try:
                prev_report = json.loads(prev_report_path.read_text(encoding="utf-8"))
                prev_api_cumulative = dict(prev_report.get("api", {}).get(
                    "cumulative", {"calls": prev_report.get("api", {}).get("calls", 0),
                                   "cache_hits": prev_report.get("api", {}).get("cache_hits", 0),
                                   "duplicates": 0}))
            except (json.JSONDecodeError, OSError):
                prev_report = None
        prev_dup_report = _read_csv_rows(reports_dir / "duplicates.csv")
        prev_exclusions = _read_csv_rows(reports_dir / "exclusions.csv")

    records = list(baseline)
    exclusions = []      # rows for exclusions.csv
    dup_report = []      # rows for duplicates.csv
    subcat_stats = {}

    target_subcats = (args.subcats.split("|") if args.subcats
                      else list(ALL_SUBCATEGORIES))
    if args.pilot:
        target_subcats = target_subcats[: args.pilot_subcats]

    for name in target_subcats:
        if name not in SUBCATEGORY_TO_CATEGORY:
            log.warning("unknown subcategory skipped: %s", name)
            continue

    # ------------------------------------------------------- tag validation
    all_tags = set()
    for name in target_subcats:
        for spec in all_specs_for(name):
            if spec.kind == "tagged":
                all_tags.update(spec.value.split(";"))
    valid_tags, invalid_tags = client.validate_tags(sorted(all_tags))
    valid_tag_set = set(valid_tags)
    if invalid_tags:
        log.info("dropping %d invalid tags: %s", len(invalid_tags), ", ".join(invalid_tags))

    baseline_by_subcat = defaultdict(list)
    for r in baseline:
        baseline_by_subcat[r["subcategory"]].append(r)
    baseline_cell_counts = Counter((r["subcategory"], r["difficulty"]) for r in baseline)

    # Seed occupied cells with baseline + (fill mode) previously exported API rows.
    seed_cell_counts = Counter(baseline_cell_counts)
    for r in records_existing_api:
        seed_cell_counts[(r.get("subcategory"), r.get("difficulty"))] += 1

    aborted = False
    assigned = {}                      # qid -> subcategory
    globally_rejected = set()          # qids excluded everywhere (duplicates)
    relevance_rejected = defaultdict(set)  # qid -> subcats that found it irrelevant
    raw_pool_records = []              # every accepted API candidate (selected or not)

    # ------------------------------------------------------------------ collect
    for name in target_subcats:
        # Difficulty cells still needing rows for this subcategory.
        cell_needs = {
            d: max(0, args.target_per_cell - seed_cell_counts.get((name, d), 0))
            for d in DIFFICULTY_LEVELS
        }
        if not any(cell_needs.values()):
            log.info("[%s] already at target in all cells, skipping", name)
            continue

        # Spec plan: gap-fill (difficulty-biased) first, then the generic search plan.
        spec_plan = []  # list of (spec, target_difficulty_or_None)
        for spec, want_diff in gap_fill_specs_for(name):
            if cell_needs.get(want_diff, 0) > 0:
                spec_plan.append((spec, want_diff))
        for spec in all_specs_for(name):
            spec_plan.append((spec, None))
        if args.specs_limit:
            spec_plan = spec_plan[: args.specs_limit]

        pool = []
        stats = {"specs_run": 0, "pages_fetched": 0, "candidates": 0,
                 "low_relevance": 0, "duplicates": 0}
        try:
            for spec, want_diff in spec_plan:
                if len(pool) >= args.max_candidates_per_subcat:
                    break
                if client.quota_remaining is not None and client.quota_remaining < args.min_quota:
                    log.warning("quota low (%s), aborting collection", client.quota_remaining)
                    aborted = True
                    break

                # skip specs whose tags were all invalidated
                if spec.kind == "tagged" and not (set(spec.value.split(";")) & valid_tag_set):
                    log.info("  skip spec (invalid tags): %s", spec.label())
                    continue

                want_tag = f" -> {want_diff}" if want_diff else ""
                log.info("[%s] search: %s%s", name, spec.label(), want_tag)
                items, pages, has_more = client.search_spec(spec, max_pages=args.max_pages_per_spec)
                stats["specs_run"] += 1
                stats["pages_fetched"] += pages
                if items is None:
                    items = []

                new_in_spec = 0
                for item in items:
                    if len(pool) >= args.max_candidates_per_subcat:
                        break
                    qid = str(item.get("question_id"))
                    if qid in baseline_ids or qid in assigned or qid in globally_rejected:
                        continue
                    if name in relevance_rejected[qid]:
                        continue
                    title = unescape_title(item.get("title"))
                    desc = html_to_text(item.get("body", ""))
                    tags = item.get("tags", []) or []
                    rel, rel_signals = relevance_score(name, title, desc, tags)
                    if rel < 3:
                        relevance_rejected[qid].add(name)
                        stats["low_relevance"] += 1
                        exclusions.append({
                            "question_id": qid, "title": title, "subcategory": name,
                            "reason": "low_relevance", "detail": f"relevance_score={rel}",
                        })
                        continue
                    hit = registry.check(qid, item.get("link", ""), title)
                    if hit:
                        globally_rejected.add(qid)
                        stats["duplicates"] += 1
                        dup_report.append({
                            "excluded_id": qid, "excluded_title": title,
                            "reason": hit.reason, "kept_id": hit.existing_id,
                            "detail": hit.detail, "found_under": name,
                        })
                        continue
                    registry.add(qid, item.get("link", ""), title)
                    assigned[qid] = name
                    cand = candidate_from_api_item(item, name, spec.label(), rel, rel_signals)
                    cand["_want_diff"] = want_diff
                    pool.append(cand)
                    raw_pool_records.append(cand)
                    new_in_spec += 1
                stats["candidates"] = len(pool)
                log.info("    +%d new candidates (pool=%d, has_more=%s)",
                         new_in_spec, len(pool), has_more)
                time.sleep(args.pause)
        except QuotaExceededError as e:
            log.warning("quota exceeded during %s: %s", name, e)
            aborted = True

        if aborted and not pool:
            subcat_stats[name] = stats
            break

        # -------------------------------------------------------- resolutions
        if pool:
            log.info("[%s] fetching answers for %d candidates...", name, len(pool))
            answers = client.get_answers([c["question_id"] for c in pool])
            for cand in pool:
                attach_resolution(cand, answers.get(int(cand["question_id"]),
                                                    answers.get(cand["question_id"], [])))
                classify_candidate(cand)

        # Selection counts occupied cells from baseline + kept rows (fill mode),
        # and in fill-gaps mode prefers candidates matching a still-empty cell.
        occupied = Counter({d: seed_cell_counts.get((name, d), 0) for d in DIFFICULTY_LEVELS})
        selected, leftover, mix = select_for_subcategory(
            occupied, pool, target=args.target_per_cell)
        for c in leftover:
            exclusions.append({
                "question_id": c["question_id"], "title": c["title"],
                "subcategory": name, "reason": "cell_quota_exceeded",
                "detail": f"difficulty={c['difficulty']} status={c['resolution_status']}",
            })
        stats["selected"] = len(selected)
        stats["resolution_mix"] = mix
        records.extend(selected)
        subcat_stats[name] = stats
        log.info("[%s] selected %d (mix=%s), leftover %d",
                 name, len(selected), mix, len(leftover))

        if aborted:
            break

    # keep previously collected API rows when filling gaps
    if args.fill_gaps and records_existing_api:
        records.extend(records_existing_api)

    # ------------------------------------------------------------------ export
    dataset_csv = out / "so_dataset.csv"
    dataset_jsonl = out / "so_dataset.jsonl"
    with open(dataset_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            writer.writerow({k: r.get(k, "") for k in FIELDNAMES})
    with open(dataset_jsonl, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps({k: r.get(k, "") for k in FIELDNAMES},
                               ensure_ascii=False) + "\n")

    raw_records_path = raw_dir / "records.jsonl"
    with open(raw_records_path, "w", encoding="utf-8") as f:
        for r in raw_pool_records:
            f.write(json.dumps({
                "question_id": r["question_id"], "link": r["link"], "title": r["title"],
                "tags": r["tags"], "subcategory": r["subcategory"],
                "relevance_score": r["relevance_score"],
                "collection_specs": r["collection_specs"],
                "body_html": r["body_html"],
            }, ensure_ascii=False) + "\n")

    cells = build_coverage(records, target_per_cell=args.target_per_cell)
    coverage_csv = reports_dir / "coverage_matrix.csv"
    with open(coverage_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["category", "subcategory", "difficulty",
                                               "target", "actual", "deficit"])
        writer.writeheader()
        writer.writerows(coverage_to_rows(cells))

    res_counts = resolution_counts(records)
    diff_counts = difficulty_counts(records)
    res_cross = resolution_by_difficulty(records)
    coverage_md = reports_dir / "coverage_matrix.md"
    coverage_md.write_text(render_markdown(cells, res_counts, diff_counts, res_cross),
                           encoding="utf-8")

    if args.fill_gaps:
        dup_report = _merge_report_rows(prev_dup_report, dup_report,
                                        ("excluded_id", "reason"))
        exclusions = _merge_report_rows(prev_exclusions, exclusions,
                                        ("question_id", "reason"))

    dup_csv = reports_dir / "duplicates.csv"
    with open(dup_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["excluded_id", "excluded_title", "reason",
                                               "kept_id", "detail", "found_under"])
        writer.writeheader()
        writer.writerows(dup_report)

    excl_csv = reports_dir / "exclusions.csv"
    with open(excl_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["question_id", "title", "subcategory",
                                               "reason", "detail"])
        writer.writeheader()
        writer.writerows(exclusions)

    images_downloaded = 0
    if args.download_images:
        images_downloaded = download_images_for_records(
            client, [r for r in records if r["source"] == "api" and r.get("image_urls")],
            out / "images")
        # re-export so updated image_files are persisted
        with open(dataset_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
            writer.writeheader()
            for r in records:
                writer.writerow({k: r.get(k, "") for k in FIELDNAMES})
        with open(dataset_jsonl, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps({k: r.get(k, "") for k in FIELDNAMES},
                                   ensure_ascii=False) + "\n")

    image_urls_total = sum(len(_split_semi(r.get("image_urls"))) for r in records)
    with_images = sum(1 for r in records if r.get("has_images") or _split_semi(r.get("image_urls")))
    gaps = [{"subcategory": c.subcategory, "difficulty": c.difficulty,
             "deficit": c.deficit} for c in cells if c.deficit > 0]
    report_path = reports_dir / "collection_report.json"

    report = {
        "generated_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "baseline": {
            "source": BASELINE_CSV,
            "rows": len(baseline),
            "resolution_status_counts": dict(Counter(r["resolution_status"] for r in baseline)),
            "note": "baseline files are preserved unchanged; rows reused with "
                    "normalized subcategory names and added difficulty labels",
        },
        "api": {
            "calls": client.api_calls,
            "cache_hits": client.cache_hits,
            "quota_max": client.quota_max,
            "quota_remaining": client.quota_remaining,
            "failures": client.failures,
            "invalid_tags_dropped": invalid_tags,
            "aborted_by_quota": aborted,
            "this_run": {
                "calls": client.api_calls,
                "cache_hits": client.cache_hits,
                "failures": len(client.failures),
            },
            "cumulative": {
                "calls": prev_api_cumulative.get("calls", 0) + client.api_calls,
                "cache_hits": prev_api_cumulative.get("cache_hits", 0) + client.cache_hits,
                "duplicates": len(dup_report),
            },
        },
        "collection": {
            "subcategories_targeted": target_subcats,
            "per_subcategory": subcat_stats,
            "raw_candidates_accepted": len(raw_pool_records),
        },
        "dataset": {
            "rows": len(records),
            "unique_question_ids": len({r["question_id"] for r in records}),
            "baseline_reused": len(baseline),
            "new_selected": len(records) - len(baseline),
            "synthetic_records": 0,
            "difficulty_counts": dict(diff_counts),
            "needs_review": sum(1 for r in records if r.get("needs_review")),
            "resolution_status_counts": dict(res_counts),
            "with_images": with_images,
            "image_urls_total": image_urls_total,
            "images_downloaded_this_run": images_downloaded,
        },
        "exclusions": {
            "low_relevance": sum(1 for e in exclusions if e["reason"] == "low_relevance"),
            "cell_quota_exceeded": sum(1 for e in exclusions if e["reason"] == "cell_quota_exceeded"),
            "duplicates": len(dup_report),
        },
        "coverage": {
            "cells": len(cells),
            "complete_cells": sum(1 for c in cells if c.deficit == 0),
            "total_actual": sum(c.actual for c in cells),
            "total_target": sum(c.target for c in cells),
            "gaps": gaps,
        },
        "outputs": {
            "dataset_csv": str(dataset_csv),
            "dataset_jsonl": str(dataset_jsonl),
            "raw_records_jsonl": str(raw_records_path),
            "api_cache_dir": str(cache_dir),
            "coverage_csv": str(coverage_csv),
            "coverage_md": str(coverage_md),
            "duplicates_csv": str(dup_csv),
            "exclusions_csv": str(excl_csv),
            "collection_report_json": str(report_path),
        },
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    log.info("dataset: %d rows (%d baseline + %d new), coverage %d/%d",
             len(records), len(baseline), len(records) - len(baseline),
             sum(c.actual for c in cells), sum(c.target for c in cells))
    return report
