# Phase 2 — retrieval evaluation

## Protocol

Evaluated the 30 queries in `eval/test_queries_draft.csv` against both indexed
collections using OpenAI `text-embedding-3-small` (1,536 dimensions) for query
embeddings and top-5 Qdrant similarity search. Each query was searched once
without a category constraint and once with an exact `category` payload filter.
The answerable-query metrics count an expected source as retrieved when its
manifest path occurs anywhere in the top *k* results. MRR is the mean
reciprocal rank of that exact source. The three `no_answer` examples have no
expected source and are excluded from Recall/MRR; their scores are measured
separately for abstention analysis.

## Overall results

| Strategy | Category filter | Recall@1 | Recall@3 | Recall@5 | MRR |
| --- | --- | ---: | ---: | ---: | ---: |
| A — `it_kb_recursive` | No | 0.741 | 0.815 | 0.889 | 0.790 |
| A — `it_kb_recursive` | Yes | 0.741 | 0.815 | 0.889 | 0.790 |
| B — `it_kb_blocks` | No | 0.778 | 0.852 | 0.926 | 0.825 |
| B — `it_kb_blocks` | Yes | **0.778** | **0.889** | **0.926** | **0.828** |

The denominator is 27 answerable queries. The A/B comparison is paired under
the same retrieval conditions: A filtered is compared with B filtered, and A
unfiltered with B unfiltered. In the unfiltered comparison, B gains one
answerable query at each of Recall@1/3/5; in the filtered comparison, B gains
one at Recall@1 and Recall@5 and two at Recall@3. **écart de 1-2 requêtes sur 27, tendance à confirmer**.

## Results by query type

Recall columns are calculated only for answerable types. The `no_answer` row
reports top-score behavior, not source retrieval.

| Strategy | Filter | Type | n | Recall@1 | Recall@3 | Recall@5 | MRR | No-answer top-score mean / max | Above threshold |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | No | paraphrase | 21 | 0.714 | 0.810 | 0.857 | 0.766 | — | — |
| A | No | table | 4 | 0.750 | 0.750 | 1.000 | 0.812 | — | — |
| A | No | exact_title | 2 | 1.000 | 1.000 | 1.000 | 1.000 | — | — |
| A | No | no_answer | 3 | — | — | — | — | 0.477 / 0.518 | 0 / 3 |
| A | Yes | paraphrase | 21 | 0.714 | 0.810 | 0.857 | 0.766 | — | — |
| A | Yes | table | 4 | 0.750 | 0.750 | 1.000 | 0.812 | — | — |
| A | Yes | exact_title | 2 | 1.000 | 1.000 | 1.000 | 1.000 | — | — |
| A | Yes | no_answer | 3 | — | — | — | — | 0.426 / 0.482 | 0 / 3 |
| B | No | paraphrase | 21 | 0.762 | 0.857 | 0.905 | 0.811 | — | — |
| B | No | table | 4 | 0.750 | 0.750 | 1.000 | 0.812 | — | — |
| B | No | exact_title | 2 | 1.000 | 1.000 | 1.000 | 1.000 | — | — |
| B | No | no_answer | 3 | — | — | — | — | 0.473 / 0.522 | 0 / 3 |
| B | Yes | paraphrase | 21 | 0.762 | 0.857 | 0.905 | 0.811 | — | — |
| B | Yes | table | 4 | 0.750 | 1.000 | 1.000 | 0.833 | — | — |
| B | Yes | exact_title | 2 | 1.000 | 1.000 | 1.000 | 1.000 | — | — |
| B | Yes | no_answer | 3 | — | — | — | — | 0.430 / 0.473 | 0 / 3 |

## Score distributions and abstention threshold

Scores are cosine similarities for each query's top-1 result. Thresholds were
selected separately for each strategy/filter combination by maximizing
balanced accuracy on these 30 queries; a result is accepted at or above the
threshold, otherwise the system abstains. `TP` means an answerable query is
accepted; `TN` means a no-answer query is correctly rejected.

