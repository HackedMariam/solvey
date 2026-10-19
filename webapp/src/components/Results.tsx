"use client";

import { AlertTriangle, CheckCircle2, CircleAlert, MessageCircleQuestion, PhoneCall, RotateCcw, Send, Ticket } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import { LIMITS, parseSolution, type SolveyResult } from "@/lib/ticket";
import { Button, Chip, CopyButton, ResultCard } from "./ui";

type ResultOf<S extends SolveyResult["status"]> = Extract<SolveyResult, { status: S }>;

function uniqueStrings(value: unknown): string[] {
  const items = Array.isArray(value) ? value : [];
  return [...new Set(items.filter((v): v is string => typeof v === "string" && v.trim() !== ""))];
}

function Note({ icon, title, items, tone }: { icon: React.ReactNode; title: string; items: string[]; tone: "amber" | "zinc" }) {
  if (items.length === 0) return null;
  const toneClass =
    tone === "amber"
      ? "bg-amber-50 text-amber-900 dark:bg-amber-500/10 dark:text-amber-200"
      : "bg-zinc-50 text-zinc-700 dark:bg-zinc-800/60 dark:text-zinc-300";
  return (
    <div className={`rounded-xl px-4 py-3 text-sm ${toneClass}`}>
      <p className="flex items-center gap-2 font-medium">
        {icon}
        {title}
      </p>
      <ul className="mt-1.5 list-disc space-y-1 pl-6 leading-relaxed">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function Resolved({
  result,
  onNew,
  onAddDetails,
}: {
  result: ResultOf<"resolved">;
  onNew: () => void;
  onAddDetails: () => void;
}) {
  const [notHelpful, setNotHelpful] = useState(false);
  const solution = parseSolution(result.solution);
  const sources = uniqueStrings(result.sources);
  const empty = !solution.summary && solution.steps.length === 0 && !solution.finalMessage;

  return (
    <ResultCard accent="green" icon={<CheckCircle2 className="size-5" />} eyebrow="Solved" title="Here's what to try">
      <div className="space-y-5 text-[15px] leading-relaxed">
        {solution.summary && <p className="text-zinc-700 dark:text-zinc-300">{solution.summary}</p>}
        {empty && (
          <p className="text-zinc-700 dark:text-zinc-300">
            The assistant marked this as solved but sent no steps. Please add details and try again.
          </p>
        )}

        <Note
          icon={<AlertTriangle className="size-4" aria-hidden />}
          title="Before you start"
          items={solution.warnings}
          tone="amber"
        />

        {solution.steps.length > 0 && (
          <ol className="space-y-4">
            {solution.steps.map((step, i) => (
              <li key={i} className="flex gap-3.5">
                <span
                  className="flex size-6 shrink-0 items-center justify-center rounded-full bg-zinc-100 text-xs font-semibold text-zinc-600 tabular-nums dark:bg-zinc-800 dark:text-zinc-300"
                  aria-hidden
                >
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1 space-y-2">
                  {step.text && <p>{step.text}</p>}
                  {step.command && (
                    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-950">
                      <div className="flex items-center justify-between border-b border-zinc-200 py-1 pr-1.5 pl-3 dark:border-zinc-800">
                        <span className="text-[11px] font-medium tracking-wide text-zinc-400 uppercase">Command</span>
                        <CopyButton text={step.command} label="Copy command" />
                      </div>
                      <pre className="overflow-x-auto px-3 py-2.5 font-mono text-[13px] leading-relaxed whitespace-pre-wrap [overflow-wrap:anywhere]">
                        {step.command}
                      </pre>
                    </div>
                  )}
                  {step.sources.length > 0 && (
                    <div className="flex flex-wrap gap-1.5" aria-label="Sources for this step">
                      {step.sources.map((source) => (
                        <Chip key={source}>{source}</Chip>
                      ))}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}

        <Note
          icon={<PhoneCall className="size-4" aria-hidden />}
          title="Contact IT if"
          items={solution.escalateIf}
          tone="zinc"
        />

        {solution.finalMessage && <p className="text-zinc-700 dark:text-zinc-300">{solution.finalMessage}</p>}

        {sources.length > 0 && (
          <div className="border-t border-zinc-100 pt-4 dark:border-zinc-800">
            <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Sources from the IT knowledge base</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {sources.map((source) => (
                <Chip key={source}>{source}</Chip>
              ))}
            </div>
          </div>
        )}
      </div>

      {notHelpful && (
        <div className="animate-fade-in mt-5 rounded-xl bg-zinc-50 px-4 py-3 text-sm leading-relaxed text-zinc-700 dark:bg-zinc-800/60 dark:text-zinc-300">
          Sorry about that. Submit the request again with what you tried and what happened. If Solvey still
          can&apos;t solve it, it opens a ticket for a technician.
          <div className="mt-3">
            <Button variant="secondary" onClick={onAddDetails}>
              Add details and resubmit
            </Button>
          </div>
        </div>
      )}

      <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        {!notHelpful ? (
          <Button variant="ghost" onClick={() => setNotHelpful(true)}>
            This didn&apos;t help
          </Button>
        ) : (
          <span />
        )}
        <Button variant="secondary" onClick={onNew}>
          New request
        </Button>
      </div>
    </ResultCard>
  );
}

export function Clarify({
  result,
  onReply,
  onNew,
}: {
  result: ResultOf<"needs_clarification">;
  onReply: (reply: string) => void;
  onNew: () => void;
}) {
  const [reply, setReply] = useState("");
  const [error, setError] = useState<string | null>(null);
  const id = useId();

  function submit(event?: FormEvent | React.KeyboardEvent) {
    event?.preventDefault();
    if (reply.trim().length < 3) return setError("Please type your answer first.");
    onReply(reply.trim());
  }

  return (
    <ResultCard
      accent="amber"
      icon={<MessageCircleQuestion className="size-5" />}
      eyebrow="One more detail"
      title="Help us narrow it down"
    >
      <p className="text-[15px] leading-relaxed text-zinc-700 dark:text-zinc-300">
        {result.question ?? "Could you share the exact error message and the application or device involved?"}
      </p>
      <form onSubmit={submit} className="mt-4 space-y-3" noValidate>
        <label htmlFor={id} className="sr-only">
          Your answer
        </label>
        <textarea
          id={id}
          value={reply}
          onChange={(e) => setReply(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(e);
          }}
          rows={3}
          maxLength={LIMITS.descriptionMax}
          placeholder="Your answer"
          aria-invalid={Boolean(error)}
          className="w-full resize-none rounded-xl border border-zinc-200 bg-white px-3.5 py-2.5 text-[15px] leading-relaxed placeholder:text-zinc-400 focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/15 focus:outline-none dark:border-zinc-700 dark:bg-zinc-950"
        />
        {error && (
          <p role="alert" className="text-sm text-rose-600 dark:text-rose-400">
            {error}
          </p>
        )}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
          <Button variant="ghost" onClick={onNew}>
            New request
          </Button>
          <Button type="submit">
            Send answer
            <Send className="size-4" aria-hidden />
          </Button>
        </div>
      </form>
    </ResultCard>
  );
}

export function TicketCreated({ result, onNew }: { result: ResultOf<"ticket_created">; onNew: () => void }) {
  return (
    <ResultCard
      accent="blue"
      icon={<Ticket className="size-5" />}
      eyebrow="Passed to IT support"
      title="A technician will take it from here"
    >
      <p className="text-[15px] leading-relaxed text-zinc-700 dark:text-zinc-300">
        Solvey couldn&apos;t safely solve this one automatically, so it opened a support ticket with your
        description. Keep the ticket number for reference.
      </p>
      {result.ticket_number && (
        <div className="mt-4 flex items-center justify-between gap-3 rounded-xl border border-zinc-200 px-4 py-3 dark:border-zinc-700">
          <div>
            <p className="text-xs text-zinc-500 dark:text-zinc-400">Ticket number</p>
            <p className="font-mono text-lg font-semibold tracking-tight">{result.ticket_number}</p>
          </div>
          <CopyButton text={result.ticket_number} label="Copy number" />
        </div>
      )}
      <div className="mt-6 flex justify-end">
        <Button variant="secondary" onClick={onNew}>
          New request
        </Button>
      </div>
    </ResultCard>
  );
}

const ERROR_TITLES: Record<string, string> = {
  timeout: "This is taking too long",
  network: "We couldn't reach the assistant",
  cancelled: "You stopped waiting",
  invalid: "Something is missing",
};

export function Failure({
  result,
  onRetry,
  onEdit,
}: {
  result: ResultOf<"error"> | ResultOf<"invalid_request">;
  onRetry: () => void;
  onEdit: () => void;
}) {
  const invalid = result.status === "invalid_request";
  const code = invalid ? "invalid" : result.code;
  const message = invalid
    ? (result.message ?? "The request was not accepted.")
    : code === "cancelled"
      ? "The assistant may still finish in the background, but this page won't show the result."
      : `${result.message} Please try again in a moment. If it keeps happening, contact IT support directly.`;

  return (
    <ResultCard
      accent="red"
      icon={<CircleAlert className="size-5" />}
      eyebrow={invalid ? "Check your request" : "Something went wrong"}
      title={ERROR_TITLES[code] ?? "The assistant ran into a problem"}
    >
      <p className="text-[15px] leading-relaxed text-zinc-700 dark:text-zinc-300">{message}</p>
      <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button variant={invalid ? "primary" : "ghost"} onClick={onEdit}>
          Edit request
        </Button>
        {!invalid && (
          <Button onClick={onRetry}>
            <RotateCcw className="size-4" aria-hidden />
            Try again
          </Button>
        )}
      </div>
    </ResultCard>
  );
}
