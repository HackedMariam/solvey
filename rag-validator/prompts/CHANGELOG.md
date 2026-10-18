# Validator prompt evaluation and change log

## Evaluation protocol

The same 28 simulated dossiers are used for every prompt/model run. Each
prompt/model pair is repeated three times. The judge is pinned to Groq with
provider fallback disabled. Accuracy, false approvals, false rejections,
failure-type accuracy, and invalid/error judge calls are reported as mean ±
sample standard deviation (`n=3`). Per-case reports are stored under the
Git-ignored `eval/results/validator_runs/`; the aggregate
[`eval/validator_summary.md`](../eval/validator_summary.md) is the committed
evaluation summary.

The requested `llama-3.1-8b-instant` is not available to the configured Groq
key (model-list omission and API 404). At the user's selection, the smaller
comparison uses `openai/gpt-oss-20b`, not an 8B model. The other judge is
`openai/gpt-oss-120b`.

## Versions and findings

| Groq model | Prompt | Accuracy (mean ± SD) | False approves (mean ± SD) | False rejections (mean ± SD) | Judge errors (mean ± SD) |
| --- | --- | ---: | ---: | ---: | ---: |
| `openai/gpt-oss-120b` | v1 baseline | 0.917 ± 0.021 | 0.333 ± 0.577 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| `openai/gpt-oss-120b` | v2 first pass | 0.940 ± 0.021 | 0.333 ± 0.577 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| `openai/gpt-oss-120b` | v2 corrected | **1.000 ± 0.000** | **0.000 ± 0.000** | **0.000 ± 0.000** | **0.000 ± 0.000** |
| `openai/gpt-oss-20b` | v1 baseline | 0.762 ± 0.021 | 0.000 ± 0.000 | 5.000 ± 0.000 | 6.000 ± 0.000 |
| `openai/gpt-oss-20b` | v2 first pass | 0.833 ± 0.021 | 1.333 ± 0.577 | 1.000 ± 0.000 | 0.667 ± 0.577 |
| `openai/gpt-oss-20b` | v2 corrected | **0.917 ± 0.021** | **0.000 ± 0.000** | 1.000 ± 0.000 | 1.333 ± 0.577 |

The first v2 pass raised accuracy on both models, but the 20B model's false
approvals increased to 1.333 per run on average. After tightening the
evidence/repair routing, corrected v2 scored 28/28 in all three 120B runs;
its accuracy rose from 0.940 to 1.000 and false approvals fell from 0.333
per run to zero. On the 20B model, corrected v2 raised accuracy from 0.833
to 0.917 and removed false approvals, but it still had one false rejection
and 1.333 invalid/error judge calls per run on average. Invalid or empty
judge outputs are recorded as evaluation errors and fail-closed `escalate`
decisions; they are not successful approvals.

The result supports **Groq `openai/gpt-oss-120b` with corrected v2** for this
test set, not a broad claim of reliability. The 20B model still struggles
with injection-heavy/user-text and ticket-consistency cases and should not be
substituted as if it were equivalent. Three repeated runs on 28 curated
dossiers cannot estimate production error rates.

## Corrective history

### v1 — concise baseline

Role: final workflow auditor, not a user-facing support agent. V1 checks
high-level grounding, safety, language, and ticket completeness; it treats
user, OCR, retrieved, and draft text as untrusted data and emits only the
decision JSON. The baseline was too broad for borderline evidence and did not
clearly distinguish correcting a bad draft from retrying retrieval.

### v2 — cross-stage and ticket-mode specificity

The first v2 pass added an explicit report → Vision → Triage → retrieval →
answer/ticket checklist, clarified that safe generic actions can be
appropriate, hardened the instruction/data boundary, and added a ticket
example where report/Vision evidence is sufficient without retrieved chunks.
That ticket-mode correction followed an observed false rejection:
`ticket-correct` was sent to retrieval retry even though the draft was a
factual human-review ticket.

The 28-case evaluation then surfaced three further patterns: unsupported
permanent guarantees could be approved; ticket contradictions were sometimes
routed to retrieval or escalation rather than draft correction; and a
partially supported answer could trigger the wrong failure route. The final
v2 text now states that every material claim and proposed fix must be
supported, unsupported guarantees/omissions require regeneration, ticket
contradictions require ticket regeneration, and retrieval retry is reserved
for weak/missing retrieval evidence in answer mode.

The corrected v2's final repeated metrics and confusion tables are recorded
in [`eval/validator_summary.md`](../eval/validator_summary.md). The data are
still a small, hand-authored challenge set, not a production error-rate
estimate. Expand it with independently authored and real de-identified
workflow cases before making a deployment-safety claim.
