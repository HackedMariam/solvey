# Solvey n8n integration

## Credentials to create in n8n Cloud

The credential **type** below is the item to choose from **Create credential**. The names in parentheses are labels shown by the exported nodes, not credential types. Keep all values in n8n credentials; never put the `.env` values in workflow JSON.

| Create credential type (exact n8n display name) | Credential label (optional) | Fields to fill | `.env` variable | Nodes using it (workflow → node) |
| --- | --- | --- | --- | --- |
| **OpenAI** (`openAiApi`, predefined) | `OpenAI API` | **API Key** = key value. Leave **Organization ID (optional)** blank unless your account requires it; leave **Base URL** at its default; **Add Custom Header** off. | `OPENAI_API_KEY` | `rag_retrieve.json` → **OpenAI Query Embedding**; `solvey_main.json` → **OpenAI Vision Fallback** |
| **Header Auth** (`httpHeaderAuth`, generic) | `Groq API` | **Name** = `Authorization`; **Value** = bearer scheme followed by the key value. | `GROQ_API_KEY` | `extract_route.json` → **Groq structured extraction**; `resolution_agent.json` → **Groq resolution**; `ticket_agent.json` → **Groq ticket** |
| **Header Auth** (`httpHeaderAuth`, generic) | `Google Gemini API key` | **Name** = `x-goog-api-key`; **Value** = key value (no bearer prefix). | `GOOGLE_API_KEY` | `solvey_main.json` → **Gemini Vision Fallback** |
| **Header Auth** (`httpHeaderAuth`, generic) | `Qdrant API Key` | **Name** = `api-key`; **Value** = API key value. | `QDRANT_API_KEY` | `rag_retrieve.json` → **Qdrant Search (category)** and **Qdrant Search (fallback)** |

`QDRANT_URL` is the Qdrant cluster endpoint, not a credential field: replace `YOUR-QDRANT-CLUSTER` in both Qdrant URL fields in `rag_retrieve.json` with that endpoint (keeping the `/collections/it_kb_blocks/points/query` path). `validator.json` and `solvey_error_workflow.json` have no n8n credential references; the Validator HTTP endpoint is unauthenticated in this export, and its LLM provider credentials belong to the separately deployed Validator service. `solvey_main.json` and the agent workflows have no further credential types beyond those listed above. Re-select each credential in the imported nodes because exported credential IDs are placeholders.

For the OpenAI type, the node JSON declares `openAiApi`; n8n's credential definition displays this as **OpenAI**. Header-based nodes declare `httpHeaderAuth`, displayed as **Header Auth**. The exported labels (`OpenAI API`, `Groq API`, etc.) can be renamed in n8n without changing the credential type.

The intake nodes come from the colleague's export and remain in place. Only downstream routing is replaced. `Mock DistilBERT Output` remains a constant demo node and is marked **À REMPLACER par le vrai modèle**.

## Import order

