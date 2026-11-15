import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import "../../styles/results.css";

export interface TabDef {
  id: string;
  label: string;
  panel: ReactNode;
}

interface Props {
  tabs: TabDef[];
  active: string;
  onChange: (id: string) => void;
  /** Accessible name of the tab list. */
  label: string;
}

/**
 * Accessible tabs (WAI-ARIA tabs pattern): Left/Right/Home/End move between tabs, only the active tab is in the tab order,
 * every panel stays in the DOM (hidden when inactive) so `aria-controls` always points at something real.
 */
export function Tabs({ tabs, active, onChange, label }: Props) {
  const uid = useId();
  const buttons = useRef(new Map<string, HTMLButtonElement>());
  const current = Math.max(0, tabs.findIndex((t) => t.id === active));

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    let next = current;
    if (e.key === "ArrowRight") next = (current + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (current - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    else return;
    e.preventDefault();
    const target = tabs[next];
    onChange(target.id);
    buttons.current.get(target.id)?.focus();
  }

  return (
    <div className="tabs">
      <div className="tablist" role="tablist" aria-label={label} onKeyDown={onKeyDown}>
        {tabs.map((tab) => {
          const selected = tab.id === tabs[current].id;
          return (
            <button
              key={tab.id}
              ref={(el) => {
                if (el) buttons.current.set(tab.id, el);
                else buttons.current.delete(tab.id);
              }}
              type="button"
              role="tab"
              id={`${uid}-tab-${tab.id}`}
              className="tab"
              aria-selected={selected}
              aria-controls={`${uid}-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(tab.id)}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {tabs.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`${uid}-panel-${tab.id}`}
          aria-labelledby={`${uid}-tab-${tab.id}`}
          className="tabpanel"
          hidden={tab.id !== tabs[current].id}
        >
          {tab.panel}
        </div>
      ))}
    </div>
  );
}