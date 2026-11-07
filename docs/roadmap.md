# PredictRx — Development Roadmap

**Scope:** 14 days, 7 Nov → 20 Nov 2026 (Congress submission target: **20 Nov**, aim to submit on 19–20 Nov)
**Team:** 5 members — Lead Dev (AI/ML + domain + architecture), Backend Dev, Frontend Dev, UI/UX Designer, Docs/QA member
**Reads alongside:** `PRD.md`, `architecture.md`, `backend-design.md`, `design.md`, `rule.md`

> **First action (Day 1):** confirm on the Congress portal that 20 Nov is the active deadline for your round.
> The knowledge base listed a preliminary deadline of 31 Oct 2026, which has passed.

This roadmap sequences work so the **core pipeline** (resolve → analyze → verify → cite) is solid *before*
extras are added. Each day lists the deliverable and a "done when" check, so progress is verifiable.

---

## Phase Overview

| Phase | Days | Focus | Key risk managed |
|---|---|---|---|
| **1 — Foundation & Data** | 7–10 Nov | Repo, schema, data pipeline, auth, UI shell, Figma | Data licensing / coverage; scope creep |
| **2 — AI Core** | 11–14 Nov | RAG, agents, MCP, resolver, scan, results UI | Wrong or uncited findings |
| **3 — Safety, Polish, Deploy** | 15–17 Nov | Guardrails, eval, twin, family view, deploy, tunnel | Hallucination, PII leaks, demo failure |
| **4 — Submission** | 18–20 Nov | Video, summary, form, audit, submit | Missing a mandatory deliverable |

**Feature freeze: 16 Nov end of day.** After that, only bug fixes.

---

## Roles

| Member | Owns |
|---|---|
| **Lead Dev** | LangGraph agents, RAG, MCP server, resolver logic, evaluation design, integration, code review |
| **Backend Dev** | Django/DRF apps, schema/migrations, Celery/Redis, auth, audit/consent, admin, deployment + tunnel |
| **Frontend Dev** | React/Vite UI, Bangla i18n, scan/review/results screens, agent-trace UI, API integration |
| **UI/UX Designer** | Figma, design tokens, Bangla typography check, demo visuals, video editing |
| **Docs/QA member** | README, 1-page summary, portal form text, test cases + QA runs, Bangla wording review, KB checklist audit |

Everyone writes commit messages and PR descriptions; Docs/QA also tracks the checklist daily.

---

## Member Task Plan — Who does what, which days

**Legend:** L = Lead Dev · B = Backend Dev · F = Frontend Dev · D = UI/UX Designer · Q = Docs/QA member
Day 1 = Sat 7 Nov … Day 14 = Fri 20 Nov. "Output" is what must exist at end of day so the next person can start.

### At a glance

| Day | Date | L (AI/ML + domain) | B (Backend) | F (Frontend) | D (UI/UX) | Q (Docs/QA) |
|---|---|---|---|---|---|---|
| 1 | 7 Nov | Scope + KPIs lock, repo, rules draft | Docker compose, Django scaffold | Vite scaffold | Wireframes | Deadline check, README skeleton |
| 2 | 8 Nov | Source licenses (`SOURCES.md`) | Models, JWT, audit | i18n + login | Design tokens | Test plan |
| 3 | 9 Nov | Data pipeline (ingest/parse/clean) | Pipeline load + Drug/Interaction APIs | Patients + manual entry | Hi-fi core screens | Brand-mapping sheet |
| 4 | 10 Nov | Resolver + MCP tools + SSE server | Resolve/search endpoints | Autocomplete UI | Hi-fi Review + Results | Brand sheet (continue), review wording |
| 5 | 11 Nov | RAG (chunks, embeddings, graph) | Analysis API + Celery wiring | Review & Confirm screen | Design system finish | Collect eval pairs (independent source) |
| 6 | 12 Nov | LangGraph agents v1 | Run status + trace endpoints | Pipeline stepper | Demo visuals | Test cases for agents |
| 7 | 13 Nov | Verifier + guardrails + PII | Throttling, error shape | Results screen (cards, evidence) | Review results UI | Guardrail test cases |
| 8 | 14 Nov | Scan extraction prompt | Scan API + OCR task + retention | Upload/camera flow | Mobile layouts | Synthetic prescription images |
| 9 | 15 Nov | Eval runner + dev/test split | Patient card, family, consent APIs | Patient card + Family view | Video storyboard | Eval set finalized + Bangla review |
| 10 | 16 Nov | Twin what-if | Admin reskin, consent banner logic | What-if tab, states, mobile | Final Figma | QA pass #1 → **FREEZE** |
| 11 | 17 Nov | Bug fixes, load check | **Deploy + Cloudflare Tunnel** | Bug fixes, polish | Video assets | Full QA vs checklist |
| 12 | 18 Nov | Record demo, KPI numbers | Stability | Demo-path rehearsal | **Record + edit video** | 1-page summary |
| 13 | 19 Nov | Final audit | Final deploy check | Final fixes | Figma link final | **Portal form + KB audit** |
| 14 | 20 Nov | **Submit (morning)** | Keep demo up | Standby | Standby | Verify submission |

