// Last few requests, kept only in this browser's localStorage as a convenience.
// Storage can be unavailable (private mode, blocked site data), so every access is guarded.

import type { SolveyResult } from "./ticket";

export interface HistoryEntry {
  id: string;
  title: string;
  description: string;
  at: number;
  result: SolveyResult;
}

const KEY = "solvey.history.v1";
const MAX_ENTRIES = 10;

export function loadHistory(): HistoryEntry[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((e) => e && typeof e.id === "string" && e.result) : [];
  } catch {
    return [];
  }
}

export function saveHistory(entries: HistoryEntry[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(entries.slice(0, MAX_ENTRIES)));
  } catch {
    // storage full or blocked: history is optional
  }
}

/** Adds or replaces an entry (a clarification reply keeps the same id) and returns the new list. */
export function addToHistory(entries: HistoryEntry[], entry: HistoryEntry): HistoryEntry[] {
  const next = [entry, ...entries.filter((e) => e.id !== entry.id)].slice(0, MAX_ENTRIES);
  saveHistory(next);
  return next;
}
