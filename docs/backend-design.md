# PredictRx — Backend Technical Design

**Database Schema · API Design · AI / RAG / MCP Design**
Django · DRF · PostgreSQL + pgvector · Celery/Redis · LangGraph · MCP · Ollama
Version 1.0

---

## 1. Overview

This document specifies the data model, REST API and AI design for PredictRx. It covers the full flow:
prescription scan → brand→generic resolution → multi-agent analysis → verified, source-cited findings →
doctor / patient / family views → what-if simulation, with consent, audit and PII handling around it.

Stack: Django 5 + DRF · PostgreSQL 16 + pgvector · Redis · Celery · LangGraph · custom MCP server (SSE) ·
Cloud LLM + Ollama. Scope: data model, API contract, AI pipeline design. Deployment details live in `deploy/`.

---

## 2. Database Schema

Fields are listed in model order. All tables have `id BigAutoField` primary keys unless noted.

### 2.1 Identity & Consent

**User** (custom, extends AbstractUser)
| Field | Type | Notes |
|---|---|---|
| email | EmailField | unique, login |
| role | CharField(12) | doctor / pharmacist / family / admin |
| display_name | CharField(150) | |
| preferred_language | CharField(5) | default 'bn' |

**Patient**
| Field | Type | Notes |
|---|---|---|
| owner | FK(User) | PROTECT — the clinician who created it |
| patient_code | CharField(20) | unique, pseudonymous label shown in the UI (no real name required) |
| birth_year | PositiveSmallIntegerField | nullable |
| sex | CharField(10) | nullable |
| weight_kg | DecimalField(5,1) | nullable |
| created_at | DateTimeField | auto_now_add |

**Consent**
| Field | Type | Notes |
|---|---|---|
| patient | FK(Patient) | CASCADE |
| scope | CharField(20) | analysis / family_view / retain_images |
| granted_by | CharField(100) | who gave consent (patient or guardian) |
| granted_at | DateTimeField | |
| revoked_at | DateTimeField | nullable |

**FamilyLink**
| Field | Type | Notes |
|---|---|---|
| patient | FK(Patient) | CASCADE |
| family_user | FK(User) | role=family |
| relationship | CharField(30) | e.g. child, spouse |
| consent | FK(Consent) | PROTECT — must be a family_view consent |
| is_active | Boolean | default True |

### 2.2 Clinical Input

**PrescriptionScan**
| Field | Type | Notes |
|---|---|---|
| patient | FK(Patient) | CASCADE |
| image | FileField | stored privately, not a public URL |
| status | CharField(15) | queued / processing / extracted / failed |
| extracted_json | JSONField | raw model output (draft) |
| retain_until | DateTimeField | image deletion deadline |
| created_at | DateTimeField | |

**Medication**
| Field | Type | Notes |
|---|---|---|
| patient | FK(Patient) | CASCADE |
| scan | FK(PrescriptionScan) | nullable, SET_NULL |
| raw_text | CharField(200) | exactly what was written / typed |
| brand_name | CharField(120) | nullable |
| strength | CharField(40) | nullable |
| frequency | CharField(60) | nullable (informational only) |
| drug | FK(Drug) | nullable — set after resolution |
| resolution_status | CharField(12) | unresolved / resolved / user_confirmed |
| confirmed_by_user | Boolean | default False — human-in-the-loop flag |
| source | CharField(10) | scan / manual |

**LabResult**
| Field | Type | Notes |
|---|---|---|
| patient | FK(Patient) | CASCADE |
| test_name | CharField(100) | |
| value / unit / ref_range | Decimal / Char / Char | |
| recorded_at | DateTimeField | |

**ClinicalNote**
| Field | Type | Notes |
|---|---|---|
| patient | FK(Patient) | CASCADE |
| text_redacted | TextField | PII-redacted copy used by agents |
| created_at | DateTimeField | |

### 2.3 Drug Knowledge