---

### Lead Dev (L) — AI/ML, domain, architecture, integration
| Days | Task | Output |
|---|---|---|
| 1 | Lock scope, KPIs, cut order; create repo, branch rules, `.cursor/rules` draft | Repo + rules live |
| 2 | Read openFDA/DDInter terms; write `data/SOURCES.md` | Licenses + attribution recorded |
| 3 | Build ingest → parse → clean → store scripts, n8n export | Drug/Interaction/Document tables loaded |
| 4 | Implement `resolve_brand`, `lookup_drug`, `check_interaction`; MCP server (SSE); test client | Tools callable over MCP |
| 5 | Semantic chunking, contextual prefixes, embeddings, graph edges, retriever | Retrieval returns chunk IDs |
| 6 | LangGraph v1 (Resolver → Notes → Interaction → Advisory) + `AgentTrace` | Findings saved with evidence refs |
| 7 | Verifier agent, output guardrail, PII redaction, LLM router + Ollama path | Uncited finding can't be saved |
| 8 | Prescription extraction prompt + schema validation | Image → draft medication list |
| 9 | Eval runner, dev/test split, metrics | Eval report (n, recall, precision) |
| 10 | Twin what-if; code review sweep | Feature complete |
| 11 | Fix top bugs; load-check non-LLM endpoints | Stable build |
| 12 | Record real demo runs; write KPI numbers from eval | Numbers backed by runs |
| 13 | Final audit with Q: AI-DLC notes, stack notes | Portal notes ready |
| 14 | Submit | Done |
**Reviews all PRs daily.**

### Backend Dev (B) — Django/DRF, infra, deploy
| Days | Task | Output |
|---|---|---|
| 1 | Docker compose (Postgres+pgvector, Redis, Ollama), Django project/settings split, Celery | `runserver` boots |
| 2 | Apps + models: accounts, patients, clinical, drugs, audit; JWT, role permissions, audit logging | Login + patient CRUD + audit rows |
| 3 | Loaders for pipeline output; Drug/Interaction read APIs; drf-spectacular schema | OpenAPI live |
| 4 | `/medications/resolve/`, `/drugs/search/`; caching | Resolve works from the API |
| 5 | `/analysis/` start endpoint, idempotency key, Celery task wiring | Run created once per key |
| 6 | Run status + trace endpoints; `AnalysisRun` snapshot | UI can poll a run |
| 7 | Throttling, consistent error shape, N+1 review | API hardening |
| 8 | Scan upload API, OCR Celery task, private storage, `retain_until` cleanup task | Scan → draft list |
| 9 | Patient-card, consent, family-link, family summary endpoints | Family flow works |
| 10 | Admin reskin (brand-mapping review, eval runs); consent banner data | Review workflow in admin |
| 11 | **Deploy**, env config, **Cloudflare Tunnel**, notes in `deploy/` | Live URL from another network |
| 12–13 | Stability, backups of demo data, final deploy check | Demo safe |
| 14 | Keep demo up | |
*ESP32/vitals app:* code already written; move into `apps/vitals/`, no demo work.

