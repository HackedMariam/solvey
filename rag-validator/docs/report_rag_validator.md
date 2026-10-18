# RAG Validator: corpus, retrieval, and final quality gate

## Scope and corpus

The project builds an IT-support retrieval corpus for five categories and a
final Validator that gates both user answers and escalation tickets. The
included manifest contains **249 documents**: 239 Microsoft support Markdown
articles and 10 PDFs. The category balance is:

| Category | Sources |
| --- | ---: |
| `network_vpn` | 60 |
| `auth_access` | 36 |
| `email_communication` | 53 |
| `software_apps` | 50 |
| `system_os` | 50 |

The Markdown articles come from a pinned revision of
`MicrosoftDocs/SupportArticles-docs`. The repository's CC BY 4.0 license is
recorded with source attribution; code snippets retain the repository's MIT
notice where applicable. Nine publicly accessible university VPN/eduroam
guides are marked `licence: non précisée, usage académique attribué`. This
records the project's approved academic, non-commercial use with attribution;
it does not claim those publishers granted an open license. NIST SP 800-46
Rev. 2 is a U.S. government work and marked public domain. Source URLs,
attribution, type, and category are maintained in
`data/corpus_manifest.csv`.

The Hugging Face dataset `UmerSajid/IT-Troubleshooting-Dataset` was reviewed
but excluded: its card describes AI-assisted curation, sampled variants
repeat scenarios with generic causes, some rows fall outside the project's
support scope, and neither the metadata nor README declares a license. No
rows were copied or indexed.

## Parsing and chunking

Markdown content is normalized into structural blocks. PDFs are parsed with
PyMuPDF4LLM 1.28.2 into page chunks and Markdown tables, then passed through
the same block representation. The NIST document yielded eight tables across
53 pages; Table 5-1 was extracted as Markdown on PDF page 43. Some PDF glyphs
decode as replacement characters, so extracted text still requires fidelity
checks. Figures are not embedded or described by a vision model.

Docling 2.140.0 was abandoned for this run: an isolated environment took
about 12 minutes to install, and its first conversion spent another six
minutes initializing layout/OCR models without completing. PyMuPDF4LLM
provided usable page-aware/table-aware output in the available time. Its
dual AGPL-3.0-or-later / Artifex commercial license must be reviewed before
redistributing the parser with the project. `pypdf` is used only for the
baseline recursive strategy.

Two chunking approaches were compared on the same included sources:

| Strategy | Rule | Documents | Chunks | Tokens | Tables split | Table introductions missing | Mid-sentence starts |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A — recursive | 800 characters, 100-character overlap | 249 | 2,678 | 385,947 | 67 | 9 | 254 |
| B — blocks | Target 450 tokens, no overlap; section prefix; tables atomic | 249 | 2,345 | 448,687 | 0 | 0 | 8 |

B preserves all detected tables and their immediate introductions, and
greatly reduces mid-sentence starts. It produces fewer but longer chunks;
12 table/code blocks exceed the target because atomic tables are intentionally
not split. Duplicate-sentence counts are high in both strategies and may
reflect repetition in the source articles as well as chunk overlap. Detailed
quality measurements are in [`chunk_quality.md`](chunk_quality.md).

## Embeddings, index, and retrieval

The final vector store is Qdrant Cloud. Both experimental collections use
1,536-dimensional vectors; the selected production collection is
`it_kb_blocks`. Embeddings use OpenAI `text-embedding-3-small`. Gemini was
the original free-tier preference, but its daily quota prevented completing
both full indexes. After approval to switch, OpenAI indexing completed; it
processed 834,634 tokens across both strategies (approximately $0.0167 at
the reference input price, before retries or infrastructure charges).
Indexing sends batches of 32 with a one-second pause, SDK retries, stable
point IDs, and existing-point checks. The recorded collection sizes are
2,678 points for A and 2,345 for B.

Retrieval embeds the query with the same OpenAI model, requests `top_k = 5`,
and applies an exact category payload filter. If the filtered query returns
fewer than two points, it retries without the filter. The low Qdrant
`score_threshold` is **0.30**. In the filtered B test, top-1 scores ranged
from 0.4053 to 0.859; therefore 0.30 removed none of the 30 test queries,
including the three no-answer cases. It is a weak-noise cutoff, not an
abstention boundary.

### A/B retrieval results

The 30-query evaluation has 27 answerable queries and three `no_answer`
queries. Recall and MRR use exact expected-source matches; no-answer items are
excluded from those metrics.

| Strategy | Category filter | Recall@1 | Recall@3 | Recall@5 | MRR |
| --- | --- | ---: | ---: | ---: | ---: |
| A — `it_kb_recursive` | No | 0.741 | 0.815 | 0.889 | 0.790 |
| A — `it_kb_recursive` | Yes | 0.741 | 0.815 | 0.889 | 0.790 |
| B — `it_kb_blocks` | No | 0.778 | 0.852 | 0.926 | 0.825 |
| B — `it_kb_blocks` | Yes | **0.778** | **0.889** | **0.926** | **0.828** |

