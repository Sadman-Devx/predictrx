import type { ReactNode } from "react";

export type Tone = "ok" | "warn" | "neutral" | "stop";

/** Distinct shapes: a status is never conveyed by colour alone (design.md §2.2). */
export function ToneGlyph({ tone }: { tone: Tone }) {
  const c = { width: 12, height: 12, viewBox: "0 0 12 12", "aria-hidden": true as const, focusable: "false" as const };
  if (tone === "ok")
    return (
      <svg {...c}>
        <circle cx="6" cy="6" r="5.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M3.4 6.2 5.2 8l3.4-3.6" fill="none" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    );
  if (tone === "warn")
    return (
      <svg {...c}>
        <path d="M6 1 11.5 11h-11z" fill="none" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    );
  if (tone === "stop")
    return (
      <svg {...c}>
        <rect x="1.5" y="1.5" width="9" height="9" rx="1" fill="none" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    );
  return (
    <svg {...c}>
      <circle cx="6" cy="6" r="5.25" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2.5 2" />
    </svg>
  );
}

/** Soft pill with a shape and a text label. */
export function StatusPill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`pill tone-${tone}`}>
      <ToneGlyph tone={tone} />
      {children}
    </span>
  );
}