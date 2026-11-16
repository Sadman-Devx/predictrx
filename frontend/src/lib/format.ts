import type { Lang } from "../i18n";

/**
 * "8 Nov 2026, 21:53" in the reader's language (digits follow the locale: Bangla digits in Bangla).
 * Returns "" when the value is missing or not a date, so a caller can simply leave the line out.
 */
export function formatWhen(value: string | null | undefined, lang: Lang): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  try {
    return new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
  } catch {
    return date.toISOString();
  }
}

export interface PickedText {
  text: string;
  /** The language the text is actually written in (may differ from the one the person asked for). */
  lang: Lang;
}

/** Text in the current language; falls back to the other one (and says which) instead of showing nothing. */
export function pickLangText(bn: string, en: string, lang: Lang): PickedText | null {
  const text: Record<Lang, string> = { bn: bn.trim(), en: en.trim() };
  const order: Lang[] = lang === "bn" ? ["bn", "en"] : ["en", "bn"];
  for (const l of order) if (text[l]) return { text: text[l], lang: l };
  return null;
}

/** Split a block of text into paragraphs (blank lines and single line breaks both start a new one). */
export function paragraphs(text: string): string[] {
  return text
    .split(/\r?\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
}