| Strategy | Filter | Answerable min / median / mean / max | No-answer min / median / mean / max | Threshold | Balanced accuracy | TP | False accept | TN | False abstain |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | No | 0.424 / 0.638 / 0.637 / 0.814 | 0.432 / 0.482 / 0.477 / 0.518 | 0.5197 | 0.926 | 23 | 0 | 3 | 4 |
| A | Yes | 0.424 / 0.638 / 0.637 / 0.814 | 0.329 / 0.467 / 0.426 / 0.482 | 0.4860 | **0.981** | 26 | 0 | 3 | 1 |
| B | No | 0.421 / 0.666 / 0.660 / 0.859 | 0.424 / 0.473 / 0.473 / 0.522 | 0.5524 | 0.907 | 22 | 0 | 3 | 5 |
| B | Yes | 0.405 / 0.666 / 0.659 / 0.859 | 0.361 / 0.457 / 0.430 / 0.473 | **0.4805** | 0.963 | 25 | 0 | 3 | 2 |

For the recommended B + category-filtered setup, threshold `0.4805` correctly
abstains on all three no-answer queries and accepts 25 of 27 answerable queries.
It would also abstain on A03 (score `0.4705`) and N06 (score `0.4053`), despite
their expected source occurring in the retrieved top five. This illustrates
that a similarity cutoff can suppress useful evidence as well as false hits.
The score ranges overlap: the lowest answerable score is below the highest
no-answer score, so no threshold perfectly separates all examples.

The proposed operational retrieval cutoff of `0.30` is intentionally much
lower than the empirically selected abstention cutoffs above. Under B with a
category filter, the lowest observed top score is `0.4053`; therefore `0.30`
would not reject any of the 30 observed queries, including the three
no-answer examples. It only removes obviously weak matches below that level
and is not a no-answer classifier. The Validator, using the retrieved
evidence, remains responsible for deciding whether to answer or abstain.

## Failure analysis

- **A misses three expected documents in its top five:** N05, a VPN
  authentication question, ranks an unrelated Windows wireless-authentication
  article first; A05 retrieves related but non-expected Microsoft sign-in
  documents; O01 returns a repeated-update article instead of the expected
  common Windows Update errors guide.
- **B misses two expected documents in its top five:** A05 again retrieves
  adjacent but different sign-in guidance, and O01 returns a Windows 10
  upgrade-error-code article rather than the general update-errors source.
- **No-answer queries still retrieve plausible neighbors:** E07 matches VPN
  dial-up error content, S01 matches an Excel blank-window issue, and S02
  matches Windows Update/Office activation troubleshooting. With the selected
  cutoffs, all three are rejected, but three negatives are far too few to
  establish general no-answer performance.
- **Filtering has mixed effects:** it makes no aggregate difference to A,
  improves B's table Recall@3 from 0.750 to 1.000, and reduces the strongest
  no-answer top score in B from 0.522 to 0.473. It does not remedy the A05 or
  O01 source-selection failures.
- **Table questions remain a small sample:** all four find the expected source
  by rank five in both strategies, but one N06 table query is low-scoring in
  filtered B and would be abstained at the chosen cutoff.

## Recommendation

Use **B (`it_kb_blocks`) with the exact category filter** as the current
retrieval strategy: it has the best Recall@3/5 and MRR among the four tested
conditions and preserves the atomic table handling measured in phase 1. Treat
`0.4805` as a provisional abstention threshold, not a production guarantee.
The threshold was selected and assessed on the same small 30-query set,
including only three no-answer examples; collect a larger independent,
category-balanced validation set before fixing a production threshold. Review
N05, A05, O01, and the low-score N06 result when expanding that set.

The evaluation runner is `eval/evaluate_retrieval.py`. Its detailed JSON
results are written to the ignored `eval/results/retrieval_results.json`;
rerun `python eval/evaluate_retrieval.py` from `rag-validator` to reproduce the
per-query progress and metrics. This Markdown analysis is the versioned
retrieval evaluation summary; the per-query JSON log is intentionally not
committed.
