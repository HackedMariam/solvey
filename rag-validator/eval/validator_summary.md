# Validator repeated evaluation summary

Dataset: 28 simulated answer/ticket dossiers. Each prompt/model pair was run 3 times. Groq was pinned as the only judge provider; no provider fallback was allowed. Standard deviations are sample standard deviations (`n=3`). Per-case JSON logs are intentionally kept under the ignored `eval/results/validator_runs/` directory and are not committed.

| Groq judge model | Prompt | Accuracy (mean ± SD) | False approves (mean ± SD) | False rejections (mean ± SD) | Failure-type accuracy (mean ± SD) | Judge errors (mean ± SD) | Per-run accuracy |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `openai/gpt-oss-120b` | v1 | 0.917 ± 0.021 | 0.333 ± 0.577 | 1.000 ± 0.000 | 0.917 ± 0.021 | 1.000 ± 0.000 | 0.893, 0.929, 0.929 |
| `openai/gpt-oss-120b` | v2 | 1.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 1.000 ± 0.000 | 0.000 ± 0.000 | 1.000, 1.000, 1.000 |
| `openai/gpt-oss-20b` | v1 | 0.762 ± 0.021 | 0.000 ± 0.000 | 5.000 ± 0.000 | 0.762 ± 0.021 | 6.000 ± 0.000 | 0.786, 0.750, 0.750 |
| `openai/gpt-oss-20b` | v2 | 0.917 ± 0.021 | 0.000 ± 0.000 | 1.000 ± 0.000 | 0.917 ± 0.021 | 1.333 ± 0.577 | 0.929, 0.929, 0.893 |

## Pooled confusion counts

### `openai/gpt-oss-120b` / v1

| Expected \ Actual | approve | retry_retrieval | regenerate | clarify | escalate |
|---|---|---|---|---|---|
| approve | 15 | 0 | 0 | 0 | 3 |
| retry_retrieval | 0 | 3 | 0 | 0 | 0 |
| regenerate | 1 | 3 | 41 | 0 | 0 |
| clarify | 0 | 0 | 0 | 3 | 0 |
| escalate | 0 | 0 | 0 | 0 | 15 |

### `openai/gpt-oss-120b` / v2

| Expected \ Actual | approve | retry_retrieval | regenerate | clarify | escalate |
|---|---|---|---|---|---|
| approve | 18 | 0 | 0 | 0 | 0 |
| retry_retrieval | 0 | 3 | 0 | 0 | 0 |
| regenerate | 0 | 0 | 45 | 0 | 0 |
| clarify | 0 | 0 | 0 | 3 | 0 |
| escalate | 0 | 0 | 0 | 0 | 15 |

### `openai/gpt-oss-20b` / v1

| Expected \ Actual | approve | retry_retrieval | regenerate | clarify | escalate |
|---|---|---|---|---|---|
| approve | 3 | 0 | 0 | 0 | 15 |
| retry_retrieval | 0 | 3 | 0 | 0 | 0 |
| regenerate | 0 | 0 | 40 | 0 | 5 |
| clarify | 0 | 0 | 0 | 3 | 0 |
| escalate | 0 | 0 | 0 | 0 | 15 |

### `openai/gpt-oss-20b` / v2

| Expected \ Actual | approve | retry_retrieval | regenerate | clarify | escalate |
|---|---|---|---|---|---|
| approve | 15 | 0 | 0 | 0 | 3 |
| retry_retrieval | 0 | 3 | 0 | 0 | 0 |
| regenerate | 0 | 0 | 41 | 0 | 4 |
| clarify | 0 | 0 | 0 | 3 | 0 |
| escalate | 0 | 0 | 0 | 0 | 15 |

## Interpretation

These are repeated measurements on one small, hand-authored test set, not independent estimates of production reliability. The per-run spread captures observed judge variability on these dossiers only. A zero false-approve count here does not establish a low real-world false-approve rate; expand and independently curate the test set before making that claim.