1. Import `rag_retrieve.json` and `validator.json`.
2. Import `extract_route.json`, `resolution_agent.json`, `ticket_agent.json`, and `solvey_error_workflow.json`.
3. Import `solvey_main.json` last.
4. In each **Execute Workflow** node in the main workflow, re-select the imported `RAG Retrieve`, `Final Validator`, `Extract & Route`, `Resolution Agent`, and `Ticket Agent`; exported references are placeholders.
5. Set the Validator URL in `validator.json` to a host reachable from n8n Cloud; deploy its FastAPI service separately.
6. In `rag_retrieve.json`, replace `YOUR-QDRANT-CLUSTER`, and re-select OpenAI/Qdrant credentials.
7. Create a Data Table named `solvey_tickets` with text columns `ticket_number`, `request_id`, `created_at`, `priority`, `title`, `summary`, `payload_json`. Both main and error workflows use its Row/Insert operation. Data Tables are documented as native n8n storage ([documentation](https://docs.n8n.io/build/work-with-data/data-tables/)), so this integration selects that option instead of Google Sheets. Confirm the **Data Tables** tab is available in the actual Cloud project; if that workspace lacks it, replace both Row/Insert nodes with Google Sheets Append Row using the same columns and a shared Sheets credential.
8. In the main workflow settings, choose `Solvey Error Workflow — fallback ticket` as the Error Workflow. Activate only after credentials and sub-workflow references are set.

## Credentials and sharing

Create the four credential instances from the table above and re-select each one in the imported HTTP Request nodes. In n8n Cloud, share workflows and credentials with the same project/team; sharing a workflow does not automatically grant credential use. Do not export credentials or commit them.

The single Qwen tunnel setting is `qwen_chat_url` in the `Vision Endpoint Config` node. Replace that one value when the trycloudflare URL changes. Qwen has a 45-second timeout; failure routes to Gemini `gemini-3.8-flash`, then OpenAI `gpt-4o-mini`, with the same visual-inspection prompt and text output shape.

## Normalizer and routing behavior

`Normalize & Parse Vision` parses the Qwen labels without an LLM. “Not visible”/“None” become null, message bullets become `error_text`, and screen state becomes `observations`. Confidence is an explicit heuristic: 0.8 when an error is extracted, otherwise 0.5; it is not calibrated. Unreadable text or no recognized data sets `usable=false`. Unrecognized text is preserved in `vision_raw_text` and forwarded verbatim as `error_text`/observation. The Code node has a unit test with the exact Qwen output from the request.

Classifier labels map case-insensitively to taxonomy IDs; an unknown label becomes `other`. Extract & Route returns structured taxonomy and an English query. Deterministic security keywords override the model and force `is_sensitive`, with high/critical urgency. Low classifier confidence still reaches Extract & Route: vague input asks for clarification, only a reliable category continues to RAG, and other substantive/unknown incidents go to a ticket.

Retrieval uses strategy B (`it_kb_blocks`), top 5, category filter and the existing unfiltered fallback. The main Code check requires at least two chunks scoring `>=0.48` and top-1 in the Triage category. It performs one deterministic reformulation (including the exact observed error) and one second search; if evidence remains weak, it routes to a ticket. The final Validator remains the quality gate. Validator retries/regeneration are bounded by dossier counters. A ticket failing its one regeneration fails closed and invokes the Error Workflow.

## Ticket and error storage

Only Validator-approved sanitized dossiers are stored as tickets. The Error Workflow files a generic fallback row with workflow/execution identifiers only; it omits raw payloads/error bodies to avoid secret leakage. It must use the same `solvey_tickets` table.

## Four webhook tests

Use `https://<your-n8n-host>/webhook/solvey/support` (or `/webhook-test/solvey/support` while listening in test mode):

```powershell
curl.exe -X POST "https://<your-n8n-host>/webhook/solvey/support" `
  -F "request_id=vpn-001" -F "title=VPN sign-in failed" `
  -F "description=VPN client says authentication failed, check username and password" `
  -F "attachment=@eval\data\screens\vpn_auth_failed.png;type=image/png"

curl.exe -X POST "https://<your-n8n-host>/webhook/solvey/support" `
  -F "request_id=blur-001" -F "title=Cannot read the error" `
  -F "description=The attached screenshot is blurry and I cannot read the error message" `
  -F "attachment=@eval\data\screens\blurred.png;type=image/png"

curl.exe -X POST "https://<your-n8n-host>/webhook/solvey/support" `
  -F "request_id=labsuite-001" -F "title=LabSuite Analyzer startup failure" `
  -F "description=LabSuite Analyzer shows Fatal QX-7781 kernel handshake rejected by licence broker"

curl.exe -X POST "https://<your-n8n-host>/webhook/solvey/support" `
  -F "request_id=security-001" -F "title=Possible account compromise" `
  -F "description=My work account was hacked and I received an unexpected MFA approval prompt"
```

The VPN and blurred-image fixtures are not present in this checkout, so provide them before running the first two image tests. No live webhook execution is claimed. The parser test does use the real Qwen response provided in the request.

## Optional Vision proposal

Optionally, the Vision owner could use Ollama `/api/chat`'s `format` parameter with a JSON Schema for structured vision output. This is not required and does not modify the colleague's source workflow; the imported text parser remains tolerant of the existing free-text response.
