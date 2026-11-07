# PredictRx — System Architecture

**Version:** 1.0
**Companion documents:** `PRD.md`, `backend-design.md` (schema, API, AI design), `design.md`, `roadmap.md`, `rule.md`

---

## 1. System Architecture

### 1.1 High-Level Overview

PredictRx is a decoupled system: a React (Vite) frontend talks to a Django REST API. The backend owns all
business logic and state. AI work runs in a separate `ai/` package (LangGraph agents, RAG, guardrails) that is
invoked by Celery workers, and tools are exposed to agents through MCP. The frontend never talks to the
database or the LLM directly.

```text
                 ┌──────────────────────────────────────────────┐
                 │   CLIENT  ·  Doctor / Caregiver / NRB family │
                 │        Browser (Bangla-first React UI)       │
                 └──────────────────────────────────────────────┘
                                      │ HTTPS
                                      ▼
                 ┌──────────────────────────────────────────────┐
                 │  EDGE  ·  Cloudflare Tunnel (demo exposure)  │
                 └──────────────────────────────────────────────┘
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
   ┌─────────────────────────┐                  ┌──────────────────────────────┐
   │  FRONTEND (React/Vite)  │ ───REST/JSON───▶ │   BACKEND API (Django + DRF) │
   │  doctor · patient ·     │ ◀─────────────── │   auth · patients · analysis │
   │  family · admin views   │                  │   audit · consent · admin    │
   └─────────────────────────┘                  └──────────────────────────────┘
                                                      │            │
                                          enqueue job │            │ reads/writes
                                                      ▼            ▼
                              ┌───────────────────────────┐   ┌────────────────────────┐
                              │  Celery workers  (Redis)  │   │ PostgreSQL + pgvector  │
                              │  OCR · analysis · eval    │   │ system of record +     │
                              └───────────────────────────┘   │ embeddings + graph     │
                                          │                   └────────────────────────┘
                                          ▼
         ┌─────────────────────────────────────────────────────────────────────┐
         │                        AI LAYER  (backend/ai/)                      │
         │                                                                     │
         │  Guardrails (PII redaction in/out)                                  │
         │        │                                                            │
         │  LangGraph pipeline:                                                │
         │   Resolver ─▶ Clinical Notes ─▶ Drug Interaction ─▶ Advisory ─▶ Verifier │
         │                                   │   ▲                              │
         │                           RAG ◀───┘   └──▶ MCP tools                │
         │   (contextual + semantic chunking + graph)   │                       │
         │                                              ▼                       │
         │   LLM router:  Cloud LLM (vision + reasoning)  |  Ollama (local)     │
         └─────────────────────────────────────────────────────────────────────┘
                                          │
                       ┌──────────────────┴───────────────────┐
                       ▼                                      ▼
        ┌─────────────────────────────┐        ┌──────────────────────────────┐
        │ Custom MCP server (SSE)     │        │ External public MCP client   │
        │ check_interaction,          │        │ (1 server, chosen in build)  │
        │ resolve_brand, lookup_drug  │        └──────────────────────────────┘
        └─────────────────────────────┘

        Data pipeline (n8n + scripts):  ingest → parse → clean → store → analytics
        Sources: openFDA drug labels · DDInter interactions · curated brand sample
```

### 1.2 Component Breakdown

