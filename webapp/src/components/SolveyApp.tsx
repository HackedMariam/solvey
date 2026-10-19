"use client";

import { History as HistoryIcon, ImageIcon, LifeBuoy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { addToHistory, loadHistory, saveHistory, type HistoryEntry } from "@/lib/history";
import { toResult, WORKFLOW_TIMEOUT_MS, type SolveyResult } from "@/lib/ticket";
import { Clarify, Failure, Resolved, TicketCreated } from "./Results";
import { TicketForm, type Draft } from "./TicketForm";
import { Waiting } from "./Waiting";

type View =
  | { kind: "form"; error: string | null }
  | { kind: "waiting" }
  | { kind: "result"; result: SolveyResult };

const EMPTY: Draft = { title: "", description: "", file: null };

const STATUS_LABELS: Partial<Record<SolveyResult["status"], { text: string; className: string }>> = {
  resolved: { text: "Solved", className: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400" },
  needs_clarification: { text: "Question", className: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400" },
  ticket_created: { text: "Ticket", className: "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-400" },
};

function timeAgo(at: number) {
  const minutes = Math.round((Date.now() - at) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return new Date(at).toLocaleDateString();
}

async function sendTicket(draft: Draft, requestId: string, signal: AbortSignal): Promise<SolveyResult> {
  const init: RequestInit = { method: "POST", signal };
  if (draft.file) {
    const form = new FormData();
    form.append("request_id", requestId);
    form.append("title", draft.title);
    form.append("description", draft.description);
    form.append("attachment", draft.file, draft.file.name);
    init.body = form;
  } else {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify({ request_id: requestId, title: draft.title, description: draft.description });
  }

  let response: Response;
  try {
    response = await fetch("/api/ticket", init);
  } catch (error) {
    const name = error instanceof DOMException ? error.name : "";
    if (name === "AbortError") return { status: "error", code: "cancelled", message: "Request cancelled." };
    if (name === "TimeoutError") return { status: "error", code: "timeout", message: "The assistant took too long to answer." };
    return { status: "error", code: "network", message: "Check your connection." };
  }

  try {
    return toResult(await response.json());
  } catch {
    return {
      status: "error",
      code: response.status >= 500 ? "upstream_error" : "bad_response",
      message: `The server answered with an unexpected response (HTTP ${response.status}).`,
    };
  }
}

export function SolveyApp() {
  const [view, setView] = useState<View>({ kind: "form", error: null });
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [requestId, setRequestId] = useState("");
  const [formKey, setFormKey] = useState(0);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const controller = useRef<AbortController | null>(null);

  // localStorage only exists in the browser, so history is read after the first render.
  // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time sync from browser storage
  useEffect(() => setHistory(loadHistory()), []);

  async function submit(next: Draft, id: string) {
    setDraft(next);
    setRequestId(id);
    setView({ kind: "waiting" });
    window.scrollTo({ top: 0, behavior: "smooth" });

    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    // A little longer than the server's own limit, so the server's timeout message wins.
    const signal = AbortSignal.any([current.signal, AbortSignal.timeout(WORKFLOW_TIMEOUT_MS + 15_000)]);

    const result = await sendTicket(next, id, signal);
    if (controller.current !== current) return; // superseded by a newer request
    controller.current = null;

    if (result.status === "invalid_request") {
      setFormKey((k) => k + 1);
      setView({ kind: "form", error: result.message ?? "The request was not accepted." });
      return;
    }
    if (result.status !== "error") {
      setHistory((entries) =>
        addToHistory(entries, { id, title: next.title, description: next.description, at: Date.now(), result }),
      );
    }
    setView({ kind: "result", result });
  }

  function startNew() {
    setDraft(EMPTY);
    setRequestId("");
    setFormKey((k) => k + 1);
    setView({ kind: "form", error: null });
  }

  function editRequest() {
    setFormKey((k) => k + 1);
    setView({ kind: "form", error: null });
  }

  function openEntry(entry: HistoryEntry) {
    setDraft({ title: entry.title, description: entry.description, file: null });
    setRequestId(entry.id);
    setView({ kind: "result", result: entry.result });
  }

  const result = view.kind === "result" ? view.result : null;

  return (
    <div className="mx-auto flex w-full max-w-[720px] flex-1 flex-col px-4 pt-10 pb-12 sm:pt-16">
      <header className="mb-8 sm:mb-10">
        <button
          type="button"
          onClick={startNew}
          className="group inline-flex items-center gap-2.5 rounded-lg focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-4 focus-visible:outline-none dark:focus-visible:ring-offset-zinc-950"
          aria-label="Solvey, start a new request"
        >
          <span className="flex size-8 items-center justify-center rounded-lg bg-indigo-600 text-white dark:bg-indigo-500">
            <LifeBuoy className="size-4.5" aria-hidden />
          </span>
          <span className="text-lg font-semibold tracking-tight">Solvey</span>
        </button>
        <h1 className="mt-6 text-2xl font-semibold tracking-tight text-balance sm:text-3xl">IT help, instantly</h1>
        <p className="mt-2 text-[15px] text-zinc-500 dark:text-zinc-400">
          Describe the problem. You&apos;ll get a verified fix, a quick follow-up question, or a ticket for a technician.
        </p>
      </header>

      <main className="flex-1 space-y-4">
        {view.kind === "form" && (
          <TicketForm key={formKey} initial={draft} serverError={view.error} onSubmit={(d) => submit(d, crypto.randomUUID())} />
        )}

        {view.kind === "waiting" && (
          <Waiting
            hasImage={Boolean(draft.file)}
            onCancel={() => {
              controller.current?.abort();
            }}
          />
        )}

        {view.kind !== "form" && (draft.title || draft.description) && (
          <div className="flex items-start gap-3 rounded-2xl border border-zinc-200/70 px-4 py-3 text-sm dark:border-zinc-800">
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Your request</p>
              <p className="mt-0.5 truncate font-medium">{draft.title || draft.description.split("\n")[0]}</p>
              {draft.title && <p className="truncate text-zinc-500 dark:text-zinc-400">{draft.description.split("\n")[0]}</p>}
            </div>
            {draft.file && <ImageIcon className="mt-1 size-4 shrink-0 text-zinc-400" aria-label="Screenshot attached" />}
          </div>
        )}

        <div aria-live="polite">
          {result?.status === "resolved" && (
            <Resolved key={requestId} result={result} onNew={startNew} onAddDetails={editRequest} />
          )}
          {result?.status === "needs_clarification" && (
            <Clarify
              key={requestId + draft.description.length}
              result={result}
              onNew={startNew}
              onReply={(reply) =>
                submit({ ...draft, description: `${draft.description}\n\nAdditional details: ${reply}` }, requestId)
              }
            />
          )}
          {result?.status === "ticket_created" && <TicketCreated result={result} onNew={startNew} />}
          {(result?.status === "error" || result?.status === "invalid_request") && (
            <Failure result={result} onRetry={() => submit(draft, requestId)} onEdit={editRequest} />
          )}
        </div>

        {view.kind === "form" && history.length > 0 && (
          <section className="pt-6" aria-labelledby="history-heading">
            <div className="mb-2 flex items-center justify-between px-1">
              <h2 id="history-heading" className="flex items-center gap-2 text-sm font-medium text-zinc-500 dark:text-zinc-400">
                <HistoryIcon className="size-4" aria-hidden />
                Recent requests
              </h2>
              <button
                type="button"
                onClick={() => {
                  saveHistory([]);
                  setHistory([]);
                }}
                className="rounded-md px-1.5 py-0.5 text-xs text-zinc-400 hover:text-zinc-700 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none dark:hover:text-zinc-200"
              >
                Clear
              </button>
            </div>
            <ul className="divide-y divide-zinc-100 overflow-hidden rounded-2xl border border-zinc-200 bg-white dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900">
              {history.map((entry) => {
                const label = STATUS_LABELS[entry.result.status];
                return (
                  <li key={entry.id}>
                    <button
                      type="button"
                      onClick={() => openEntry(entry)}
                      className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-zinc-50 focus-visible:bg-zinc-50 focus-visible:outline-none dark:hover:bg-zinc-800/50 dark:focus-visible:bg-zinc-800/50"
                    >
                      <span className="min-w-0 flex-1 truncate text-sm">{entry.title || entry.description}</span>
                      {label && (
                        <span className={`shrink-0 rounded-md px-1.5 py-0.5 text-[11px] font-medium ${label.className}`}>
                          {label.text}
                        </span>
                      )}
                      <span className="w-16 shrink-0 text-right text-xs text-zinc-400">{timeAgo(entry.at)}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <p className="mt-2 px-1 text-xs text-zinc-400">Stored only in this browser.</p>
          </section>
        )}
      </main>

      <footer className="mt-12 text-center text-xs text-zinc-400">
        Solvey · Internal IT support assistant · Answers are AI-generated and checked before they are shown
      </footer>
    </div>
  );
}
