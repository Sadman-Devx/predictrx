# PredictRx — Design System

*Bangla-first clinical decision-support interface — UX & visual design documentation*

This document defines how PredictRx should look, read and behave. Core idea: in a medical-safety tool,
**clarity and honesty beat decoration**. The interface must make it easy to see what is risky, why, and
how sure the system is.

---

## 1. User Experience (UX)

### 1.1 Core Principle
**Calm, clear, honest.** No alarmist red walls, no gamification. A doctor under time pressure should
find the highest-severity finding in seconds, see its source in one click, and never be shown more
confidence than the evidence supports.

### 1.2 Navigation Flow
- **Top bar:** logo, patient selector, language toggle (বাংলা / English), user menu.
- **Main flow (doctor):** Dashboard → Patient → **Scan / Add medications → Review & confirm → Analysis → Results**.
- Primary navigation stays small: *Patients · Analyses · Admin (role-gated)*.
- **Family users** see a separate, reduced layout: linked patients and read-only summaries only.

### 1.3 The Core Journey (screens)

1. **Dashboard** — recent patients/analyses, a single prominent "New analysis" action.
2. **Scan / Add** — drag-and-drop or camera upload for a prescription image, or manual entry with autocomplete.
   Shows a short privacy note and the consent status for this patient.
3. **Review & Confirm** (human-in-the-loop) — extracted drugs in an editable list next to the image.
   Each row shows the resolved generic name and a resolution badge: *Resolved · Confirmed by you · Unresolved*.
   The "Run analysis" button stays disabled until unresolved rows are fixed or explicitly removed.
4. **Analysis (progress)** — visible pipeline steps (Resolver → Notes → Interactions → Advisory → Verifier)
   updating live. This doubles as the agent-trace view.
5. **Results** — tabs: **Doctor view · Patient card · Agent trace · What-if**.
6. **Family view** — one calm page: a short plain-Bangla summary and a "talk to the doctor" prompt.

### 1.4 Results Screen (doctor view)
- Findings sorted by severity (major → moderate → minor → unknown).
- Each finding is a card: drug pair, severity label, one-line rationale, **evidence chips** (source name +
  open-source link/ID), **confidence**, and a **verification badge** (Verified · Unverified · Conflict).
- "Conflict" cards are visually distinct and explained in one sentence — they are never hidden.
- A persistent disclaimer strip: *decision support, not a diagnosis*.

### 1.5 Honest States
- **No record found:** "No interaction record found. This does not mean the combination is safe." (never a green "safe" tick).
- **Low confidence / unverified:** muted style + short reason.
- **Unresolved brand:** inline prompt to pick the generic; never auto-fill silently.
- **Model/API failure:** clear message, retry action, nothing partially shown as final.

### 1.6 Patient Card & Family View
- Short sentences, large text, plain Bangla, no medical jargon without a gloss.
- Never includes dosing or stop/start instructions. Ends with: "Please talk to your doctor before changing any medicine."
- Family view shows when it was last updated and who consented.

### 1.7 What-if (Digital Twin) tab
- Pick a hypothetical drug → see **added or changed findings** compared with the base run.
- Clearly labelled *Simulation for exploration*. Same evidence chips and honest states as the main results.

### 1.8 Loading, Empty, Error
- Skeleton blocks for results; a stepper for the pipeline (not a bare spinner).
- Empty states explain the next action ("Add a prescription to start").
- Errors say what happened and what to do next, in Bangla first.

---

## 2. Colour & Visual Theme

### 2.1 Palette (tokens)
| Token | Value | Use |
|---|---|---|
| `--bg` | `#F6F9F9` | page background |
| `--surface` | `#FFFFFF` | cards, panels |
| `--ink` | `#12262A` | primary text |
| `--ink-muted` | `#4A5F64` | secondary text |
| `--primary` | `#0F5C63` | primary actions, links, focus |
| `--primary-soft` | `#E1F0F1` | selected / subtle fills |
| `--border` | `#D5E2E3` | dividers |
| `--sev-major` | `#B3261E` | major severity |
| `--sev-moderate` | `#B26A00` | moderate severity |
| `--sev-minor` | `#2E7D5B` | minor severity |
| `--sev-unknown` | `#5B6770` | no record / unknown |
| `--conflict` | `#6B3FA0` | verifier conflict |