| Component | Role | Notes |
|---|---|---|
| **React + Vite frontend** | Bangla-first UI: upload, review/confirm extracted drugs, results (doctor / patient / family views), agent trace, admin links. | Talks only to the REST API. i18n files `bn.json` / `en.json`. |
| **Django + DRF backend** | Single source of truth: patients, consent, medications, analysis runs, findings, audit. Every business rule lives here. | Stateless. JWT auth. |
| **PostgreSQL + pgvector** | System of record, embeddings for RAG chunks, graph edge tables. | One database keeps the demo deployable by a small team. |
| **Redis** | Celery broker/result store, cache for drug lookups. | |
| **Celery workers** | Slow work off the request path: prescription OCR/vision, analysis pipeline, evaluation runs. | The API returns a run ID immediately; UI polls or streams status. |
| **LangGraph pipeline** | Orchestrates the five agent steps with shared state and a persisted trace. | See backend-design §6. |
| **RAG layer** | Semantic chunking of openFDA labels, contextual prefixes per chunk, vector search plus a graph of drug↔interaction↔section edges. | Retrieval returns chunk IDs used as citations. |
| **LLM router** | Cloud LLM for vision and reasoning; Ollama local model for steps that handle sensitive text. | Provider is configurable; no keys in code. |
| **Custom MCP server (SSE)** | Exposes deterministic tools to agents: `check_interaction`, `resolve_brand`, `lookup_drug`. | The Verifier uses the same tools, independent of the LLM's prose. |
| **External MCP client** | Uses one public MCP server for an extra capability, documented in `mcp-server/README.md`. | Choice finalized during build. |
| **Guardrails** | PII redaction before cloud calls; output checks (no dosing, disclaimer present, every finding cited). | |
| **n8n** | Orchestrates the data-ingest workflow (fetch → parse → clean → store). Exports in `automation/n8n/`. | |
| **Cloudflare Tunnel** | Exposes the local/staging app for the live demo; documented in `deploy/`. | |
| **Django admin (reskinned)** | Review brand mappings, view eval runs, manage users. | Admin skin: django-unfold (optional). |

### 1.3 Key Request Flows

**Prescription analysis (async)**
```
Browser → POST /api/prescriptions/scan/ (image)
        → Django stores image (retention-limited), enqueues OCR task, returns scan_id
Worker  → vision model extracts drug list → saved as draft Medication rows
Browser → GET scan → user edits/confirms the list (human-in-the-loop)
Browser → POST /api/analysis/ {patient_id, medication_ids, idempotency_key}
Django  → creates AnalysisRun(status=queued), enqueues pipeline, returns run_id
Worker  → LangGraph: Resolver → Clinical Notes → Drug Interaction → Advisory → Verifier
        → every step writes an AgentTrace row; findings written as RiskFinding rows
Browser → polls GET /api/analysis/{id}/ → renders doctor / patient / family views
```

**Brand → generic resolution**
```
"Napa 500" → resolve_brand (MCP tool) → BrandMapping lookup (exact → fuzzy)
          → { generic: "paracetamol", confidence, verified }  | or  { unresolved }
Unresolved names are returned to the UI for manual selection; never guessed.
```

**Verification**
```
Advisory agent proposes findings → Verifier calls check_interaction for each pair
 ├─ matches table  → verification_status = verified
 ├─ not in table   → unverified (shown with lower confidence + reason)
 └─ contradicts    → conflict (shown to doctor, flagged)
```

**Family (NRB) view**
```
Patient record has Consent(scope=family_view) + FamilyLink
Family user → GET /api/family/patients/{id}/summary/ → read-only plain-language summary
Every access is written to AuditLog.
```

---

## 2. Project Structure (monorepo)

### 2.1 Repository Strategy

**One repository** (`predictrx`) containing frontend, backend, MCP server, data pipeline, firmware and docs.
Rationale: the Congress portal accepts few GitHub links, five people need one place to coordinate, and
the API contract, types and docs stay in sync. Work happens on feature branches merged into `dev`, then `main`.

### 2.2 Layout

