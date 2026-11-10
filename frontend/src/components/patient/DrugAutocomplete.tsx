import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { useDebounce } from "../../hooks/useDebounce";
import { useI18n } from "../../i18n";
import { searchDrugs } from "../../lib/clinical";
import type { DrugSuggestion } from "../../lib/types";

interface Props {
  id?: string;
  text: string;
  onTextChange: (text: string) => void;
  picked: DrugSuggestion | null;
  onPick: (s: DrugSuggestion | null) => void;
}

const MIN_CHARS = 2;

export function DrugAutocomplete({ id, text, onTextChange, picked, onPick }: Props) {
  const { t } = useI18n();
  const uid = useId();
  const listId = `${uid}-list`;
  const optionId = (i: number) => `${uid}-opt-${i}`;

  const [items, setItems] = useState<DrugSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(-1);
  const rootRef = useRef<HTMLDivElement>(null);

  const query = useDebounce(text.trim(), 250);

  useEffect(() => {
    if (picked || query.length < MIN_CHARS) {
      setItems([]);
      setLoading(false);
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    searchDrugs(query, ctrl.signal)
      .then((res) => {
        if (ctrl.signal.aborted) return;
        setItems(res);
        setActive(-1);
      })
      .catch(() => {
        if (!ctrl.signal.aborted) setItems([]);
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [query, picked]);

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  function choose(s: DrugSuggestion) {
    onPick(s);
    onTextChange(s.label);
    setOpen(false);
    setActive(-1);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => (items.length ? (i + 1) % items.length : -1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (items.length ? (i <= 0 ? items.length - 1 : i - 1) : -1));
    } else if (e.key === "Enter" && open && active >= 0 && items[active]) {
      e.preventDefault();
      choose(items[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  const showList = open && !picked && query.length >= MIN_CHARS;

  return (
    <div className="combo" ref={rootRef}>
      <input
        id={id}
        type="text"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={showList && active >= 0 ? optionId(active) : undefined}
        autoComplete="off"
        maxLength={200}
        value={text}
        onChange={(e) => {
          onTextChange(e.target.value);
          if (picked) onPick(null);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />

      {showList && (
        <ul id={listId} role="listbox" aria-label={t("meds.suggestions")} className="combo-list">
          {loading && items.length === 0 && <li className="combo-note muted">{t("meds.suggestions.searching")}</li>}
          {!loading && items.length === 0 && <li className="combo-note muted">{t("meds.suggestions.none")}</li>}
          {items.map((s, i) => (
            <li
              key={`${s.kind}-${s.drug_id}-${s.label}-${s.strength}`}
              id={optionId(i)}
              role="option"
              aria-selected={i === active}
              className={i === active ? "combo-opt active" : "combo-opt"}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(s)}
              onMouseEnter={() => setActive(i)}
            >
              <span>
                <strong>{s.label}</strong>
                {s.strength ? <span className="muted"> {s.strength}</span> : null}
                {s.kind === "brand" ? <span className="muted small"> → {s.generic_name}</span> : null}
              </span>
              <span className="badge">{s.kind === "brand" ? t("meds.kind.brand") : t("meds.kind.generic")}</span>
            </li>
          ))}
        </ul>
      )}

      {picked && (
        <p className="combo-picked small">
          {t("meds.picked")}: <strong>{picked.generic_name}</strong>{" "}
          <button type="button" className="link-btn" onClick={() => onPick(null)}>
            {t("meds.clearPick")}
          </button>
        </p>
      )}
    </div>
  );
}