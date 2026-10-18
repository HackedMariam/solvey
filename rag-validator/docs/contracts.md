# Shared JSON contracts

These are the hand-off shapes between the n8n workflow, RAG sub-workflow, and
Validator sub-workflow. Property names are intentionally stable for the team.
The retrieval workflow embeds only `text`; other chunk fields are payload.

## Retrieval request

```json
{
  "query": "Outlook cannot send email error 0x800CCC0F",
  "category": "email_communication",
  "top_k": 5
}
```

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `query` | string | yes | English search query produced by Triage. |
| `category` | string or `null` | yes | Taxonomy id (`network_vpn`, `auth_access`, `email_communication`, `software_apps`, `system_os`, `general`); `null` means no category filter. |
| `top_k` | integer | yes | Maximum number of results; default is `5`. |

## Retrieval response

```json
{
  "chunks": [
    {
      "id": "S1",
      "text": "Document: ...\nSection: ...",
      "table_raw": null,
      "title": "Troubleshooting Outlook",
      "section": "Troubleshooting > Sending",
      "page": 4,
      "source": "outlook-troubleshooting.pdf",
      "url": "https://support.example.org/outlook",
      "category": "email_communication",
      "score": 0.82
    }
  ],
  "used_filter": true
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `chunks` | array | Ordered by descending retrieval score; at most `top_k` records. |
| `chunks[].id` | string | Per-response citation id (`S1`, `S2`, ...). |
| `chunks[].text` | string | Embedded chunk text. |
| `chunks[].table_raw` | string or `null` | Raw Markdown table, when present. |
| `chunks[].title`, `section`, `source` | string | Human-readable document provenance. |
| `chunks[].page` | integer or `null` | Page number when known. |
| `chunks[].url` | string or `null` | Original public URL when known. |
| `chunks[].category` | string | Taxonomy id or `general`. |
| `chunks[].score` | number | Similarity score returned by Qdrant. |
| `used_filter` | boolean | Whether the returned results came from the category-filtered search. |

## Final retrieval configuration

| Setting | Value |
| --- | --- |
| Qdrant collection | `it_kb_blocks` (strategy B) |
| Query embedding | OpenAI `text-embedding-3-small`, 1,536 dimensions |
| `top_k` | 5 |
| Primary search | Exact category payload filter when `category` is non-null |
| Fallback | Repeat the search without a category filter if the filtered search returns fewer than 2 points; if `category` is null, search without a filter directly |
| Qdrant `score_threshold` | 0.30 |
| No-answer decision | The Validator decides whether the evidence supports an answer; retrieval score alone does not classify a query as answerable |

The filtered B evaluation observed top scores from 0.4053 for answerable
queries and up to 0.4726 for no-answer queries. A 0.30 cutoff is below every
observed top score, so it removes no test result and cannot separate
answerable from no-answer cases. It is a low cutoff for discarding obviously
weak retrieval noise, not an abstention threshold. The Validator must make
and justify the final no-answer decision from the retrieved evidence.

## Agent output contracts

Vision emits:

```json
{
  "usable": true,
  "image_quality": "good",
  "application": "Outlook",
  "error_text": "Cannot connect to server",
  "error_code": null,
  "observations": [],
  "contradictions": [],
  "confidence": 0.94
}
```

Triage emits:

```json
{
  "category": "email_communication",
  "subcategory": "cannot_send_email",
  "urgency": "medium",
  "confidence": 0.91,
  "problem_type": "Outlook cannot send messages.",
  "search_query": "Outlook messages remain in the Outbox and are not sent",
  "automatable": true,
  "is_sensitive": false,
  "sensitivity_reason": null,
  "needs_clarification": false,
  "clarification_question": null,
  "language": "en"
}
```

RAG output is the retrieval response above plus query/attempt metadata:

```json
{
  "query": "Outlook messages remain in the Outbox and are not sent",
  "chunks": [
    {
      "id": "S1",
      "text": "When Work Offline is selected, messages remain in the Outbox.",
      "table_raw": null,
      "title": "Troubleshoot messages stuck in Outbox",
      "section": "Sending messages",
      "page": null,
      "source": "outlook-outbox.md",
      "url": "https://support.example.org/outlook",
      "category": "email_communication",
      "score": 0.74
    }
  ],
  "attempts": 1
}
```

The solution writer emits:

```json
{
  "summary": "Outlook may be offline, leaving messages queued.",
  "steps": [
    {
      "instruction": "Check that Work Offline is not selected, then try sending again.",
      "command": null,
      "source_ids": ["S1"]
    }
  ],
  "warnings": [],
  "escalate_if": "Contact IT if the message remains in the Outbox.",
  "confidence": 0.88,
  "final_message": "Check that Work Offline is not selected, then try sending again."
}
```

`final_message` is optional; absent it, the Validator checks the answer
summary and step instructions as the user-facing text.

Escalation/Ticket emits:

```json
{
  "title": "Outlook messages remain in Outbox",
  "summary": "The user cannot send mail; messages remain queued after checking the connection.",
  "evidence": [{"source": "user_report", "detail": "Messages remain in the Outbox."}],
  "attempted_steps": ["Checked the network connection."],
  "priority": "medium",
  "suggested_actions_for_staff": ["Review Outlook connectivity and mailbox status."]
}
```

## Validator input — complete dossier

The final Validator is the workflow quality gate in both modes, after answer
generation and before ticket creation. All listed top-level fields are
required. `vision` may be `null` when no image was submitted; its key must
still be present. Use [`examples/dossier_answer.json`](../examples/dossier_answer.json)
and [`examples/dossier_ticket.json`](../examples/dossier_ticket.json) as
reference dossiers.

```json
{
  "mode": "answer",
  "user_text": "Outlook reports 0x800CCC0F when I send.",
  "language": "en",
  "vision": null,
  "triage": {
    "category": "email_communication",
    "subcategory": "cannot_send_email",
    "urgency": "medium",
    "confidence": 0.9,
    "problem_type": "Outlook cannot send messages.",
    "search_query": "Outlook cannot send error 0x800CCC0F",
    "automatable": true,
    "is_sensitive": false,
    "sensitivity_reason": null,
    "needs_clarification": false,
    "clarification_question": null,
    "language": "en"
  },
  "retrieval": {"query": "...", "chunks": [], "attempts": 1},
  "draft_answer": {"summary": "...", "steps": []},
  "attempt_counts": {"retry_retrieval": 0, "regenerate": 0, "total": 0}
}
```

For ticket mode, replace `draft_answer` by `draft_ticket`; all other
top-level fields remain present.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `mode` | string | yes | `answer` before user delivery, or `ticket` before ticket creation. |
| `user_text` | string | yes | Original user report; untrusted data. |
| `language` | string | yes | User-facing language (`fr`, `en`, `ar`, `other`). |
| `vision` | object or `null` | yes | Vision output from the schema above; untrusted evidence. |
| `triage` | object | yes | Triage output from the schema above. |
| `retrieval` | object | yes | `{query, chunks, attempts}`; chunks use `S1..S5`, score and category. |
| `draft_answer` | object | answer mode | Resolution output; never used in ticket mode. |
| `draft_ticket` | object | ticket mode | Escalation output; never used in answer mode. |
| `attempt_counts` | object | yes | Non-negative `{retry_retrieval, regenerate, total}` counters. |

Missing or malformed required fields do not crash the Validator: they return
`escalate` / `inconsistent_pipeline`, with the precise stage and field path in
`reason` and `feedback_for_stage`.

## Validator output

```json
{
  "verdict": "regenerate",
  "failure_type": "unfaithful_answer",
  "target_stage": "answer",
  "stage_checks": {
    "vision": {"status": "ok", "issues": [], "corrections": []},
    "triage": {"status": "ok", "issues": [], "corrections": []},
    "retrieval": {"status": "ok", "issues": [], "corrections": []},
    "answer": {"status": "failed", "issues": ["steps[0] command is not verbatim in its cited source"], "corrections": []},
    "ticket": {"status": "ok", "issues": [], "corrections": []},
    "final_message": {"status": "ok", "issues": [], "corrections": []}
  },
  "feedback_for_stage": "Copy the command exactly from the cited passage, or omit it.",
  "reason": "A proposed command differs from the cited instructions."
}
```

Verdicts are `approve`, `retry_retrieval`, `regenerate`, `clarify`, and
`escalate`. Failure types are `insufficient_evidence`, `unfaithful_answer`,
`missing_user_info`, `safety_risk`, `inconsistent_pipeline`,
`incomplete_ticket`, and `leak`; `failure_type` is `null` on approval because
there is no failure. `target_stage` is the stage to retry, or `null` on
approval. `stage_checks` always reports `vision`, `triage`, `retrieval`,
`answer`, `ticket`, and `final_message`, with issues and deterministic
corrections.

Deterministic code runs before the LLM judge. Vision confidence must be at
least 0.55, and usable images must include `error_text`. The Triage pair is
checked against the shared taxonomy; a known subcategory repairs its category
in code and records the correction. Security keywords cross-check the
sensitive flag; a detected incident repairs a missing flag, raises urgency
to `high`, then escalates immediately. A problem/category mismatch is
reported as an inconsistent pipeline.

In answer mode, at least two retrieved chunks must have score `>= 0.48`, and
the highest-scoring chunk must match the Triage category. Failure requests
`retry_retrieval` once; `0.48` is a code-based rewrite trigger, not a refusal
threshold. Every source id must exist. Proposed commands must match their
cited passage verbatim; destructive actions escalate before the LLM call.
Ticket mode requires summary, evidence, attempted steps, and priority. Secret
values are redacted before further inspection or submission and reported as
`leak`. User-facing text is checked for language, internal JSON, and personal
contact data.

The LLM judge assesses semantic consistency, factual support, relevance,
clarity, and safety. Provider order is Groq `openai/gpt-oss-120b` via the
official SDK, Gemini `gemini-3.8-flash`, then OpenAI `gpt-4o-mini`; the
responding provider/model is logged without credentials. `safety_risk` always
escalates. There is at most one retrieval retry and one regeneration, with no
more than two correction attempts total; exhausted paths escalate. An
incomplete ticket can be regenerated once.

## Provider and model decisions

| Component | Decision | Status |
| --- | --- | --- |
| Vector database | Qdrant Cloud | Both indexes are verified at the configured HTTPS URL: `it_kb_recursive` has 2,678 points and `it_kb_blocks` has 2,345 points; each uses 1,536 dimensions. |
| Embeddings | OpenAI `text-embedding-3-small`, **1,536 dimensions** | Selected after Gemini's free daily quota prevented completing both indexes. A live one-input probe and both full indexes succeeded. Use this exact model and dimension in n8n and offline indexing. |
| Embedding throughput | OpenAI Embeddings API, 32 texts per batch, 1-second pause, up to 5 SDK retries | Indexer validates returned vector count and dimension and resumes from existing deterministic point IDs. Both strategies processed 834,634 input tokens total; estimated API cost is approximately $0.0167, excluding retries and Qdrant charges. |
| Validator and descriptions | Groq `openai/gpt-oss-120b` first, Gemini `gemini-3.8-flash` fallback, OpenAI `gpt-4o-mini` last | All three returned a minimal successful response using their respective clients. Groq works via the official SDK; `urllib` receives Cloudflare HTTP 403 `error code: 1010`. Any fallback must log which provider returned the response. |

The `.env` file was verified as UTF-8 without BOM, with the expected variable
names, no surrounding whitespace, and no quoted values. It remains ignored by
Git. A repository-wide GitHub code search located three additional Microsoft
Outbox articles at the pinned source revision; the corpus manifest records
their CC BY 4.0 attribution. `eval/test_queries_draft.csv` contains 30 queries,
including four table questions and three no-answer cases.
