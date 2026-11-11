import { useId, useState, type KeyboardEvent } from "react";
import { useDrugSearch } from "../../hooks/useDrugSearch";
import { useI18n } from "../../i18n";
import type { DrugSuggestion } from "../../lib/drugs";

interface Props {
  /** A suggestion was chosen from the list. */
  onPick: (s: DrugSuggestion) => void;
  /** Enter pressed on free text with no highlighted suggestion: the caller resolves it (never guessed here). */
  onSubmitText: (text: string) => void;
  disabled?: boolean;
}

/** WAI-ARIA 1.2 combobox with a listbox popup. Brand and generic names are searched together. */
export function DrugAutocomplete({ onPick, onSubmitText, disabled }: Props) {
  const { t } = useI18n();
  const uid = useId();
  const listId = `${uid}-list`;
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const { state, results } = useDrugSearch(text);

  const showList = open && text.trim().length >= 2;
  const optionId = (i: number) => `${uid}-opt-${i}`;

  function pick(s: DrugSuggestion) {
    onPick(s);
    setText("");
    setOpen(false);
    setActive(-1);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => (results.length ? (i + 1) % results.length : -1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (results.length ? (i <= 0 ? results.length - 1 : i - 1) : -1));
    } else if (e.key === "Escape") {
      setOpen(false);
      setActive(-1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (showList && active >= 0 && results[active]) pick(results[active]);
      else if (text.trim()) {
        onSubmitText(text.trim());
        setText("");
        setOpen(false);
      }
    }
  }

  return (
    <div className="ac">
      <label htmlFor={`${uid}-input`} className="ac-label">{t("med.search.label")}</label>
      <div className="ac-row">
        <input
          id={`${uid}-input`}
          className="ac-input"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={showList && active >= 0 ? optionId(active) : undefined}
          autoComplete="off"
          spellCheck={false}
          maxLength={120}
          value={text}
          disabled={disabled}
          placeholder={t("med.search.placeholder")}
          onChange={(e) => {
            setText(e.target.value);
            setOpen(true);
            setActive(-1);
          }}
          onKeyDown={onKeyDown}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)} // let a click on an option land first
        />
        <button
          type="button"
          className="btn"
          disabled={disabled || !text.trim()}
          onClick={() => {
            onSubmitText(text.trim());
            setText("");
            setOpen(false);
          }}
        >
          {t("med.add")}
        </button>
      </div>

      {showList && (
        <ul id={listId} role="listbox" aria-label={t("med.search.label")} className="ac-list">
          {state === "loading" && <li className="ac-note" role="presentation">{t("common.loading")}</li>}
          {state === "error" && <li className="ac-note ac-error" role="presentation">{t("med.search.error")}</li>}
          {state === "ready" && results.length === 0 && <li className="ac-note" role="presentation">{t("med.search.empty")}</li>}
          {state === "ready" &&
            results.map((s, i) => (
              <li
                key={`${s.type}-${s.name}-${s.strength}-${i}`}
                id={optionId(i)}
                role="option"
                aria-selected={i === active}
                className="ac-option"
                onMouseDown={(e) => e.preventDefault()} // keep input focus
                onClick={() => pick(s)}
                onMouseEnter={() => setActive(i)}
              >
                <span className="ac-name">{s.name}{s.strength ? ` ${s.strength}` : ""}</span>
                <span className="ac-tag">{t(s.type === "brand" ? "med.type.brand" : "med.type.generic")}</span>
                {s.type === "brand" && <span className="ac-generic">→ {s.generic}</span>}
                {s.type === "brand" && !s.verified && <span className="ac-unrev">{t("med.badge.unreviewed")}</span>}
              </li>
            ))}
        </ul>
      )}

      {/* Screen readers: announce the result count without moving focus. */}
      <p className="visually-hidden" role="status" aria-live="polite">
        {state === "ready" && showList ? `${results.length} ${t("med.search.available")}` : ""}
      </p>
    </div>
  );
}
