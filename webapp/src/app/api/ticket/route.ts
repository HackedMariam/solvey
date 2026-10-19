// Thin proxy to the n8n workflow: validates the request, forwards it (JSON, or multipart with the
// screenshot in the "attachment" field) and returns n8n's JSON unchanged. Ticket text and images are
// never logged or stored here.

import { LIMITS, WORKFLOW_TIMEOUT_MS, validateImage, validateTicket } from "@/lib/ticket";

// Hosting platforms (e.g. Vercel) read this as the function's time limit, in seconds.
export const maxDuration = 300;

// Large enough for a 5 MB screenshot plus text; anything bigger is rejected before reading.
const MAX_REQUEST_BYTES = LIMITS.imageMaxBytes + 64 * 1024;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function reply(status: number, body: Record<string, unknown>) {
  return Response.json(body, { status });
}

/** Checks the file's first bytes, so a renamed non-image is rejected even if its MIME type claims otherwise. */
async function looksLikeImage(file: File) {
  const b = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  const png = b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47;
  const jpeg = b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff;
  const webp =
    String.fromCharCode(...b.slice(0, 4)) === "RIFF" && String.fromCharCode(...b.slice(8, 12)) === "WEBP";
  return png || jpeg || webp;
}

export async function POST(request: Request) {
  const webhookUrl = process.env.N8N_WEBHOOK_URL;
  if (!webhookUrl) {
    return reply(500, { status: "error", code: "not_configured", message: "The assistant is not configured yet." });
  }

  // 1. Read the incoming request.
  let title = "";
  let description = "";
  let requestId = "";
  let file: File | null = null;
  const contentType = request.headers.get("content-type") ?? "";
  if (Number(request.headers.get("content-length") ?? 0) > MAX_REQUEST_BYTES) {
    return reply(413, { status: "invalid_request", message: "Screenshots can be at most 5 MB." });
  }
  try {
    if (contentType.includes("multipart/form-data")) {
      const form = await request.formData();
      title = String(form.get("title") ?? "");
      description = String(form.get("description") ?? "");
      requestId = String(form.get("request_id") ?? "");
      const attachment = form.get("attachment");
      if (attachment instanceof File && attachment.size > 0) file = attachment;
    } else if (contentType.includes("application/json")) {
      const body = (await request.json()) as Record<string, unknown>;
      title = typeof body.title === "string" ? body.title : "";
      description = typeof body.description === "string" ? body.description : "";
      requestId = typeof body.request_id === "string" ? body.request_id : "";
    } else {
      return reply(415, { status: "invalid_request", message: "Send JSON or multipart/form-data." });
    }
  } catch {
    return reply(400, { status: "invalid_request", message: "The request could not be read." });
  }

  // 2. Validate.
  title = title.trim();
  description = description.trim();
  const problem =
    validateTicket(title, description) ??
    (file ? validateImage(file) ?? ((await looksLikeImage(file)) ? null : "The screenshot is not a valid image.") : null);
  if (problem) return reply(400, { status: "invalid_request", message: problem });
  if (!UUID.test(requestId)) requestId = crypto.randomUUID();

  // 3. Forward to n8n.
  const headers: Record<string, string> = {};
  if (process.env.N8N_WEBHOOK_SECRET) headers["X-Solvey-Secret"] = process.env.N8N_WEBHOOK_SECRET;

  let body: BodyInit;
  if (file) {
    const form = new FormData();
    form.append("request_id", requestId);
    form.append("title", title);
    form.append("description", description);
    form.append("attachment", file, file.name || "screenshot");
    body = form; // fetch sets the multipart boundary itself
  } else {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify({ request_id: requestId, title, description });
  }

  let upstream: Response;
  try {
    upstream = await fetch(webhookUrl, {
      method: "POST",
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(WORKFLOW_TIMEOUT_MS),
    });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "TimeoutError";
    console.error(`[api/ticket] ${requestId}: ${timedOut ? "timeout" : "workflow unreachable"}`);
    return timedOut
      ? reply(504, { status: "error", code: "timeout", message: "The assistant took too long to answer." })
      : reply(502, { status: "error", code: "network", message: "The assistant could not be reached." });
  }

  // 4. Return n8n's JSON unchanged; anything else becomes a friendly error.
  const text = await upstream.text();
  let data: unknown = null;
  try {
    data = JSON.parse(text);
  } catch {
    // handled below
  }

  if (!upstream.ok) {
    console.error(`[api/ticket] ${requestId}: workflow returned HTTP ${upstream.status}`);
    return reply(502, {
      status: "error",
      code: "upstream_error",
      message:
        upstream.status === 404
          ? "The assistant workflow is not active."
          : "The assistant ran into a problem while handling your request.",
    });
  }
  if (!data || typeof data !== "object" || !("status" in data)) {
    console.error(`[api/ticket] ${requestId}: workflow returned an unreadable response`);
    return reply(502, { status: "error", code: "bad_response", message: "The assistant sent a response we couldn't read." });
  }
  return Response.json(data);
}