Filtered B leads on Recall@3/5 and MRR; unfiltered B also improves over A.
The difference is only one or two queries out of 27, so the result is a
promising trend rather than a decisive win. Filtered B's empirically selected
score boundary, 0.4805, accepted 25/27 answerable items and rejected all
three no-answer items, but also abstained on two answerable queries. The
answerable and no-answer score ranges overlap, and the boundary was selected
on this same small set. Do not use it as a production guarantee.

Failure review found adjacent-but-wrong results for A05 and O01; A also
missed N05 within its top five. B's table Recall@3 improves from 0.750 to
1.000 with category filtering, but N06 is low-scoring and would be rejected
by the empirical boundary despite a relevant source in the top five.
Plausible neighboring content still appears for all three no-answer
examples. These results support B with filtering as the provisional strategy,
while the Validator—not retrieval score alone—decides whether an answer is
supported. Full tables and failure notes are in
[`retrieval_summary.md`](../eval/results/retrieval_summary.md).

## Validator: final two-mode gate

The Validator is called after answer generation and again before ticket
creation. Its input dossier contains the user report and language, Vision,
Triage, retrieval query/chunks/attempts, the answer or ticket draft, and
attempt counters. Its contract returns a verdict, failure type, target stage,
stage checks, actionable feedback, and reason.

Deterministic code runs before the LLM judge. It handles malformed pipeline
fields without crashing; checks Vision confidence and extracted error; checks
Triage taxonomy, sensitive keywords, urgency, and category consistency;
enforces the answer-mode retrieval gate (at least two passages scoring
`>= 0.48` and top-1 in the Triage category); verifies citations and literal
commands; uses shared guardrails for destructive actions; validates ticket
fields; and redacts secrets and personal data. The `0.48` rule triggers one
retrieval rewrite—it is not an answer refusal threshold. Sensitive incidents
escalate immediately. Remaining semantic grounding, cross-stage consistency,
clarity, and language checks go to the LLM judge.

Groq is primary, followed by Gemini and OpenAI for the deployed service.
The judge returns one of `approve`, `retry_retrieval`, `regenerate`,
`clarify`, or `escalate`. The workflow allows at most one retrieval retry
and one regeneration, no more than two correction attempts total, then
escalates. Ticket mode does not require RAG passages merely to create a
human-review ticket: report and Vision evidence can support a factual ticket.
Secret leakage is redacted before further inspection and reported; retries
are bounded.

### Repeated prompt evaluation

The Validator uses 28 simulated dossiers covering both modes and difficult
cases such as nearly modified commands, partially supported claims, category
conflicts, OCR/user prompt injection, wrong language, contradictory tickets,
and a partially masked password. V1 and V2 are repeated three times per
model, with Groq pinned and provider fallback disabled. Aggregated means,
sample standard deviations, per-run accuracy, and pooled confusion matrices
are in [`validator_summary.md`](../eval/validator_summary.md). These repeated
scores measure judge variability on this hand-authored set only; they do not
estimate the production false-approve rate. No prompt should be described as
reliably superior if the observed difference is within run-to-run spread.

The first v2 pass increased mean accuracy, but false approvals also rose on
the 20B model (1.333 per run) and a ticket contradiction remained misrouted.
After strengthening v2, the measured results were:

| Model | Prompt | Accuracy (mean ± sample SD) | False approves/run | False rejections/run | Judge errors/run |
| --- | --- | ---: | ---: | ---: | ---: |
| `openai/gpt-oss-120b` | v1 | 0.917 ± 0.021 | 0.333 ± 0.577 | 1.000 ± 0.000 | 1.000 ± 0.000 |
| `openai/gpt-oss-120b` | v2 corrected | **1.000 ± 0.000** | **0.000 ± 0.000** | **0.000 ± 0.000** | **0.000 ± 0.000** |
| `openai/gpt-oss-20b` | v1 | 0.762 ± 0.021 | 0.000 ± 0.000 | 5.000 ± 0.000 | 6.000 ± 0.000 |
| `openai/gpt-oss-20b` | v2 corrected | 0.917 ± 0.021 | 0.000 ± 0.000 | 1.000 ± 0.000 | 1.333 ± 0.577 |

The corrected prompt eliminated observed false approvals in these repeated
runs. However, 20B still produced invalid judge decisions that were converted
to fail-closed escalations, especially on the user-injection case. Prefer
120B v2 for this evaluation; do not interpret 28 curated dossiers as a
production reliability guarantee.

## Limitations and lessons

The corpus is Microsoft- and network-support-heavy, while the evaluation set
is small and hand-authored. Three no-answer queries are insufficient to
calibrate abstention, and the retrieval threshold was selected on the same
queries used to report it. Small score gaps do not establish statistical
significance. PDF text extraction can corrupt glyphs, and images/diagrams are
not searchable. The university PDFs have no specified licenses; the manifest
records the approved academic attribution but does not convert that into an
open license.

The attempted Gemini embedding route stopped at a free-tier quota; this
prevented completing comparable full indexes there. Docling's setup and
conversion initialization exceeded the available time. Groq's previously
tested `llama-3.1-8b-instant` is no longer accessible on the configured key;
the repeated small-model comparison therefore uses the available
`openai/gpt-oss-20b`, not an 8B model. These constraints are recorded rather
than hidden. Next steps are a larger independent no-answer set, more
category-balanced queries, manual review of PDF text/table fidelity, and a
repeat evaluation on real (de-identified) workflow dossiers.