**Drug**
| Field | Type | Notes |
|---|---|---|
| generic_name | CharField(150) | unique, normalized lower-case |
| aliases | JSONField | synonyms / salt forms |
| external_ids | JSONField | optional identifiers from source datasets |

**BrandMapping** — the local-naming layer
| Field | Type | Notes |
|---|---|---|
| brand_name | CharField(120) | indexed |
| strength | CharField(40) | nullable |
| dosage_form | CharField(30) | nullable |
| drug | FK(Drug) | PROTECT |
| source | CharField(60) | where the mapping came from (must be filled) |
| verified | Boolean | default False — true only after a pharmacist/mentor review |
| confidence | DecimalField(3,2) | |

**Interaction** — drug-pair record from the interaction source
| Field | Type | Notes |
|---|---|---|
| drug_a / drug_b | FK(Drug) | stored with a canonical order (a.id < b.id) |
| severity | CharField(10) | minor / moderate / major / unknown |
| mechanism | TextField | nullable |
| management | TextField | nullable |
| source | CharField(30) | e.g. ddinter |
| source_ref | CharField(200) | record/version reference |
| license_note | CharField(120) | e.g. "CC BY-NC-SA 4.0 — non-commercial" |
| unique | (drug_a, drug_b, source) | |

### 2.4 Knowledge Base (RAG)

**KnowledgeDocument**
| Field | Type | Notes |
|---|---|---|
| source | CharField(30) | openfda_label / ddinter |
| drug | FK(Drug) | nullable |
| title | CharField(250) | |
| source_url | URLField | nullable |
| license_note | CharField(120) | |
| fetched_at | DateTimeField | |
| content_hash | CharField(64) | dedupe on re-ingest |

**Chunk**
| Field | Type | Notes |
|---|---|---|
| document | FK(KnowledgeDocument) | CASCADE |
| section | CharField(80) | e.g. warnings, drug interactions |
| text | TextField | semantic chunk |
| context_prefix | TextField | short generated context placed before embedding (contextual RAG) |
| embedding | VectorField | pgvector, dimension set by the embedding model |
| token_count | IntegerField | |

**GraphEdge**
| Field | Type | Notes |
|---|---|---|
| src_type / src_id | Char / BigInt | e.g. drug, chunk |
| relation | CharField(40) | mentions / interacts_with / contraindicated_with |
| dst_type / dst_id | Char / BigInt | |
| chunk | FK(Chunk) | nullable — evidence for the edge |

### 2.5 Analysis

**AnalysisRun**
| Field | Type | Notes |
|---|---|---|
| patient | FK(Patient) | PROTECT |
| requested_by | FK(User) | SET_NULL |
| idempotency_key | CharField(64) | unique — a double-click creates one run |
| status | CharField(12) | queued / running / completed / failed |
| input_snapshot | JSONField | exact medication list, labs, notes (redacted) at run time |
| model_info | JSONField | model names / versions used |
| started_at / finished_at | DateTimeField | |

**AgentTrace**
| Field | Type | Notes |
|---|---|---|
| run | FK(AnalysisRun) | CASCADE |
| agent_name | CharField(30) | resolver / clinical_notes / drug_interaction / advisory / verifier |
| step_order | PositiveSmallIntegerField | |
| input_summary / output_summary | TextField | redacted summaries |
| tool_calls | JSONField | MCP tool names + args + result refs |
| latency_ms | IntegerField | |

**RiskFinding**
| Field | Type | Notes |
|---|---|---|
| run | FK(AnalysisRun) | CASCADE |
| drug_a / drug_b | FK(Drug) | |
| severity | CharField(10) | minor / moderate / major / unknown |
| rationale | TextField | |
| confidence | DecimalField(3,2) | |
| verification_status | CharField(12) | verified / unverified / conflict |
| evidence | JSONField | [{type: interaction|chunk, id, source}] — **must be non-empty for any severity other than unknown** |

