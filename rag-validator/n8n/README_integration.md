# Solvey n8n integration

## Credentials to create in n8n Cloud

The credential **type** below is the item to choose from **Create credential**. The names in parentheses are labels shown by the exported nodes, not credential types. Keep all values in n8n credentials; never put the `.env` values in workflow JSON.

| Create credential type (exact n8n display name) | Credential label (optional) | Fields to fill | `.env` variable | Nodes using it (workflow → node) |
| --- | --- | --- | --- | --- |
| **OpenAI** (`openAiApi`, predefined) | `OpenAI API` | **API Key** = key value. Leave **Organization ID (optional)** blank unless your account requires it; leave **Base URL** at its default; **Add Custom Header** off. | `OPENAI_API_KEY` | `rag_retrieve.json` → **OpenAI Query Embedding**; `solvey_main.json` → **OpenAI Vision Fallback** |
| **Header Auth** (`httpHeaderAuth`, generic) | `Groq API` | **Name** = `Authorization`; **Value** = bearer scheme followed by the key value. | `GROQ_API_KEY` | `extract_route.json` → **Groq structured extraction**; `resolution_agent.json` → **Groq resolution**; optional fallback `ticket_agent.json` → **Groq ticket** |
| **Header Auth** (`httpHeaderAuth`, generic) | `Google Gemini API key` | **Name** = `x-goog-api-key`; **Value** = key value (no bearer prefix). | `GOOGLE_API_KEY` | `solvey_main.json` → **Gemini Vision Fallback** |
| **Header Auth** (`httpHeaderAuth`, generic) | `Qdrant API Key` | **Name** = `api-key`; **Value** = API key value. | `QDRANT_API_KEY` | `rag_retrieve.json` → **Qdrant Search (category)** and **Qdrant Search (fallback)** |
| **Header Auth** (`httpHeaderAuth`, generic) | `OpenAI Validator API` | **Name** = `Authorization`; **Value** = bearer scheme followed by the key value. | `OPENAI_API_KEY` | `validator.json` → **OpenAI Judge Fallback** |
| **Jira SW Cloud API** (`jiraSoftwareCloudApi`, predefined) | `Solvey Jira` | **Email** = Atlassian account email; **API Token** = token created in Atlassian; **Domain** = Jira Cloud site domain (for example, `company.atlassian.net`, without `https://`). | No Jira variables exist in `.env`; create this credential directly in n8n. | `solvey_main.json` → **Create Jira issue**; `solvey_error_workflow.json` → **Create Jira fallback issue** |

`QDRANT_URL` is the Qdrant cluster endpoint, not a credential field: replace `YOUR-QDRANT-CLUSTER` in both Qdrant URL fields in `rag_retrieve.json` with that endpoint (keeping the `/collections/it_kb_blocks/points/query` path). `validator.json` runs its deterministic checks in native Code nodes, then calls Groq, Gemini, and OpenAI directly through HTTP Request nodes; it does not call FastAPI or any external Validator service. Select the listed credentials in those three nodes. Re-select each credential in the imported nodes because exported credential IDs are placeholders.

For the OpenAI embedding/vision type, the node JSON declares `openAiApi`; n8n's credential definition displays this as **OpenAI**. The Validator's OpenAI fallback uses a raw HTTP Request and therefore a separate **Header Auth** credential (`Authorization: Bearer …`). Header-based nodes declare `httpHeaderAuth`, displayed as **Header Auth**. Jira nodes declare `jiraSoftwareCloudApi`, displayed as **Jira SW Cloud API**. The exported labels can be renamed in n8n without changing the credential type.

The intake nodes come from the colleague's export and remain in place. Only downstream routing is replaced. `Mock DistilBERT Output` remains a constant demo node and is marked **À REMPLACER par le vrai modèle**.

## Import order

1. Import `rag_retrieve.json` and `validator.json`.
2. Import `extract_route.json`, `resolution_agent.json`, `ticket_agent.json` (documented fallback only), `escalation_agent.json`, and `solvey_error_workflow.json`.
3. Import `solvey_main.json` last.
4. In each **Execute Workflow** node in the main workflow, re-select the imported `RAG Retrieve`, `Final Validator`, `Extract & Route`, `Resolution Agent`, and **Colleague Escalation Agent adapter (draft only)**; exported references are placeholders. Both the initial ticket and its single regeneration call the adapter. In that adapter, re-select **Ticket Agent** on **Call local Ticket Agent fallback**.
5. In `validator.json`, select `Groq API`, `Google Gemini API key`, and `OpenAI Validator API` in their respective HTTP Request nodes. No FastAPI service or validator URL is needed.
6. In `rag_retrieve.json`, replace `YOUR-QDRANT-CLUSTER`, and re-select OpenAI/Qdrant credentials.
7. Create the **Jira SW Cloud API** credential and re-select it on both Jira nodes. In `solvey_main.json` → **Create Jira issue** and `solvey_error_workflow.json` → **Create Jira fallback issue**, select the target Project (its key is `YOUR_PROJECT_KEY` in the export) and Issue Type (`YOUR_ISSUE_TYPE_ID`). Set the Jira priority IDs used in **Prepare Jira issue** and **Build secret-free fallback ticket** to the IDs configured in your Jira project; the sample IDs follow the common default ordering and may differ in your site.
8. In the main workflow settings, choose `Solvey Error Workflow — fallback ticket` as the Error Workflow. Activate only after credentials and sub-workflow references are set.