```
predictrx/
├── .cursor/rules/                       # AI-DLC: Cursor Rules for the team
├── docs/                                # PRD, architecture, design, backend-design, roadmap, rule
├── backend/                             # Django + DRF
│   ├── config/
│   │   ├── settings/{base,local,production}.py
│   │   ├── urls.py · celery.py · asgi.py · wsgi.py
│   ├── apps/
│   │   ├── accounts/                    # User (role), JWT auth
│   │   ├── patients/                    # Patient, Consent, FamilyLink
│   │   ├── clinical/                    # PrescriptionScan, Medication, LabResult, ClinicalNote
│   │   ├── drugs/                       # Drug, BrandMapping, Interaction
│   │   ├── knowledge/                   # KnowledgeDocument, Chunk (pgvector), GraphEdge
│   │   ├── analysis/                    # AnalysisRun, AgentTrace, RiskFinding, RiskSummary
│   │   ├── twin/                        # TwinScenario (what-if simulation)
│   │   ├── evaluation/                  # EvalCase, EvalRun
│   │   ├── vitals/                      # ESP32 ingest (roadmap, code ready)
│   │   └── audit/                       # AuditLog
│   ├── ai/
│   │   ├── agents/                      # resolver, clinical_notes, drug_interaction, advisory, verifier
│   │   ├── graph.py                     # LangGraph pipeline definition
│   │   ├── rag/                         # chunking, contextual, graph, retriever
│   │   ├── llm/                         # router: cloud + ollama
│   │   └── guardrails/                  # pii.py, output_checks.py
│   ├── core/                            # permissions, pagination, exceptions, cache
│   ├── tests/
│   ├── requirements/{base,local,production}.txt
│   ├── docker-compose.yml               # Postgres+pgvector, Redis, Ollama
│   └── Dockerfile
├── mcp-server/                          # custom MCP server (SSE + stdio notes)
│   ├── server.py
│   └── README.md                        # transport, client/host, tools
├── frontend/                            # React + Vite
│   ├── src/
│   │   ├── pages/                       # Login, Dashboard, Patients, Scan, Review, Analysis, Twin, Family
│   │   ├── components/{ui,patient,analysis,twin,layout}/
│   │   ├── i18n/{bn.json,en.json}
│   │   ├── lib/{api.ts,types.ts}
│   │   ├── hooks/
│   │   └── styles/tokens.css
│   └── package.json
├── data/
│   ├── raw/ · processed/
│   └── pipeline/                        # ingest → parse → clean → store → analytics scripts
├── automation/n8n/                      # workflow exports
├── firmware/predictrx_vitals/           # ESP32 sketch (roadmap)
├── deploy/                              # Cloudflare Tunnel notes, prod compose
├── submission/                          # 1-page summary, video script, form text, KB checklist
├── .env.example · CHANGELOG.md · README.md
```

Each Django app is self-contained (`models`, `serializers`, `views`, `services`, `urls`, `admin`, `tests`).
`services.py` holds business logic; views stay thin HTTP adapters.

---

## 3. Technology Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | **React + Vite**, TypeScript | Team's existing stack; fast iteration. |
| Backend | **Django + DRF** | Team's existing stack; admin for review workflows. |
| Auth | **simplejwt** | JWT access/refresh. |
| API docs | **drf-spectacular** | Living OpenAPI contract; frontend types generated from it. |
| Database | **PostgreSQL + pgvector** | One store for relational data and embeddings. |
| Queue / cache | **Celery + Redis** | Async OCR and analysis. |
| Agents | **LangGraph** | Explicit multi-agent graph with state and traceability. |
| LLM | **Cloud LLM** (vision + reasoning) + **Ollama** local model | Cloud for capability, local for sensitive text. |
| RAG | **Semantic chunking + contextual chunk prefixes + graph RAG** | Better retrieval on long drug labels; citations from chunk IDs. |
| MCP | **Custom server (SSE)** + **1 external public MCP** | Deterministic tools shared by agents and verifier. |
| Automation | **n8n** | Data-ingest workflow, exportable for judges. |
| Dev workflow | **Cursor + Cursor Rules** (AI-DLC) | Documented AI-assisted development process. |
| Exposure | **Cloudflare Tunnel** | Live demo URL without paid hosting. |
| Admin skin | **django-unfold** (optional) | Cleaner review screens. |
| Error tracking | **Sentry** (optional) | If time allows. |
| Testing | **pytest**, **factory_boy** | Backend and eval tests. |
| IoT (roadmap) | **ESP32 + MAX30102** | Code written, outside demo flow. |

Exact local-model choice and the external MCP server are decided during build and recorded in the README.

---

*Read alongside `PRD.md` for scope and `backend-design.md` for schema, API contract, and the AI/RAG/MCP design.*