**RiskSummary**
| Field | Type | Notes |
|---|---|---|
| run | OneToOne(AnalysisRun) | |
| doctor_summary_bn / _en | TextField | |
| patient_card_bn | TextField | plain language, no dosing |
| disclaimer_version | CharField(10) | |

**TwinScenario**
| Field | Type | Notes |
|---|---|---|
| patient | FK(Patient) | |
| base_run | FK(AnalysisRun) | |
| hypothetical_drug | FK(Drug) | |
| result_json | JSONField | new/changed findings vs. base run |
| created_at | DateTimeField | |

### 2.6 Evaluation, Audit, IoT

**EvalCase** — `drug_a`, `drug_b`, `expected_severity`, `rationale_ref` (independent source note), `reviewed_by`, `split` (dev/test).
**EvalRun** — `created_at`, `n_cases`, `metrics` (JSON: recall, precision, per-severity), `config` (JSON).
**AuditLog** — `actor` FK(User, SET_NULL), `action`, `object_type`, `object_id`, `patient` FK nullable, `ip`, `meta` JSON, `at` (indexed).
**Device / VitalReading** — as implemented in `backend/apps/vitals/` (roadmap; token-hashed device auth, rule-based triage).

### 2.7 Key Relationships

```
User 1—N Patient · Patient 1—N Consent · Patient 1—N FamilyLink —N:1— User(family)
Patient 1—N PrescriptionScan 1—N Medication —N:1— Drug
Drug 1—N BrandMapping · Drug —N:N— Drug via Interaction
KnowledgeDocument 1—N Chunk · Chunk —(evidence)— GraphEdge
Patient 1—N AnalysisRun 1—N AgentTrace · AnalysisRun 1—N RiskFinding · AnalysisRun 1—1 RiskSummary
AnalysisRun 1—N TwinScenario
```

---

## 3. API Design

REST/JSON under `/api/`. JWT bearer auth. All patient-scoped endpoints check ownership or an active
`FamilyLink` + `Consent`, and write an `AuditLog` entry.

### Authentication
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | /api/auth/register/ | No | Create doctor/pharmacist account (family accounts via invite) |
| POST | /api/auth/login/ | No | JWT pair |
| POST | /api/auth/token/refresh/ | No | New access token |
| POST | /api/auth/logout/ | Yes | Blacklist refresh |
| GET/PATCH | /api/auth/me/ | Yes | Profile |

### Patients & Consent
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET/POST | /api/patients/ | Yes | List / create |
| GET/PATCH | /api/patients/{id}/ | Owner | Detail / update |
| POST | /api/patients/{id}/consents/ | Owner | Record a consent scope |
| POST | /api/patients/{id}/consents/{cid}/revoke/ | Owner | Revoke |
| POST | /api/patients/{id}/family/ | Owner | Link a family user (needs family_view consent) |

### Prescription & Medications
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | /api/prescriptions/scan/ | Yes | Upload image → `{scan_id}` (async) |
| GET | /api/prescriptions/scan/{id}/ | Owner | Status + extracted draft list |
| GET/POST | /api/patients/{id}/medications/ | Owner | List / add manually |
| PATCH/DELETE | /api/medications/{id}/ | Owner | Edit / remove (user confirms extracted drafts here) |
| POST | /api/medications/resolve/ | Yes | Resolve brand names → generics (synchronous, uses BrandMapping) |
| GET | /api/drugs/search/?q= | Yes | Autocomplete over brand + generic names |

### Analysis
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | /api/analysis/ | Owner | Start run `{patient_id, medication_ids, idempotency_key}` → `{run_id}` |
| GET | /api/analysis/{id}/ | Owner | Status, findings, summaries |
| GET | /api/analysis/{id}/trace/ | Owner | Agent trace for the UI |
| GET | /api/analysis/{id}/patient-card/ | Owner | Plain Bangla patient card |
| POST | /api/twin/ | Owner | What-if `{base_run_id, drug_id}` |

