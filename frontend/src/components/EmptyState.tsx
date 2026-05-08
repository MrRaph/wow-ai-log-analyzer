import type { ReactNode } from "react";

// Decorative empty-state placeholder shown in lists/sections that have no
// items yet (e.g. "no analyses yet", "no reports yet"). The pulse-wave
// graphic echoes the brand mark to keep the dead area atmospheric instead
// of just leaving a bald sentence.
export function EmptyState({
  message,
  hint,
  graphic = "pulse",
}: {
  message: ReactNode;
  hint?: ReactNode;
  graphic?: "pulse" | "constellation" | "none";
}) {
  const src =
    graphic === "constellation"
      ? "/brand/empty-constellation.png"
      : graphic === "pulse"
        ? "/brand/empty-pulse.png"
        : null;
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-10 text-center">
      {src && (
        <img
          src={src}
          alt=""
          aria-hidden="true"
          className="h-24 w-auto opacity-50 sm:h-32"
        />
      )}
      <p className="max-w-md text-sm text-zinc-400">{message}</p>
      {hint && <p className="text-xs text-zinc-500">{hint}</p>}
    </div>
  );
}
