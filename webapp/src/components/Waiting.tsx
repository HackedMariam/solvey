"use client";

import { useEffect, useState } from "react";
import { Button, Card } from "./ui";

// Time-based captions describing what the workflow does. They do not reflect real progress.
const STAGE_SECONDS = 8;

function stagesFor(hasImage: boolean) {
  return [
    ...(hasImage ? ["Reading your screenshot"] : []),
    "Understanding the problem",
    "Searching the IT knowledge base",
    "Checking the answer",
  ];
}

export function Waiting({ hasImage, onCancel }: { hasImage: boolean; onCancel: () => void }) {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const stages = stagesFor(hasImage);
  // The vision model is the slowest step, so its caption stays up longer; the last caption holds.
  const durations = stages.map((_, i) => (hasImage && i === 0 ? STAGE_SECONDS * 3 : STAGE_SECONDS));
  let index = 0;
  let until = durations[0];
  while (index < stages.length - 1 && seconds >= until) {
    index += 1;
    until += durations[index];
  }
  const elapsed = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;

  return (
    <Card className="animate-fade-in">
      <div className="flex flex-col items-center py-6 text-center" role="status" aria-live="polite">
        <div className="relative h-1 w-40 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800" aria-hidden>
          <div className="animate-indeterminate absolute inset-y-0 w-2/5 rounded-full bg-indigo-500" />
        </div>
        <p key={index} className="animate-fade-in mt-6 text-base font-medium">
          {stages[index]}…
        </p>
        <p className="mt-1.5 text-sm text-zinc-500 dark:text-zinc-400">
          {hasImage ? "Requests with a screenshot can take up to 3 minutes." : "This usually takes under a minute."}
        </p>
        <p className="mt-4 font-mono text-xs text-zinc-400 tabular-nums" aria-hidden>
          {elapsed}
        </p>
        <Button variant="ghost" className="mt-4" onClick={onCancel}>
          Stop waiting
        </Button>
      </div>
    </Card>
  );
}