## Colleague escalation agent adapter

`solvey_main.json` calls `escalation_agent.json` with the complete ticket dossier. The adapter converts it to the colleague service's `CaseInputPayload`, calls its `/format-preview` endpoint, and converts `synthesized_ticket` into our `draft_ticket` format. `/format-preview` creates no Jira issue: the same local ticket-mode Validator runs next, and the existing Jira node creates the issue only after approval. The colleague's source branch and workflow have not been modified; `/escalate` is not used.

The adapter's **Escalation Endpoint Config** node contains the one setting `format_preview_url`; update that value to change the colleague service endpoint. n8n Cloud cannot reach a loopback or private workstation URL. Put the endpoint behind an authenticated HTTPS gateway before exposing it; configure any required headers in the HTTP Request node without placing secrets in exported JSON. **Request colleague ticket draft (no Jira)** has a 30,000 ms timeout and sends transport/API errors to **Call local Ticket Agent fallback**. That node calls the imported `ticket_agent.json` with the original dossier; its `{draft_ticket}` output then follows the same ticket Validator and Jira approval path as the colleague-generated draft. This also applies when the main workflow makes its one allowed ticket regeneration. The local fallback is not used if the colleague response succeeds. If both draft providers fail, the error reaches the configured Error Workflow; no ticket is created from an unvalidated draft. After importing, re-select the adapter in both main-workflow Execute Workflow nodes and re-select **Ticket Agent** in the adapter's fallback Execute Workflow node. Regenerate exports with `python scripts/build_escalation_adapter.py`.

## Credentials and sharing

Create the six credential instances from the table above and re-select each one in the imported HTTP Request/Jira nodes. In n8n Cloud, share workflows and credentials with the same project/team; sharing a workflow does not automatically grant credential use. Do not export credentials or commit them.

The single Qwen tunnel setting is `qwen_chat_url` in the `Vision Endpoint Config` node. Replace that one value when the trycloudflare URL changes. Qwen has a 45-second timeout; failure routes to Gemini `gemini-3.8-flash`, then OpenAI `gpt-4o-mini`, with the same visual-inspection prompt and text output shape.

## Normalizer and routing behavior

`Normalize & Parse Vision` parses the Qwen labels without an LLM. “Not visible”/“None” become null, message bullets become `error_text`, and screen state becomes `observations`. Confidence is an explicit heuristic: 0.8 when an error is extracted, otherwise 0.5; it is not calibrated. Unreadable text or no recognized data sets `usable=false`. Unrecognized text is preserved in `vision_raw_text` and forwarded verbatim as `error_text`/observation. The Code node has a unit test with the exact Qwen output from the request.

Classifier labels map case-insensitively to taxonomy IDs; an unknown label becomes `other`. Extract & Route returns structured taxonomy and an English query. Deterministic security keywords override the model and force `is_sensitive`, with high/critical urgency. Low classifier confidence still reaches Extract & Route: vague input asks for clarification, only a reliable category continues to RAG, and other substantive/unknown incidents go to a ticket.

Retrieval uses strategy B (`it_kb_blocks`), top 5, category filter and the existing unfiltered fallback. The main Code check requires at least two chunks scoring `>=0.48` and top-1 in the Triage category. It performs one deterministic reformulation (including the exact observed error) and one second search; if evidence remains weak, it routes to a ticket. The final Validator remains the quality gate. Validator retries/regeneration are bounded by dossier counters. A ticket failing its one regeneration fails closed and invokes the Error Workflow.

`validator.json` is self-contained: `Deterministic Validator Checks` ports the Python schema, taxonomy, sensitivity, retrieval relevance, ticket-section, exact-command, destructive-action, language, PII and secret checks. If no deterministic verdict applies, **Groq** (`openai/gpt-oss-120b`) judges first, then **Gemini** (`gemini-3.8-flash`) and **OpenAI** (`gpt-4o-mini`) when a request fails or returns non-JSON. `Apply Judge Decision` enforces verdict/failure-type consistency and the retry limits. If all providers fail, the workflow escalates without approving a user response or ticket. `n8n/validator_logic.js` and `n8n/validator_decision.js` are the editable sources for the embedded Code nodes; rebuild the export with `python scripts/build_validator_n8n.py`.

## Jira ticket creation

Only Validator-approved sanitized dossiers reach Jira. `Prepare Jira issue` sends the required title as Jira Summary and the required seven-section description; it inserts the Validator verdict and reason in the escalation section. The Jira response key is returned as `ticket_number`. The Error Workflow creates a generic high-priority Jira issue with workflow/execution identifiers only; raw payloads and error bodies are intentionally omitted.

If the team already has a Jira-creation workflow, replace **Create Jira issue** (and, if desired, **Create Jira fallback issue**) with an **Execute Workflow** node. Once its workflow name is known, select it, pass `summary`, `description`, and mapped Jira priority, and make sure its output includes the created issue key. Keep the direct Jira node as the default until that shared workflow is available.

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