### Frontend Dev (F) — React/Vite, Bangla UI
| Days | Task | Output |
|---|---|---|
| 1 | Vite + TS + routing scaffold | App boots |
| 2 | `tokens.css`, i18n (`bn.json`/`en.json`), login page, API client from schema | Bangla login works |
| 3 | Patients list/create, manual medication entry | Core CRUD UI |
| 4 | Drug autocomplete (brand + generic) | Resolve badges visible |
| 5 | **Review & Confirm** screen (editable list, resolution badges, disabled run until fixed) | Human-in-the-loop UI |
| 6 | Pipeline stepper + polling | Live progress |
| 7 | **Results** screen: finding cards, severity badges, evidence chips, verification badges, disclaimer strip | Doctor view |
| 8 | Upload/camera flow → draft list → confirm | Scan UI |
| 9 | Patient card tab, Family view, consent banner | Dual output + NRB |
| 10 | What-if tab, empty/error/loading states, mobile pass | Feature complete |
| 11 | Bug fixes, polish, a11y check | Stable UI |
| 12 | Rehearse demo path with D | Demo ready |
| 13 | Final fixes | |

### UI/UX Designer (D) — Figma, visuals, video
| Days | Task | Output |
|---|---|---|
| 1 | Wireframes for 6 core screens | Figma wireframes |
| 2 | Tokens from `design.md` (colors, type, spacing), contrast check | Token sheet |
| 3–4 | Hi-fi: Dashboard, Scan, Review, Results | Handoff-ready frames |
| 5 | Design system components (SeverityBadge, EvidenceChip, etc.) | Component library |
| 6 | Demo visuals: logo, architecture graphic, slide backgrounds | Assets |
| 7 | Review built Results UI vs Figma; feedback to F | Fix list |
| 8 | Mobile layouts, Family view, Patient card | Frames |
| 9 | Video storyboard (5 required segments) | Storyboard |
| 10 | Final Figma, public/shareable link | Figma link |
| 11 | Video assets, captions (Bangla + English) | Asset pack |
| 12 | **Record + edit 3-min video**, upload to YouTube | Video link |
| 13 | Support portal form (Figma + YouTube links) | |

### Docs/QA member (Q) — documentation, testing, data sheets, submission
| Days | Task | Output |
|---|---|---|
| 1 | Confirm portal deadline; README skeleton; GitHub project board | Board + README |
| 2 | Test plan; checklist from the Congress KB | Checklist |
| 3–4 | Curated **brand-mapping sheet** (common drugs): every row with a `source`, `verified=false` | Sheet ready to load |
| 5 | Collect eval pairs from an **independent source / reviewer** (mentor/pharmacist) | Draft eval set |
| 6–7 | Agent + guardrail test cases (no-dosing, no-evidence, conflict cases) | Test list |
| 8 | **Synthetic** prescription images (no real patient data) | Image set |
| 9 | Finalize eval set (dev/test split recorded); review Bangla strings with mentor | Eval set + wording notes |
| 10 | QA pass #1; bug list | **Feature freeze** gate |
| 11 | Full QA vs checklist on the deployed URL | Bug list closed |
| 12 | **1-page summary** aligned to judge criteria | Summary draft |
| 13 | **Portal form fill**, character minima, links, NRB/mentor facts (real only), KB audit with L | Form verified by 2 people |
| 14 | Confirm submission received; screenshot proof | Done |

---

### Handoff points (who waits for whom)

| Handoff | From → To | Needed by |
|---|---|---|
| OpenAPI schema | B → F | Day 3 |
| MCP tools + resolver | L → B (resolve API) | Day 4 |
| Figma hi-fi (Review/Results) | D → F | Day 4 |
| Brand-mapping sheet | Q → L (load) | Day 4 |
| Retriever + agents | L → B (analysis API) | Day 6 |
| Eval set | Q → L | Day 9 |
| Feature freeze | all | End of Day 10 (16 Nov) |
| Live URL | B → D, Q | Day 11 |
| Demo video link | D → Q | Day 12 |

### Load note
Lead Dev carries the heaviest AI load; if L falls behind, B takes the MCP server wiring first and F takes the
agent-trace UI so L can focus on RAG, agents and the Verifier. Check each evening and move tasks, not blame.

---

## PHASE 1 — Foundation & Data (7–10 Nov)

### Day 1 — Sat 7 Nov: Scope lock & scaffold
- Confirm deadline on portal; lock KPIs from `PRD.md` §4; lock the feature list (core vs. cuttable).
- Create the monorepo per `architecture.md` §2.2; branches `main` / `dev` / `feature/*`; `.env.example`; `.cursor/rules/` first draft.
- `docker-compose.yml`: Postgres + pgvector, Redis, Ollama.
- **Designer:** Figma file, wireframes for the 6 core screens.
- **Done when:** `docker compose up` + `manage.py runserver` and `npm run dev` both boot; everyone can push to `dev`.

