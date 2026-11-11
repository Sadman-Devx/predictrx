import { useI18n } from "../../i18n";

export function LanguageToggle() {
  const { lang, setLang } = useI18n();
  return (
    <div className="lang-toggle" role="group" aria-label="Language / ভাষা">
      <button type="button" aria-pressed={lang === "bn"} onClick={() => setLang("bn")}>বাংলা</button>
      <button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")}>English</button>
    </div>
  );
}
