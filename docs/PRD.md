# PredictRx — Product Requirements Document

**Version:** 1.0
**Market:** Bangladesh (NRB family use-case included)
**Domain track:** HealthTech — International AI Builders Congress 2026
**Status:** Design complete — build starts 7 Nov 2026, submission target 20 Nov 2026

---

## 1. Product Vision

### 1.1 Statement

PredictRx is a **Bangla-first, evidence-cited medication-safety assistant**. A doctor (or a caregiver) gives
it a prescription — as a photo or typed list — and a multi-agent AI pipeline resolves brand names to
generics, checks drug–drug interactions against public sources, verifies its own answer, and returns a
risk summary where **every warning shows its source and confidence**. When the system is not sure, it says so.

PredictRx is **decision support for a clinician. It is not a diagnosis tool and does not replace a doctor.**

### 1.2 Positioning

| | Generic English drug-checkers | **PredictRx** | Hospital EHR / commercial CDS suites |
|---|---|---|---|
| Language | English only | **Bangla-first, English toggle** | Mostly English |
| Drug naming | Generic names | **Brand names used locally → generic resolver** | Generic / formulary codes |
| Input | Type drug names | **Prescription photo or typed list** | Structured EHR entry |
| Transparency | Often a bare "severity" label | **Every warning cites its source + confidence; shows "unknown"** | Varies |
| Access | Free but not localized | **Prototype, open-data based** | Licensed, expensive |

### 1.3 Why now

Polypharmacy raises interaction risk, and published interaction resources are built around English and
generic names. In Bangladesh, patients typically take medicines known by **brand names** and often carry
**handwritten or printed prescriptions**. That gap — between how drugs are named and written locally and how
safety databases are keyed — is where PredictRx works. Recent multimodal LLMs, RAG, agent frameworks, and MCP
make a small team able to build this as an AI-native system rather than a rules table.

### 1.4 Success looks like

- A doctor uploads a prescription and gets a **verified, source-cited** interaction summary in Bangla
  without reading raw database output.
- No warning is shown without a source. No source → the system says "insufficient evidence".
- A caregiver abroad (NRB) can see a plain-language alert about a parent's medication list, with the
  patient's consent.
- Claimed accuracy numbers are **measured on an independent test set**, not asserted.

---

## 2. Target Users

### 2.1 Primary — "The Time-Pressed Doctor"
- General practitioners / physicians seeing many patients, reviewing medication lists quickly.
- **Needs:** fast, trustworthy, Bangla-readable summary; sources visible so they can verify; no false confidence.
- **Turn-offs:** black-box scores, unexplained alerts, alert fatigue.

### 2.2 Secondary — "The Caregiver / Patient"
- Family members managing an elderly parent's medicines, or patients wanting a plain-language explanation.
- **Needs:** simple Bangla explanation, clear "talk to your doctor" guidance. Never a dosing instruction.

### 2.3 Tertiary — "The NRB Family Guardian"
- Non-Resident Bangladeshi whose parents live in Bangladesh and take several medicines.
- **Needs:** a read-only family view with consent, alerts for potentially risky combinations.

### 2.4 Explicitly *not* the audience
- Anyone wanting autonomous treatment decisions. PredictRx never prescribes, doses, or diagnoses.

---

## 3. Key Capabilities

### 3.1 Input
- **Prescription photo scan** — vision model extracts drug names, strengths, frequency into an editable list;
  the user always confirms the extracted list before analysis.
- Manual entry / search with autocomplete (brand and generic names).
- Optional structured inputs: age, sex, weight, key lab values (entered by the clinician).

### 3.2 Brand → Generic Resolver
- Maps locally used brand names to generic names so safety data (keyed by generic) can be queried.
- Backed by a **curated sample mapping** table; each row carries `verified` and `confidence`. Unresolved
  names are surfaced to the user, never silently guessed.

### 3.3 Multi-Agent Analysis (LangGraph)
- **Clinical Notes agent** — reads notes/labs/vitals, extracts relevant context (after PII redaction).
- **Drug Interaction agent** — queries the custom MCP tool and the RAG knowledge base (openFDA labels, DDInter).
- **Advisory agent** — drafts the risk summary for the doctor and a plain-language Bangla card for the patient.
- **Verifier agent** — independently cross-checks every finding against the interaction table; flags
  `verified / unverified / conflict`. Conflicts are shown, not hidden.
- The agent trace (which agent did what, which tools it called) is visible in the UI.

