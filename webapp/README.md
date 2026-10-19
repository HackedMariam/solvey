# Solvey web app

Minimal web interface for the Solvey IT-support assistant. An employee describes a problem (optionally
with a screenshot) and gets one of three outcomes:

- **Solved** — step-by-step instructions grounded in the IT knowledge base and checked by the Validator
- **Question** — the assistant needs one more detail; the answer is sent back as a new request
- **Ticket** — the request was escalated to a technician (Jira), with the ticket number

All AI logic lives in the n8n workflow **Main workflow** (vision model → DistilBERT classifier → safety
routing → RAG → Resolution Agent → Validator → answer / clarification / Jira). This app is only the UI
plus a thin proxy.

```
Browser ──► POST /api/ticket (Next.js route, validates) ──► n8n webhook /solvey/main ──► JSON result
```

The browser never calls n8n directly, so the webhook URL and secret stay on the server. Ticket text and
screenshots are only forwarded, never logged or stored by the server. The last 10 results are kept in the
user's own browser (localStorage) as a convenience.

## Requirements

- Node.js 20.9 or newer
- The n8n **Main workflow** published (active), plus everything it depends on running: the classifier API
  (`classification/serve.py`) and its Cloudflare tunnel, the Hugging Face vision Space, Qdrant and the
  OpenAI and Jira credentials in n8n.

## Run locally

```bash
cd webapp
npm install
cp .env.example .env.local   # then edit if needed
npm run dev
```

Open http://localhost:3000.

| Variable | Required | Meaning |
|---|---|---|
| `N8N_WEBHOOK_URL` | yes | Production webhook URL of Main workflow |
| `N8N_WEBHOOK_SECRET` | no | Sent as `X-Solvey-Secret`. Only effective once the n8n webhook node is configured to require that header |

## API contract

`POST /api/ticket` accepts JSON `{ request_id, title, description }` or `multipart/form-data` with the
same fields plus the file `attachment` (PNG/JPEG/WebP, ≤ 5 MB). Description 10–4000 characters, title ≤ 200.
It returns n8n's JSON unchanged:

| `status` | Fields |
|---|---|
| `resolved` | `solution` `{ summary, steps[{ instruction, command, source_ids }], warnings, escalate_if, final_message }`, `sources` |
| `needs_clarification` | `question` |
| `ticket_created` | `ticket_number` |
| `invalid_request` | `message` |
| `error` (proxy only) | `code` (`timeout`, `network`, `upstream_error`, `bad_response`, `not_configured`), `message` |

A run takes 5–90 s, and up to ~3 min with a screenshot; the proxy waits up to 240 s.

## Deploy (Vercel)

1. Import the repository in Vercel and set the **Root Directory** to `webapp`.
2. Add `N8N_WEBHOOK_URL` (and optionally `N8N_WEBHOOK_SECRET`) as environment variables.
3. Deploy.

The API route declares `maxDuration = 300` seconds. Make sure your Vercel plan allows functions to run that
long; if it doesn't, long requests (especially with screenshots) will be cut off. In that case, run the
app locally or on a server instead (`npm run build && npm start`).

## Safety

The app only displays text. Commands in a solution are shown for the user to copy and run themselves;
nothing is ever executed on, or changed on, the user's computer.
