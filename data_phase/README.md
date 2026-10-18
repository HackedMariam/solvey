# Solvey Dataset Pipeline

Extension of the existing Stack Overflow collectors (`scrape_so.py`, `scrape_so copy.py`).
It **reuses the preserved 100-row baseline** and collects additional real questions via the
official Stack Exchange API to build a balanced, auditable multimodal dataset.

Nothing in `so_bug_data/` or `with resolution/` is modified. All new artifacts are written to
`dataset/`.

Run the commands below from this folder (`cd data_phase`). The root `.env` is still found by
`python-dotenv` when working here.

## Requirements

- Python 3.12
- `pip install requests beautifulsoup4 python-dotenv pytest`
- A Stack Exchange API key in `.env` as `API_KEY=...`
  (register one at https://stackapps.com/apps/oauth/register — free, ~10,000 requests/day)

## Commands

```bash
# Run the tests (43 unit tests: taxonomy, dedup, classification, coverage, API client, images)
python -m pytest tests -q

# Pilot run: first 2 subcategories, small limits (validates end-to-end quickly)
python collect_dataset.py --pilot --max-pages-per-spec 1 --max-candidates-per-subcat 40

# Full collection toward the 1,500 target (resume-safe: reuses the API cache)
python collect_dataset.py

# Fill remaining gaps in an existing dataset (keeps prior rows, targets empty cells)
python collect_dataset.py --fill-gaps

# Validate the finished dataset (baseline, taxonomy, uniqueness, coverage, no synthetic rows)
python validate_dataset.py

# Target specific subcategories
python collect_dataset.py --subcats "Account locked|Driver problem"

# Also download screenshots for newly collected records
python collect_dataset.py --download-images

# Standalone: fetch every screenshot referenced by the dataset into dataset/images/
# (git-ignored, local-only; only touches dataset/so_dataset.csv + so_dataset.jsonl)
python download_images.py
```

`python -m so_pipeline ...` is equivalent to `python collect_dataset.py ...`.

### Resuming

Every API response is cached under `dataset/raw/api_cache/`. Re-running the pipeline replays
cached pages instead of re-hitting the API, so an interrupted run continues where it stopped and
never restarts from zero. Use `--refresh-cache` only if you deliberately want fresh API data.

`--fill-gaps` is the safest way to resume after a partial run: it re-reads the existing
`dataset/so_dataset.csv`, keeps every already-collected API row, and only searches for the
subcategory/difficulty cells still below target. Cells already at target are skipped without a
single API call. Audit artifacts (`duplicates.csv`, `exclusions.csv`) are carried forward across
fill-gaps runs, and the report tracks both per-run and cumulative API usage.

## Results

The dataset is complete and validated:

| Metric | Value |
|---|---|
| Dataset rows | **1,500** (100 baseline + 1,400 collected) |
| Unique question ids | 1,500 (no duplicates) |
| Coverage | **75/75 cells** complete, 20 per cell |
| Difficulty | hard 500 / medium 500 / easy 500 |
| Resolution | accepted 925 / top_voted 119 / none 456 |
| Multimodal | 195 records with images (300 image URLs) |
| Needs review | 864 flagged as ambiguous, with evidence + confidence kept |
| Synthetic rows | 0 — every row is a real Stack Overflow question |

`python validate_dataset.py` re-checks all of the above (28 assertions, including that the
baseline folders are untouched in git).

## What it does

1. **Reuses the baseline** — loads the 100 preserved rows from `with resolution/results.csv`,
   normalizes three legacy subcategory names into the required taxonomy, and adds a
   difficulty label to each. Baseline resolution text and screenshots are kept.
2. **Collects** — runs a per-subcategory search plan (full-text `q` searches, tag searches, and
   generated easy-biased queries) through `/search/advanced` and `/search`, paginating with
   `has_more`, honoring `backoff` and quota, and dropping API-invalid tags at runtime.
3. **Validates relevance** — every returned question is scored against a semantic profile for
   its subcategory; low-relevance results are excluded (see `exclusions.csv`).
4. **Deduplicates** — by question id, canonical URL, normalized title, and near-duplicate title
   against the baseline and all newly accepted records (see `duplicates.csv`).
5. **Classifies difficulty** — a rule-based classifier labels each question `easy`, `medium`, or
   `hard` from its title, body, error messages, code, tags, and resolution text. It never uses
   votes, views, age, answer count, or mere presence of a resolution. Each record stores its
   evidence, confidence, and a `needs_review` flag for ambiguous cases.
6. **Balances** — fills each of the 75 subcategory×difficulty cells up to the target (20 each),
   prioritizing `resolution_status = none` (~60% per need) while keeping resolved questions as
   comparison examples.
7. **Exports** — CSV + JSONL dataset, raw records, coverage matrix, resolution summary,
   duplicate/exclusion reports, and a JSON collection report.

## Difficulty rubric

- **easy** — common, narrowly scoped problem with a straightforward diagnostic or fix.
- **medium** — several diagnostic steps, log interpretation, or multiple plausible causes.
- **hard** — advanced debugging, system-component interaction, or complex root-cause analysis.

Classification is heuristic and auditable: each row's `difficulty_evidence` lists the matched
signals, `difficulty_confidence` gives a 0–1 score, and `needs_review` marks cases where the
evidence is mixed. These flags exist so ambiguous rows can be inspected rather than silently
trusted.

## Outputs (`dataset/`)

| Path | Description |
|---|---|
| `so_dataset.csv`, `so_dataset.jsonl` | Clean dataset (baseline reused + new records) |
| `raw/records.jsonl` | Raw accepted API candidates (pre-selection) |
| `raw/api_cache/` | Cached Stack Exchange API responses |
| `reports/coverage_matrix.csv`, `.md` | Target / actual / deficit for all 75 cells |
| `reports/collection_report.json` | API usage (`this_run` + `cumulative`), failures, exclusions, resolution + difficulty counts, gaps |
| `reports/duplicates.csv` | Excluded duplicates and the record kept instead (carried forward across fill-gaps runs) |
| `reports/exclusions.csv` | Low-relevance and over-quota exclusions (carried forward across fill-gaps runs) |

Columns include the baseline fields plus `question_url`, `category`, `subcategory`,
`difficulty`, `difficulty_confidence`, `difficulty_evidence`, `needs_review`, `has_images`,
`image_urls`, `image_dir`, `source`, `relevance_score`, and `collection_specs`. Original SO tags
are preserved in `tags`; each record still has exactly one primary subcategory and one
difficulty.

## Notes

- `resolution_status` follows the existing convention: `accepted` (accepted answer),
  `top_voted` (highest-voted answer chosen by the pipeline), `none` (no resolution found).
  `none` does **not** mean the question is unsolvable — only that no resolution was found.
- No records are fabricated. Every row traces to a real Stack Overflow question id and URL.
- The coverage report is the source of truth for what has and has not been filled; deficits are
  reported honestly rather than papered over.

## SFT notebook

`solvey_qwen25vl_sft_v2.ipynb` trains the Qwen2.5-VL QLoRA adapter from the exported dataset and
pushes it to the Hugging Face Hub. It expects the dataset mounted at the Kaggle input path defined
in its config cell.
