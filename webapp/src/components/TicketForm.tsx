"use client";

import { ArrowRight, ImagePlus, Lock, X } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, useState, type FormEvent } from "react";
import { IMAGE_TYPES, LIMITS, validateImage, validateTicket } from "@/lib/ticket";
import { Button, Card } from "./ui";

export interface Draft {
  title: string;
  description: string;
  file: File | null;
}

const inputClass =
  "w-full rounded-xl border border-zinc-200 bg-white px-3.5 py-2.5 text-[15px] text-zinc-900 placeholder:text-zinc-400 transition-colors focus:border-indigo-500 focus:outline-none focus:ring-4 focus:ring-indigo-500/15 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100 dark:placeholder:text-zinc-500";

export function TicketForm({
  initial,
  serverError,
  onSubmit,
}: {
  initial: Draft;
  serverError: string | null;
  onSubmit: (draft: Draft) => void;
}) {
  const [title, setTitle] = useState(initial.title);
  const [description, setDescription] = useState(initial.description);
  const [file, setFile] = useState<File | null>(initial.file);
  const [error, setError] = useState<string | null>(serverError);
  const [dragging, setDragging] = useState(false);
  const [preview, setPreview] = useState<{ file: File; url: string } | null>(null);

  const textarea = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const ids = useId();

  // Grow the description box with its content.
  useLayoutEffect(() => {
    const el = textarea.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 420)}px`;
  }, [description]);

  // Thumbnail as a data URL, tagged with its file so a stale preview is never shown.
  useEffect(() => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setPreview({ file, url: String(reader.result) });
    reader.readAsDataURL(file);
    return () => reader.abort();
  }, [file]);
  const previewUrl = preview && preview.file === file ? preview.url : null;

  function pickFile(candidate: File | undefined) {
    if (!candidate) return;
    const problem = validateImage(candidate);
    if (problem) return setError(problem);
    setError(null);
    setFile(candidate);
  }

  function submit(event?: FormEvent) {
    event?.preventDefault();
    const problem = validateTicket(title, description) ?? (file ? validateImage(file) : null);
    if (problem) {
      setError(problem);
      textarea.current?.focus();
      return;
    }
    onSubmit({ title: title.trim(), description: description.trim(), file });
  }

  const length = description.trim().length;

  return (
    <Card>
      <form onSubmit={submit} noValidate className="space-y-5">
        <div className="space-y-1.5">
          <label htmlFor={`${ids}-title`} className="text-sm font-medium">
            Title <span className="font-normal text-zinc-400">(optional)</span>
          </label>
          <input
            id={`${ids}-title`}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={LIMITS.titleMax}
            placeholder="e.g. VPN won't connect"
            autoComplete="off"
            className={inputClass}
          />
        </div>

        <div className="space-y-1.5">
          <div className="flex items-baseline justify-between gap-3">
            <label htmlFor={`${ids}-description`} className="text-sm font-medium">
              What&apos;s going on?
            </label>
            <span
              className={`text-xs tabular-nums ${length > LIMITS.descriptionMax ? "text-rose-600" : "text-zinc-400"}`}
            >
              {length}/{LIMITS.descriptionMax}
            </span>
          </div>
          <textarea
            id={`${ids}-description`}
            ref={textarea}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit();
            }}
            rows={4}
            placeholder="Describe the problem: what you were doing, the exact error message, and what you already tried."
            aria-invalid={Boolean(error)}
            aria-describedby={`${ids}-hint${error ? ` ${ids}-error` : ""}`}
            className={`${inputClass} resize-none leading-relaxed`}
          />
          <p id={`${ids}-hint`} className="text-xs text-zinc-400">
            Ctrl + Enter to send
          </p>
        </div>

        <div className="space-y-1.5">
          <span className="text-sm font-medium">
            Screenshot <span className="font-normal text-zinc-400">(optional)</span>
          </span>
          {file ? (
            <div className="flex items-center gap-3 rounded-xl border border-zinc-200 p-2.5 dark:border-zinc-700">
              {previewUrl ? (
                // eslint-disable-next-line @next/next/no-img-element -- local data-URL preview
                <img src={previewUrl} alt="Selected screenshot" className="size-14 rounded-lg object-cover" />
              ) : (
                <div className="size-14 rounded-lg bg-zinc-100 dark:bg-zinc-800" aria-hidden />
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{file.name}</p>
                <p className="text-xs text-zinc-500">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
              </div>
              <Button variant="ghost" className="size-9 px-0" onClick={() => setFile(null)} aria-label="Remove screenshot">
                <X className="size-4" aria-hidden />
              </Button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                pickFile(e.dataTransfer.files[0]);
              }}
              className={`flex w-full flex-col items-center gap-1.5 rounded-xl border border-dashed px-4 py-6 text-center transition-colors focus-visible:border-indigo-500 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-indigo-500/15 ${
                dragging
                  ? "border-indigo-500 bg-indigo-50/60 dark:bg-indigo-500/10"
                  : "border-zinc-300 hover:border-zinc-400 hover:bg-zinc-50 dark:border-zinc-700 dark:hover:border-zinc-600 dark:hover:bg-zinc-800/40"
              }`}
            >
              <ImagePlus className="size-5 text-zinc-400" aria-hidden />
              <span className="text-sm">
                <span className="font-medium text-indigo-600 dark:text-indigo-400">Upload a screenshot</span> or drag
                it here
              </span>
              <span className="text-xs text-zinc-400">PNG, JPEG or WebP · up to 5 MB</span>
            </button>
          )}
          <input
            ref={fileInput}
            type="file"
            accept={IMAGE_TYPES.join(",")}
            className="sr-only"
            tabIndex={-1}
            aria-hidden
            onChange={(e) => {
              pickFile(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </div>

        {error && (
          <p id={`${ids}-error`} role="alert" className="rounded-xl bg-rose-50 px-3.5 py-2.5 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-400">
            {error}
          </p>
        )}

        <Button type="submit" className="h-11 w-full text-[15px]">
          Get help
          <ArrowRight className="size-4" aria-hidden />
        </Button>

        <p className="flex items-start justify-center gap-1.5 text-center text-xs text-zinc-500 dark:text-zinc-400">
          <Lock className="mt-px size-3.5 shrink-0" aria-hidden />
          Don&apos;t include passwords or personal data. Screenshots are processed by our AI models.
        </p>
      </form>
    </Card>
  );
}