### Family (NRB)
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | /api/family/patients/ | Family | Patients linked with active consent |
| GET | /api/family/patients/{id}/summary/ | Family | Read-only latest summary |

### Admin / Evaluation
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | /api/eval/run/ | Admin | Run evaluation on the test split |
| GET | /api/eval/runs/ | Admin | Metrics history |

### IoT (roadmap)
`POST /api/vitals/ingest/`, `GET /api/vitals/patient/{id}/` — already implemented.

### Response conventions
- Errors: `{ "error": { "code": "...", "message": "..." } }`.
- Any finding with severity other than `unknown` carries a non-empty `evidence` list; the serializer enforces it.
- Every analysis response includes `disclaimer_version`.

---

## 4. Design Decisions

- **Human-in-the-loop on OCR.** Extracted drug lists are drafts. The user must confirm before analysis,
  because a wrong OCR read propagates into a wrong safety result.
- **Resolver never guesses.** Exact match → fuzzy match with a confidence threshold → else `unresolved`.
- **Findings must be evidenced.** `RiskFinding.evidence` is mandatory for any non-`unknown` severity.
  "Insufficient evidence" is a valid output.
- **Deterministic verification.** The Verifier uses MCP tools backed by the `Interaction` table, independent
  of the LLM's wording, so it can catch hallucinated or mis-stated pairs.
- **Snapshots.** `AnalysisRun.input_snapshot` freezes the inputs, so an old run stays explainable after
  medication lists change.
- **PROTECT / CASCADE / SET_NULL.** `Medication.drug`, `BrandMapping.drug`, `AnalysisRun.patient` are PROTECT;
  `AuditLog.actor` is SET_NULL so logs survive user deletion.
- **Pseudonymous patients.** `patient_code` is shown instead of names to limit PII exposure.
- **One database.** pgvector inside PostgreSQL avoids running a separate vector service for the demo.

---

## 5. Data Pipeline (ingest → parse → clean → store → analytics)

| Stage | What happens | Where |
|---|---|---|
| Ingest | Fetch openFDA drug labels via the API; load DDInter downloadable files; load the curated brand sample | n8n workflow + `data/pipeline/` |
| Parse | Split labels into sections (warnings, interactions…); parse interaction CSVs | `data/pipeline/parse_*.py` |
| Clean | Normalize drug names (case, salts), dedupe by `content_hash`, drop malformed rows, record license note | `data/pipeline/clean.py` |
| Store | Upsert `Drug`, `Interaction`, `KnowledgeDocument`, `Chunk` (+ embeddings), `GraphEdge` | `data/pipeline/load.py` |
| Analytics | Coverage report: drugs per source, interaction counts by severity, unresolved-brand rate, eval metrics | `data/pipeline/report.py`, shown in admin |

Raw and processed files are kept under `data/` (large files git-ignored; scripts are committed). Each source's
license note is stored with the records it produced.

---

## 6. AI Design

### 6.1 LangGraph pipeline

State object carries: `patient_context` (redacted), `medications`, `resolved_drugs`, `retrieved_chunks`,
`findings`, `verification`, `summaries`, `trace`. Nodes run in order:

1. **Resolver** — maps each medication to a `Drug` through the `resolve_brand` tool; unresolved items are
   carried forward as explicit gaps.
2. **Clinical Notes** — extracts relevant context (age band, renal/hepatic lab flags entered by the clinician,
   notes) from the **redacted** inputs.
3. **Drug Interaction** — for each pair: calls `check_interaction` (MCP) and retrieves supporting label
   passages from RAG; proposes findings with evidence references.
4. **Advisory** — writes the doctor summary and the patient card from the findings only (no new facts).
5. **Verifier** — re-checks each finding through the MCP tool and labels it `verified / unverified / conflict`;
   the output guardrail then enforces: evidence present, no dosing language, disclaimer attached.

Each node writes an `AgentTrace` row (inputs/outputs summarized, tool calls, latency).

### 6.2 RAG

