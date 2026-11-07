# PredictRx — Engineering Rule Book

**Purpose:** What to avoid and why — across backend, AI, medical safety, privacy, frontend, data and process —
so the team doesn't quietly reintroduce a problem the project already designed around.

Each rule says what to avoid and gives the reason. A rule without a reason gets worked around the first time it is inconvenient.

---

## 1. Medical Safety & Product Claims — Avoid

- **Never present output as diagnosis, treatment advice, or dosing guidance.** PredictRx is decision support
  for a clinician. The patient card never says to start, stop, or change a medicine or a dose.
- **Never show a "safe" state.** The best statement available is "minor" or "no interaction record found —
  this does not mean the combination is safe." Absence of data is not evidence of safety.
- **Never display a warning without a source.** A finding with severity other than `unknown` must carry
  evidence (interaction record or retrieved chunk). No source → "insufficient evidence — consult a clinician."
- **Never hide a Verifier `conflict` or `unverified` result.** Disagreement between agents and the table is
  information the doctor needs.
- **Never invent or auto-fill a brand→generic match.** Low confidence = `unresolved` and ask the user.
- **Never skip the human confirmation step after OCR.** A misread drug name corrupts everything downstream.
- **Never quote accuracy, recall, or time-saved numbers that were not produced by a recorded run.**
  State the test-set size next to every number.

## 2. AI / Agents / RAG — Avoid

- **Avoid free-form LLM output as a source of truth.** Facts come from retrieved chunks and the interaction
  table; the model phrases them, it does not originate them.
- **Never let the Advisory agent add facts not present in the findings.** It summarizes; it does not research.
- **Never skip the output guardrail.** It enforces: evidence present, no dosing language, disclaimer attached.
- **Avoid evaluating on the same data the system retrieves from.** DDInter and openFDA feed RAG and the
  Verifier, so grading against them alone is circular. Build the test set from an independent source or a
  pharmacist/mentor reviewer, and split dev/test. Do not tune on the test split.
- **Avoid changing chunking, embedding model, or prompts without re-running the eval.** Silent retrieval
  changes are how quality quietly drops.
- **Never hard-code model names, API keys or provider URLs in agents.** Use the LLM router and environment config.
- **Avoid unbounded agent loops.** Every graph run has a step limit and timeout; failures end in a clear failed state.
- **Never call an LLM synchronously inside a request/response cycle.** Use Celery; return a run ID.

## 3. Privacy & Security — Avoid

- **Never send raw free-text patient notes to a cloud LLM.** Redact PII first (names, phones, addresses, IDs).
  Sensitive free-text steps prefer the local Ollama path.
- **Never use real patient data in the demo, tests, repo or video.** Synthetic or explicitly consented cases only.
- **Never commit prescription images, datasets with personal data, or secrets.** `.env` is git-ignored;
  `.env.example` shows the shape without values.
- **Never expose prescription images through public URLs.** Private storage, short retention (`retain_until`).
- **Never show a family user anything without an active `Consent` + `FamilyLink`.** Check on every request.
- **Every patient-data read, analysis, family view and consent change writes an `AuditLog` entry.**
  Features that skip the audit trail are not done.
- **Avoid logging PII.** Logs and traces store redacted summaries only.
- **Never weaken auth "temporarily"** (token lifetimes, permission checks, CORS). Temporary shortcuts become permanent.
- **Never trust client-supplied roles or ownership.** Derive them server-side from the authenticated user.

## 4. Backend (Django) — Avoid

- **Avoid business logic in `views.py`.** Views are thin HTTP adapters; logic lives in `services.py` so it is testable.
- **Never create two analysis runs for one click.** `idempotency_key` is unique; retries return the same run.
- **Never change `RiskFinding`/`AnalysisRun` history in place.** Runs are snapshots; new analysis = new run.
- **Avoid N+1 queries** on findings, trace and search endpoints (`select_related`/`prefetch_related`).
- **Avoid `save()` without `update_fields`** when only a field or two changed.
- **Avoid bare `except:`.** Catch the specific exception; swallowing errors hides safety-relevant failures.
- **Never delete a `Drug`, `Medication` or `Patient` referenced by an analysis run.** `PROTECT` is intentional.
- **Never run `makemigrations` output on shared data without reading it.**
- **Never trust a pgvector index or embedding dimension change without re-embedding** and re-running eval.

## 5. Frontend (React/Vite) — Avoid

- **Never hard-code UI strings.** Everything goes through `i18n/bn.json` / `en.json`; Bangla is the default.
- **Never use colour as the only severity signal.** Pair with icon + text label.
- **Never display a confidence value without its basis** (source/verification status).
- **Never store tokens in `localStorage`** if an httpOnly cookie option is available; never put API keys in frontend code.
- **Avoid fetching without a cache key or abort handling.** Use a data-fetching layer; handle slow/failed runs visibly.
- **Avoid animation that ignores `prefers-reduced-motion`.**
- **Avoid one-off hex colours or font sizes.** Use tokens from `styles/tokens.css`.
- **Never let the Results screen render a partial run as final.** Show progress until status is `completed`.

## 6. Data & Licensing — Avoid

- **Never ingest a data source without recording its license and attribution** in `data/SOURCES.md` and on the records.
- **DDInter is non-commercial (CC BY-NC-SA 4.0 per its download terms).** Fine for a prototype with attribution;
  do **not** present it as ready for a paid product. Verify the current terms on the DDInter site yourself.
- **openFDA data must not be presented as validated medical guidance.** Its own disclaimer says not to rely on it
  for medical-care decisions. Keep that caution visible.
- **Never add brand-mapping rows without a `source`.** `verified` stays false until a pharmacist/mentor reviews the row.
- **Avoid scraping sites whose terms prohibit it.** Check terms first; prefer official downloads/APIs.
- **Never overwrite loaded data without `content_hash` dedupe and a recorded fetch date.**
- **Avoid re-running the whole ingest on every deploy.** Make loads idempotent and run on demand.

## 7. Congress Compliance — Avoid

- **Never fabricate demo output or metrics.** Simulated data is labelled simulated (the IoT code tags
  `source: simulated`). Pre-recorded fallback clips must be real runs.
- **Never claim an NRB or mentor contribution that did not happen.** Document only real contributions.
- **Never hide AI-tool usage.** Document Cursor/LLM usage, data sources and the AI-DLC process.
- **Avoid submitting on the last hour.** Submit on the morning of 20 Nov or earlier.
- **Never skip the portal checklist** (links, notes minimum length, MCP documentation, tunnel notes).

## 8. Process — Avoid

- **Never call a fix done without verifying it.** Backend changes get a test; UI changes get a real browser
  check; anything touching findings, verification or guardrails gets an eval run.
- **Never merge to `main` directly.** Feature branch → PR → Lead review → `dev` → tested → `main`.
- **Avoid scope creep after 16 Nov.** After feature freeze only bug fixes land.
- **Avoid silently reversing a deliberate decision** (e.g. removed features, evidence-required rule, cut order).
  Raise it in the daily sync first.
- **Never commit large raw datasets or model files.** Keep scripts and download instructions instead.
- **Avoid scope disguised as a small fix.** A one-line change to guardrails, verification or consent logic gets
  the same scrutiny as a large one.

---

*Read alongside `PRD.md` (why), `architecture.md` (how it's organized), `backend-design.md` (schema, API, AI design),
`design.md` (UX) and `roadmap.md` (plan).*