### Day 2 — Sun 8 Nov: Models & auth
- Backend: apps `accounts`, `patients`, `clinical`, `drugs`, `audit`; migrations; JWT auth; role permissions.
- Lead: **data licensing check** — read openFDA and DDInter terms, write `data/SOURCES.md` with source, license, attribution text.
- Frontend: Vite + routing + i18n skeleton + tokens.css; login page.
- **Done when:** a doctor can register/login, create a patient, and every patient read writes an `AuditLog` row.

### Day 3 — Mon 9 Nov: Data pipeline
- Lead + Backend: ingest → parse → clean → store for openFDA labels + DDInter; `Drug`, `Interaction`, `KnowledgeDocument` loaded; n8n workflow exported.
- Docs/QA: start the **sample brand mapping** sheet (curated list of common drugs); record the source of every row and mark `verified=false` until reviewed.
- Frontend: patients list/create, medication manual-entry with autocomplete.
- **Done when:** a coverage report prints drugs per source, interaction counts by severity, license notes stored.

### Day 4 — Tue 10 Nov: Resolver & MCP skeleton
- Lead: `resolve_brand`, `lookup_drug`, `check_interaction` implemented as plain functions + tests.
- Backend: `/api/medications/resolve/`, `/api/drugs/search/`.
- Lead: custom MCP server (SSE) exposing the three tools; client connection from a test script.
- Designer: hi-fi Figma for Review & Results screens.
- **Done when:** typing "Napa" (or any sample brand) returns a generic with confidence, and the MCP tools answer over SSE.

**Phase 1 exit:** data is loaded with licenses recorded, tools work deterministically, UI shell runs in Bangla.

---

## PHASE 2 — AI Core (11–14 Nov)

### Day 5 — Wed 11 Nov: RAG
- Lead: semantic chunking, contextual prefixes, embeddings into pgvector, retriever returning chunk IDs; `GraphEdge` build.
- Backend: `Chunk` indexes, `/api/analysis/` skeleton with idempotency key and Celery wiring.
- Frontend: Review & Confirm screen (static data).
- **Done when:** querying a drug pair returns relevant label passages with IDs, graph expansion adds linked chunks.

### Day 6 — Thu 12 Nov: Agents (v1)
- Lead: LangGraph with Resolver → Clinical Notes → Drug Interaction → Advisory; `AgentTrace` persistence.
- Backend: run status endpoints; trace endpoint.
- Frontend: pipeline stepper + polling.
- **Done when:** a 3-drug list produces findings stored as `RiskFinding` rows with evidence refs.

### Day 7 — Fri 13 Nov: Verifier + guardrails
- Lead: Verifier agent via MCP; `verified/unverified/conflict` states; output guardrail (evidence required, no dosing language, disclaimer).
- Lead: PII redaction module + tests; LLM router with Ollama path.
- Frontend: Results screen — finding cards, evidence chips, verification badges.
- **Done when:** a finding without evidence cannot be saved; a seeded wrong finding is flagged by the Verifier.

### Day 8 — Sat 14 Nov: Prescription scan
- Backend: `/api/prescriptions/scan/`, Celery OCR/vision task, private image storage, `retain_until` cleanup task.
- Lead: extraction prompt + schema validation of model output.
- Frontend: upload/camera → draft list → confirm flow.
- Docs/QA: prepare **synthetic** prescription images (no real patient data) for testing.
- **Done when:** a synthetic prescription image becomes a confirmed medication list end-to-end.

**Phase 2 exit:** scan → confirm → analyze → verified, cited findings, working on a demo patient.

---

## PHASE 3 — Safety, Polish & Deploy (15–17 Nov)

### Day 9 — Sun 15 Nov: Evaluation + outputs
- Lead + Docs/QA: build `EvalCase` set from an **independent source / reviewer** (see `backend-design.md` §8); split dev/test; `/api/eval/run/`.
- Backend: patient-card endpoint; family link/consent endpoints; family summary endpoint.
- Frontend: Patient card tab, Family view.
- **Done when:** eval run prints n, recall, precision on the test split; patient card contains no dosing text.

