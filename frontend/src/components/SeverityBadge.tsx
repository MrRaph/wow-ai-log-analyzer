"use client";
import clsx from "clsx";
import type { Severity } from "@/types/api";

const STYLES: Record<Severity, string> = {
  critical: "bg-red-500/15 text-red-400 ring-red-500/40",
  high: "bg-orange-500/15 text-orange-400 ring-orange-500/40",
  medium: "bg-yellow-500/10 text-yellow-300 ring-yellow-500/40",
  low: "bg-sky-500/10 text-sky-300 ring-sky-500/40",
  info: "bg-zinc-500/10 text-zinc-300 ring-zinc-500/40",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ring-1 ring-inset",
        STYLES[severity],
      )}
    >
      {severity}
    </span>
  );
}
