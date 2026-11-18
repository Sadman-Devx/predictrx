import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import bnBase from "./bn.json";
import enBase from "./en.json";
import evidenceBn from "./evidence.bn.json";
import accountBn from "./account.bn.json";
import accountEn from "./account.en.json";
import evidenceEn from "./evidence.en.json";
import evalBn from "./evaluation.bn.json";
import evalEn from "./evaluation.en.json";
import listBn from "./list.bn.json";
import listEn from "./list.en.json";
import insightsBn from "./insights.bn.json";
import insightsEn from "./insights.en.json";

// The Evidence panel strings live in their own small files (evidence.bn.json / evidence.en.json) and are merged here,
// so every UI string still comes from i18n files and nothing is hard-coded in a component.
const bn = { ...bnBase, ...evidenceBn, ...listBn, ...accountBn, ...evalBn, ...insightsBn };
const en = { ...enBase, ...evidenceEn, ...listEn, ...accountEn, ...evalEn, ...insightsEn };

export type Lang = "bn" | "en";
export type MessageKey = keyof typeof bn;
export type MessageVars = Record<string, string | number>;

const dictionaries: Record<Lang, Record<MessageKey, string>> = { bn, en };

interface I18nValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  /** `t("key")` or `t("key", { n: 3 })` — placeholders look like {{n}}. */
  t: (key: MessageKey, vars?: MessageVars) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

function initialLang(): Lang {
  try {
    const saved = window.localStorage.getItem("predictrx.lang");
    if (saved === "bn" || saved === "en") return saved;
  } catch {
    /* storage unavailable */
  }
  return "bn"; // Bangla is the default
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      window.localStorage.setItem("predictrx.lang", l); // language preference only, never tokens
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo<I18nValue>(
    () => ({
      lang,
      setLang,
      t: (key, vars) => {
        const msg = dictionaries[lang][key] ?? dictionaries.en[key] ?? key;
        if (!vars) return msg;
        return msg.replace(/\{\{(\w+)\}\}/g, (whole, name: string) => (name in vars ? String(vars[name]) : whole));
      },
    }),
    [lang, setLang],
  );
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside <I18nProvider>");
  return ctx;
}