# RAG + Validator

Python 3.11+ utilities for offline parsing, indexing, and evaluation, plus the
shared contracts for the n8n RAG and Validator sub-workflows. The final
architecture uses one Qdrant collection; the offline chunking comparison may
temporarily use separate collections for strategies A and B.

## Qdrant Cloud (shared team index)

1. Create a free account at [cloud.qdrant.io](https://cloud.qdrant.io/) and
   create a free cluster. Select a region close to the team's n8n instance.
2. Open the cluster's connection details and copy its HTTPS cluster URL. Use
   the cluster URL itself as `QDRANT_URL` (not the dashboard URL).
3. Create an API key in the cluster's API-key/security settings. Grant the
   permissions needed to create collections, upload points, and search; keep
   the key private.
4. Copy `.env.example` to `.env` and set `QDRANT_URL`,
   `QDRANT_API_KEY`, `OPENAI_API_KEY`, and `GROQ_API_KEY`.
   `GOOGLE_API_KEY` is used only for the configured Gemini LLM fallback.
   Never commit `.env`.
5. In n8n, use the same Qdrant URL/key and the exact embedding model and
   vector dimension recorded in [docs/contracts.md](docs/contracts.md).
   Do not index until the embedding model has been validated and frozen there.

Cloud dashboard labels and free-tier availability can change. Verify the
cluster is active and its API-key permissions allow both indexing and search
before running the pipeline.

## Local Qdrant fallback

Docker Compose is an optional local fallback; it is not required when the team
uses the shared Cloud cluster.

1. For local use, set `QDRANT_URL=http://localhost:6333` and
   `QDRANT_API_KEY` to a private local development key in `.env`.
2. Start Qdrant from this directory with `docker compose up -d`.
3. The service persists data in the `qdrant_storage` Docker volume.

Do not point a cloud-hosted n8n instance at `localhost`; keep Cloud Qdrant
configured in n8n, or use a secure, publicly reachable Qdrant deployment.

## Python environment

### Reproduce the pipeline in five commands

Run these from PowerShell at the `rag-validator` root. Before command 2, make
the MicrosoftDocs checkout available as shown below; after copying `.env`,
fill it with your own Qdrant, OpenAI, and Groq credentials. The command
blocks are grouped by task so setup and evaluation can be repeated in order.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

```powershell
Copy-Item .env.example .env
notepad .env
```

```powershell
if (-not (Test-Path 'data\upstream\SupportArticles-docs')) { git clone --depth 1 --filter=blob:none --sparse https://github.com/MicrosoftDocs/SupportArticles-docs.git data\upstream\SupportArticles-docs }
git -C data\upstream\SupportArticles-docs fetch --depth 1 origin 2bc340377700b726eecb79f9dcca71dfa8d6a78e
git -C data\upstream\SupportArticles-docs checkout --detach 2bc340377700b726eecb79f9dcca71dfa8d6a78e
git -C data\upstream\SupportArticles-docs sparse-checkout set --no-cone '/Outlook/classic-outlook-for-windows/**/*.md' '/Exchange/ExchangeOnline/**/*.md' '/Microsoft365/admin/**/*.md' '/Office/Client/**/*.md' '/support/entra/entra-id/**/*.md' '/support/windows-client/networking/**/*.md' '/support/windows-client/installing-updates-features-roles/**/*.md' '/support/windows-client/setup-upgrade-and-drivers/**/*.md' '/support/windows-client/application-management/**/*.md' '/support/windows-client/active-directory/**/*.md' '/support/windows-hardware/drivers/**/*.md' '/LICENSE' '/LICENSE-CODE' '/README.md'
.\.venv\Scripts\python.exe -m scripts.prepare_corpus
```

```powershell
.\.venv\Scripts\python.exe -m scripts.chunk_quality
.\.venv\Scripts\python.exe -m scripts.index_corpus --strategies recursive blocks
```

```powershell
.\.venv\Scripts\python.exe eval\evaluate_retrieval.py
.\.venv\Scripts\python.exe eval\run_validator_matrix.py
```

The indexer batches OpenAI embedding requests, pauses between batches, retries
transient rate-limit/server errors, and upserts points to both strategy
collections. It does not delete existing points unless `--reset` is given.
Retrieval summary: [`eval/results/retrieval_summary.md`](eval/results/retrieval_summary.md).
Repeated Validator summary: [`eval/validator_summary.md`](eval/validator_summary.md).
Per-query and per-case JSON logs remain local and ignored by Git.

For individual Validator runs, pin the Groq judge with
`eval\validator_eval.py --prompt-version v1 --groq-model openai/gpt-oss-120b`.
The matrix command runs v1/v2 three times each with Groq
`openai/gpt-oss-120b` and `openai/gpt-oss-20b`. The requested
`llama-3.1-8b-instant` is not available to the configured key; see the report
for the verified model substitution.

For phase 3, import `n8n\rag_retrieve.json` into n8n and configure its OpenAI
and Qdrant credentials as described in
[`docs/rag_retrieve_setup.md`](docs/rag_retrieve_setup.md).

## Phase 1 corpus

The Microsoft support corpus is sourced from a sparse checkout of
`MicrosoftDocs/SupportArticles-docs`. The current selection was produced from
the 2026-10-17 `main` revision recorded in the manifest. Recreate the checkout
and selection with:

```powershell
git clone --depth 1 --filter=blob:none --sparse https://github.com/MicrosoftDocs/SupportArticles-docs.git data\upstream\SupportArticles-docs
git -C data\upstream\SupportArticles-docs sparse-checkout set --no-cone '/Outlook/classic-outlook-for-windows/**/*.md' '/Exchange/ExchangeOnline/**/*.md' '/Microsoft365/admin/**/*.md' '/Office/Client/**/*.md' '/support/entra/entra-id/**/*.md' '/support/windows-client/networking/**/*.md' '/support/windows-client/installing-updates-features-roles/**/*.md' '/support/windows-client/setup-upgrade-and-drivers/**/*.md' '/support/windows-client/application-management/**/*.md' '/support/windows-client/active-directory/**/*.md' '/support/windows-hardware/drivers/**/*.md' '/LICENSE' '/LICENSE-CODE' '/README.md'
python -m scripts.prepare_corpus
```

The script selects Markdown articles and writes their attribution and category
mappings to `data/corpus_manifest.csv`. The Hugging Face
`UmerSajid/IT-Troubleshooting-Dataset` is recorded as rejected and is not
indexed because its card describes AI-assisted curation and does not declare
a license.

PDFs are not downloaded automatically. Add them to
`data/corpus/<category>/`; their license and public URL must be recorded in
the manifest before indexing. PDF parsing uses PyMuPDF4LLM; its dual
AGPL-3.0-or-later / Artifex commercial license must be reviewed before
redistributing the project. `pypdf` is retained only for baseline A.

## Shared contracts

See [docs/contracts.md](docs/contracts.md) for the retrieval and Validator
request/response shapes agreed with the n8n workflow.