- **Semantic chunking:** split by label section boundaries first, then by meaning/length within long sections.
- **Contextual chunks:** each chunk gets a short generated context prefix (drug name, section, what it covers)
  that is embedded with the text, so retrieved passages are self-explanatory.
- **Graph RAG:** `GraphEdge` links drugs, interaction mentions and the chunks that evidence them;
  retrieval expands from the queried drug pair to connected chunks.
- **Citations:** retrieval returns chunk IDs; those IDs become `evidence` entries on findings.
- Embedding model and dimension are configuration; changing them requires re-embedding.

### 6.3 MCP

**Custom server (SSE transport):**
| Tool | Input | Output |
|---|---|---|
| `resolve_brand` | brand string, optional strength | generic, confidence, verified flag, or unresolved |
| `lookup_drug` | generic name | basic record + source list |
| `check_interaction` | two generic names | severity, mechanism, management, source ref — or `no_record` |

Documented in `mcp-server/README.md`: transport (SSE, with notes on Stdio), which component is the MCP
**host** (the LangGraph worker) and which is the **client**. **External MCP:** one public server integrated and documented.

### 6.4 LLM routing & guardrails
- **PII redaction** runs before any text is sent to a cloud model (names, phone numbers, addresses, IDs in
  free-text notes). Prescription *images* go to the vision model only after the user's `analysis` consent.
- **Ollama (local)** handles steps working on sensitive free text where feasible.
- **Output guardrails:** no dosing/stop/start instructions; every finding cited; disclaimer present;
  anything that fails the check is replaced with "insufficient evidence — consult a clinician".

---

## 7. Scalability, Concurrency & Performance

These are **design targets, not measured results.** They are validated with a load test (Locust/k6) before any
number is quoted in the pitch.

| Metric | Target |
|---|---|
| Drug search / brand resolve (no LLM) | p95 < 300 ms |
| Start analysis (enqueue) | p95 < 500 ms |
| Full analysis (async) | Completes within ~30 s for a typical 5–8 drug list; progress visible |
| Error rate | < 1% excluding upstream LLM outages (retried) |

- **Idempotency:** `AnalysisRun.idempotency_key` unique; a retry returns the same run.
- **Async:** OCR and analysis run in Celery; API never blocks on an LLM call.
- **Indexes:** `BrandMapping.brand_name`, `Interaction(drug_a, drug_b)`, `Chunk` vector index (HNSW/IVFFlat),
  `AuditLog(patient, at)`, `AnalysisRun(patient, started_at)`.
- **N+1 control:** `select_related`/`prefetch_related` on findings and trace endpoints.
- **Caching:** Redis cache for `lookup_drug` / `check_interaction` results (invalidate on data reload).
- **Rate limiting:** DRF throttles on login, scan upload, analysis start.
- **Statelessness:** API instances hold no state; scale horizontally behind a load balancer.

---

## 8. Evaluation (KPI measurement)

- `EvalCase` rows form a labelled set of drug pairs with expected severity.
- **The test set must be independent of the data the system retrieves from.** The Verifier and RAG use DDInter
  and openFDA, so grading against DDInter alone would be circular and inflate results. Cases should come
  from a source or reviewer outside that pipeline (e.g. a pharmacist/mentor-reviewed list), recorded in `rationale_ref`.
- Split into `dev` (tune prompts/thresholds) and `test` (reported once). Report counts: **n cases, recall,
  precision, per-severity breakdown**, and state the limitations of a small set.
- Also measure: brand-resolution accuracy (held-out brands), % findings cited (must be 100%),
  and rate of correct "unknown" for pairs with no evidence.

---

## 9. Privacy, Audit & Retention
- `AuditLog` entry for: patient read, analysis start, family view, consent change, image access.
- Prescription images: private storage, deleted at `retain_until` (default short unless `retain_images` consent).
- Secrets in environment variables only; `.env` git-ignored.
- Demo data: synthetic or explicitly consented cases only.