### Day 10 — Mon 16 Nov: What-if + admin → **FEATURE FREEZE**
- Lead: Twin what-if endpoint (reuses verified data).
- Backend: admin reskin (unfold) for brand-mapping review, eval runs; consent banner logic.
- Frontend: What-if tab; error/empty/loading states; mobile pass.
- Designer: final Figma + demo visuals.
- **Done when:** the full demo path works; **no new features after tonight.**

### Day 11 — Tue 17 Nov: Deploy
- Backend: production-like compose, env config, **Cloudflare Tunnel** live URL documented in `deploy/`.
- Docs/QA: full QA run against the checklist; bug list triaged.
- Lead: load check on the non-LLM endpoints; fix top bugs.
- **Done when:** a live demo URL works from a phone on a different network.

**Phase 3 exit:** deployed, guarded, evaluated, frozen.

---

## PHASE 4 — Submission (18–20 Nov)

### Day 12 — Wed 18 Nov: Video & summary
- Designer + Lead: record the **3-minute YouTube demo** following the 5 required segments:
  1. Problem & users → 2. AI solution → 3. Live demo/flow → 4. AI approach (models/RAG/tools) → 5. Impact, KPIs, next steps.
- Docs/QA: 1-page structured project summary aligned to judge criteria.
- **Done when:** video is uploaded (unlisted/public as required) and the summary is drafted.

### Day 13 — Thu 19 Nov: Audit & form
- Docs/QA + Lead: audit against the Congress KB checklist; fill every portal field; meet character minima (token-optimization note ≥50 chars, AI-DLC note ≥100, other notes ≥80).
- Links ready: YouTube, GitHub, live demo, Figma, plus other supporting links.
- Document AI tools, data sources, and **real** NRB/mentor contributions only.
- **Done when:** every portal field is filled and verified by two people.

### Day 14 — Fri 20 Nov: Submit
- **Submit in the morning.** Keep the rest of the day as buffer for portal problems.
- Freeze the repo with a release tag; keep the live demo up until results.

---

## Cut Order (if time runs short)

Cut from the top first; **never cut the bottom group.**

1. NRB family view → keep as a slide + a minimal read-only page if time allows
2. Digital Twin → reduce to one simple what-if example
3. Admin reskin → use plain Django admin
4. Graph RAG depth → keep a basic edge expansion
5. ESP32 / federated learning / audio → already roadmap-only
---
6. **Never cut:** brand→generic resolver, evidence citations, Verifier agent, PII redaction + disclaimer, measured evaluation, the 3-minute video, the portal form

---

## Congress Portal Checklist (track daily)

| Area | Target |
|---|---|
| Links | YouTube, GitHub, live demo, Figma, + other supporting links |
| Team | Up to 5 members; include NRB/female bonus fields accurately |
| Notes | Token optimization ≥50 chars; AI-DLC ≥100; other notes ≥80 |
| Stack documented | LLM, contextual RAG, semantic chunking, graph RAG, Cursor/AI tool, n8n, Ollama, LangGraph |
| MCP | ≥1 custom MCP (SSE) + ≥1 external MCP; transport and client/host documented |
| Data lifecycle | ingest → parse → clean → store (Postgres + pgvector) → analytics |
| Tunnel | Cloudflare Tunnel documented |
| Deliverables | 1-page summary, 3-min video, working prototype, Bangla localization, measurable outcomes |
| Honesty | AI tools, data sources and contributions documented; no fabricated demos |

---

## Working Agreements
- Daily 10-minute sync (evening). Blockers are raised the same day.
- Branches: `feature/<name>` → PR → Lead review → `dev`; `main` only from tested `dev`.
- Docs/QA keeps `CHANGELOG.md` and the checklist current.
- Every claim in the pitch (accuracy, time saved) must come from a recorded run.

## Risks

| Risk | Mitigation |
|---|---|
| Brand-mapping data is thin | Curated sample list, labelled as sample; show "unresolved" honestly |
| Interaction data license (DDInter non-commercial) | Prototype use with attribution; state the licensed-data path in the pitch |
| LLM output not cited / hallucinated | Evidence-required guardrail + Verifier + "insufficient evidence" fallback |
| Scan accuracy on handwriting | Human confirmation step; synthetic demo images; state limits |
| Live demo failure | Pre-recorded fallback clips; tested tunnel; seeded demo patient |
| Over-scoping | Feature freeze 16 Nov; cut order above |