### 3.4 Output
- **Doctor view:** findings sorted by severity, each with mechanism, management note, source citation,
  confidence, verification status.
- **Patient card:** short plain Bangla summary + "discuss with your doctor". No dosing, no stop/start instructions.
- **Family view (NRB):** read-only, consent-gated page.

### 3.5 Digital Twin (small, scoped)
- A what-if view: "if drug X is added, how does the interaction risk picture change?" — computed from the
  same verified interaction data plus entered vitals/labs. It is a **simulation for exploration**, labelled as such.

### 3.6 Admin & Audit
- Admin dashboard (Django admin reskinned) for drug/brand-mapping review, evaluation runs, user management.
- **Audit log** of every access to patient data and every analysis run.

### 3.7 Platform (non-functional)
- Bangla localization throughout (UI, summaries, disclaimers).
- Async processing for slow work (OCR, analysis) with a progress UI.
- PII redaction before any text reaches a cloud LLM; local model (Ollama) for sensitive steps.
- Observability: structured logs, per-agent latency, error tracking.

### 3.8 Roadmap (shown in the pitch, **not** in the demo)
- **IoT vitals (ESP32 SpO2/pulse):** firmware and ingest endpoint are already written; not part of the demo flow.
- **Federated learning:** train across hospitals without centralizing patient data.
- **Audio / cough biomarkers:** respiratory risk signals from voice/cough audio.

### 3.9 Explicitly out of scope (this phase)
- Diagnosis, treatment recommendations, dosing instructions, or anything presented as medical advice.
- Real patient data in the demo (synthetic / consented sample cases only).
- Pharmacy ordering, payments, e-prescribing.

---

## 4. KPIs (targets — measured before claiming)

| KPI | Target | How measured |
|---|---|---|
| Warnings with a cited source | 100% | Automated check on every `RiskFinding` |
| Interaction detection recall on independent test set | Report the measured number honestly | `EvalRun` on a pharmacist-reviewed set (see backend-design §8) |
| Precision on the same set | Report measured number | Same |
| Brand-resolution accuracy on sample mapping | Report measured number | Held-out brand list |
| Review time vs. manual lookup | Report measured number | Timed comparison, small n, stated as such |
| "Insufficient evidence" correctly used | Tracked | Cases with no source must not produce a severity |

Numbers are **not** pre-filled. They are filled from real runs and stated with the test-set size.

---

## 5. Ethics, Safety & Compliance

- **Decision support only.** Every screen carries a disclaimer; the patient card never gives dosing.
- **openFDA's own disclaimer** states its data must not be relied on for medical-care decisions; PredictRx
  surfaces data with that caution and keeps the clinician as decision maker.
- **Consent:** a patient record has an explicit consent scope; family view requires it.
- **Privacy:** PII redaction before cloud LLM calls; minimal retention of prescription images; audit trail.
- **Honesty:** simulated data is labelled simulated. No fabricated demos.
- **Licensing:** DDInter data is non-commercial (CC BY-NC-SA); fine for a prototype with attribution, **not**
  for a paid product without permission or a licensed source. Stated openly in the pitch (see rule.md §6).
- **Bias/coverage:** public data is US/China-centric; local brands/formulations may be missing. Gaps are
  shown as "not found", not guessed.

---

## 6. Congress Alignment

| Judging area (pts) | How PredictRx addresses it |
|---|---|
| Innovation (20) | Bangla prescription scan + brand→generic resolver + verifier agent + evidence-cited output |
| Technical (20) | LangGraph multi-agent, contextual + semantic-chunked + graph RAG, pgvector, custom MCP (SSE), Ollama local model |
| Business / Global (20) | Clinic / hospital SaaS, NRB family subscription; licensed-data upgrade path; expansion to other South Asian markets |
| Impact / Ethics (20) | Medication-error reduction goal, consent, audit, PII redaction, "unknown" over false confidence |
| Scalability / NRB (10) | Stateless API, async workers, modular cloud deploy; NRB family guardian; mentor/NRB collaboration [TBD — fill from real contributions] |
| Presentation (10) | 3-minute demo video following the five required segments |

**Team:** 5 members, including a female member. NRB / mentor involvement: [TBD — document real contributions only].

---

*Read alongside `architecture.md` (how it's built), `backend-design.md` (schema, API, AI design),
`design.md` (UX), `roadmap.md` (7–20 Nov plan), and `rule.md` (what to avoid and why).*
