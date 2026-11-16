import type { ReactNode } from "react";
import { useI18n } from "../../i18n";
import { ToneGlyph, type Tone } from "./StatusPill";

export type StateKind = "loading" | "empty" | "error";

interface Props {
  kind: StateKind;
  /** Short heading. Loading and error have a default; an empty state says what is missing in its own words. */
  title?: string;
  /** Explanation and the next step, in plain words. */
  children?: ReactNode;
  /** Shows a "Retry" button. Only pass it when asking again can help. */
  onRetry?: () => void;
  /** Any other next step, e.g. a link button. */
  action?: ReactNode;
  /** Render without its own card, for use inside another card. */
  bare?: boolean;
}

/**
 * One look for the three states every screen has (design.md §1.8): loading, empty, error.
 * Each carries a shape and a text label, never colour alone. An error is announced (role="alert"), a loading state is a
 * polite status, and neither ever shows a partial result as if it were final.
 */
export function StateBlock({ kind, title, children, onRetry, action, bare = false }: Props) {
  const { t } = useI18n();
  const tone: Tone = kind === "error" ? "stop" : "neutral";
  const role = kind === "error" ? "alert" : kind === "loading" ? "status" : undefined;
  const heading = title ?? (kind === "error" ? t("state.error.title") : kind === "loading" ? t("common.loading") : undefined);

  return (
    <div
      className={`${bare ? "" : "card "}state state-${kind}`}
      role={role}
      aria-busy={kind === "loading" ? true : undefined}
    >
      <div className="state-head">
        <span className="state-glyph">
          <ToneGlyph tone={tone} />
        </span>
        {heading && <p className="state-title">{heading}</p>}
      </div>

      {kind === "loading" && (
        <div className="state-skels" aria-hidden="true">
          <span className="skeleton state-skel" />
          <span className="skeleton state-skel short" />
        </div>
      )}

      {children && <div className="state-text">{children}</div>}

      {(onRetry || action) && (
        <div className="state-actions">
          {onRetry && (
            <button type="button" className="btn secondary" onClick={onRetry}>
              {t("common.retry")}
            </button>
          )}
          {action}
        </div>
      )}
    </div>
  );
}