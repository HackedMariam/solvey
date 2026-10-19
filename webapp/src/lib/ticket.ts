// Shared request limits, response types and parsing for the Solvey n8n workflow
// (webhook "Main workflow", POST /webhook/solvey/main). Used by the browser and the API route.

export const LIMITS = {
  titleMax: 200,
  descriptionMin: 10,
  descriptionMax: 4000,
  imageMaxBytes: 5 * 1024 * 1024,
} as const;

export const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];

/** Generous upper bound for one workflow run (vision model + classifier + RAG + validator). */
export const WORKFLOW_TIMEOUT_MS = 240_000;

export type ErrorCode =
  | "network"
  | "timeout"
  | "upstream_error"
  | "bad_response"
  | "not_configured"
  | "cancelled";

export type SolveyResult =
  | { status: "resolved"; request_id?: string; solution?: unknown; sources?: unknown }
  | { status: "needs_clarification"; request_id?: string; question?: string }
  | { status: "ticket_created"; request_id?: string; ticket_number?: string }
  | { status: "invalid_request"; message?: string }
  | { status: "error"; code: ErrorCode; message: string };

/** Returns a user-facing error message, or null when the ticket text is acceptable. */
export function validateTicket(title: string, description: string): string | null {
  if (title.trim().length > LIMITS.titleMax) {
    return `The title can be at most ${LIMITS.titleMax} characters.`;
  }
  const length = description.trim().length;
  if (length < LIMITS.descriptionMin) {
    return `Please describe the problem in at least ${LIMITS.descriptionMin} characters.`;
  }
  if (length > LIMITS.descriptionMax) {
    return `The description can be at most ${LIMITS.descriptionMax} characters.`;
  }
  return null;
}

export function validateImage(file: { type: string; size: number }): string | null {
  if (!IMAGE_TYPES.includes(file.type)) return "Screenshots must be PNG, JPEG or WebP images.";
  if (file.size > LIMITS.imageMaxBytes) return "Screenshots can be at most 5 MB.";
  return null;
}

/** Turns any parsed response body into a known result; unknown shapes become an error. */
export function toResult(data: unknown): SolveyResult {
  const d = (data && typeof data === "object" ? data : {}) as Record<string, unknown>;
  const text = (v: unknown) => (typeof v === "string" && v.trim() ? v.trim() : undefined);
  const request_id = text(d.request_id);

  switch (d.status) {
    case "resolved":
      return { status: "resolved", request_id, solution: d.solution, sources: d.sources };
    case "needs_clarification":
      return { status: "needs_clarification", request_id, question: text(d.question) };
    case "ticket_created":
      return { status: "ticket_created", request_id, ticket_number: text(d.ticket_number) };
    case "invalid_request":
      return { status: "invalid_request", message: text(d.message) };
    case "error":
      return {
        status: "error",
        code: (text(d.code) as ErrorCode) ?? "upstream_error",
        message: text(d.message) ?? "Something went wrong.",
      };
    default:
      return { status: "error", code: "bad_response", message: "The assistant sent a response we couldn't read." };
  }
}

// ---------------------------------------------------------------------------
// Solution object written by the Resolution Agent (an LLM), validated by the Validator:
// { summary, steps: [{ instruction, command, source_ids }], warnings, escalate_if, confidence, final_message }
// Parsed defensively: every field may be missing or have an unexpected type.

export interface SolutionStep {
  text: string;
  command: string | null;
  sources: string[];
}

export interface Solution {
  summary: string | null;
  steps: SolutionStep[];
  warnings: string[];
  escalateIf: string[];
  finalMessage: string | null;
}

function str(value: unknown): string | null {
  if (typeof value === "string") return value.trim() || null;
  if (typeof value === "number") return String(value);
  return null;
}

function strList(value: unknown): string[] {
  const items = Array.isArray(value) ? value : [value];
  return items
    .map((item) =>
      item && typeof item === "object"
        ? str((item as Record<string, unknown>).text) ?? str((item as Record<string, unknown>).message)
        : str(item),
    )
    .filter((item): item is string => item !== null);
}

export function parseSolution(raw: unknown): Solution {
  if (typeof raw === "string") {
    return { summary: str(raw), steps: [], warnings: [], escalateIf: [], finalMessage: null };
  }
  const s = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;

  const steps = (Array.isArray(s.steps) ? s.steps : [])
    .map((step): SolutionStep => {
      if (typeof step === "string") return { text: step.trim(), command: null, sources: [] };
      const o = (step && typeof step === "object" ? step : {}) as Record<string, unknown>;
      return {
        text: str(o.instruction) ?? str(o.text) ?? str(o.step) ?? str(o.description) ?? "",
        command: str(o.command),
        sources: strList(o.source_ids ?? o.sources),
      };
    })
    .filter((step) => step.text || step.command);

  const summary = str(s.summary) ?? str(s.answer) ?? str(s.intro);
  const finalMessage = str(s.final_message) ?? str(s.outro);

  return {
    summary,
    steps,
    warnings: strList(s.warnings),
    escalateIf: strList(s.escalate_if),
    finalMessage: finalMessage && finalMessage !== summary ? finalMessage : null,
  };
}