Hex values are starting points. **Check contrast (WCAG AA) for text on every background** before freezing them.

### 2.2 Rules
- **Never rely on colour alone.** Each severity pairs colour with an icon and a text label (মারাত্মক / মাঝারি / সামান্য / অজানা).
- No green "safe" state. The best a pair can be is "minor" or "no record found".
- Restrained use: colour appears on severity badges and the primary action, not as decoration.

---

## 3. Typography

### 3.1 Typeface Pairing
- **Bangla:** Noto Sans Bengali (readable at small sizes, complete conjunct support).
- **Latin / numerals / code-like labels:** Inter.
- Fallback stacks required for both; test Bangla rendering on common Android devices.

### 3.2 Scale
| Role | Size / weight |
|---|---|
| Page title | 28 / 600 |
| Section title | 20 / 600 |
| Body | 16 / 400 (Bangla line-height ≥ 1.6) |
| Small / captions | 14 / 400 |
| Severity badge | 13 / 600, letter-spacing normal |

### 3.3 Rules
- Bangla text gets slightly more line-height than Latin; avoid tight leading that clips matras.
- Use Bangla numerals only where the whole sentence is Bangla; keep drug names and doses in their written form.
- Drug names always show **generic + the brand as entered**.

---

## 4. UI Preferences

### 4.1 Shape Language
Soft but sober: `8px` card radius, `6px` inputs/buttons, `999px` pills for badges. Thin borders over heavy shadows.

### 4.2 Elevation
One subtle card shadow (`0 1px 2px rgba(18,38,42,.06)`) and one overlay shadow for modals/drawers. No stacked glows.

### 4.3 Motion
- Short, functional: `150–200ms` fades/slides; the pipeline stepper animates state changes.
- Respect `prefers-reduced-motion` everywhere; no decorative or looping animation on clinical screens.

### 4.4 Iconography
Simple outline icons (e.g. lucide). Severity icons are distinct in shape, not only colour.

### 4.5 Layout & Spacing
- 4px base grid; section rhythm `24–32px`; max content width ~1100px.
- Desktop: two-column results (findings list + detail/evidence panel). Mobile: single column, evidence in an expandable drawer.
- Touch targets ≥ 44px.

### 4.6 Component Inventory
| Component | Notes |
|---|---|
| `Button` | primary / secondary / quiet; loading state |
| `SeverityBadge` | colour + icon + label |
| `EvidenceChip` | source name + ID; opens source panel |
| `ConfidenceMeter` | numeric + short label; never shown without its basis |
| `VerificationBadge` | Verified / Unverified / Conflict |
| `MedicationRow` | raw text, resolved generic, status, edit/remove |
| `PipelineStepper` | five agent steps + live status |
| `DisclaimerStrip` | persistent, dismiss-proof on results pages |
| `LanguageToggle` | বাংলা / English; remembers choice |
| `ConsentBanner` | shows missing/active consent for the current patient |

### 4.7 Accessibility
- Keyboard-navigable, visible focus ring in `--primary`.
- ARIA labels in Bangla for icon-only controls.
- Severity and status announced as text for screen readers.
- Image upload has a text alternative path (manual entry).

### 4.8 Localization
- All strings in `i18n/bn.json` and `i18n/en.json`; no hard-coded UI text.
- Bangla is the default; English toggle available. Dates and numbers formatted per locale.
- Clinical wording for Bangla strings should be reviewed by a mentor/clinician before the demo.

---

## 5. Demo Considerations
- The demo path must be fast and legible on a projector: use the largest readable sizes on the Results screen.
- Keep a prepared synthetic prescription image and a second case that triggers an "unverified" or "no record" state,
  to show honesty behaviour on camera.
- Do not use any real patient's prescription.

---

## Summary — The 5 Principles
1. **Evidence before assertion** — every warning shows where it came from.
2. **Honest uncertainty** — "unknown" and "conflict" are first-class states.
3. **Human in the loop** — extracted drugs are confirmed by a person before analysis.
4. **Bangla first** — language, naming and wording designed for local use.
5. **Calm clarity** — severity is obvious without alarm; colour is never the only signal.
