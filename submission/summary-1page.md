# PredictRx — 1-page summary

**Track:** HealthTech · International AI Builders Congress 2026 · **Team:** Neural Devx (5) · **Market:** Bangladesh, NRB family use-case
**Repo:** github.com/Sadman-Devx/predictrx · **Live demo:** https://predictrx-assi.malaysiawest.cloudapp.azure.com · **Video:** [TBD] · **Figma:** https://www.figma.com/design/5fV8aTEasT6l4AY8xWPIqj/PredictRx-%E2%80%93-Smart-Healthcare-Management-System

## Problem
Patients in Bangladesh take medicines by **brand name** and carry paper prescriptions, while interaction databases are in English and keyed by generic name. Doctors have little time; families abroad (NRBs) cannot see risk in a parent's medicine list. Alerts without sources are hard to trust.

## Solution
A **Bangla/English, evidence-cited medication-safety assistant** (decision support, not diagnosis). Sign in with email (one-time-code verification) or Google. A prescription photo is read by a vision model; the clinician **confirms** the list (matched / unresolved brands, "I checked this against the prescription"). A six-step live analysis follows (upload → OCR → brand→generic → interaction check → guardrail & verify → report). Results show **severity** (major / moderate / minor / unknown), **verification status**, and an **evidence panel** (source, licence, confidence) per finding; no record is shown as unknown and never as safe. Outputs: clinician view with PDF handoff, plain-Bangla patient card (no start/stop/dose advice), agent trace, a what-if lookup, patient history with comparison between analyses, follow-up board and a **rule-based review queue** (nine written rules, no AI ranking; "not flagged" is never called safe), and a **Trust center** listing what is known, unverified and planned. Synthetic demo data is labelled.

## How it maps to the judging criteria
| Criterion | What we built |
|---|---|
| **Innovation** | Human-confirmed scan; brand→generic resolver that never guesses; Verifier agent; honest "unknown" states; Trust center |
| **Technical** | LangGraph multi-agent pipeline; RAG (semantic chunking, contextual prefixes, graph links) on Postgres + pgvector; custom **MCP server (SSE)** + external PubMed MCP utility; Celery/Redis; Ollama `bge-m3`; Gemini vision; n8n ingest; Docker on Azure |
| **Business / Global** | Clinic SaaS + NRB family subscription; licensed-data upgrade path (DDInter is non-commercial); South Asia expansion |
| **Impact / Ethics** | Goal: fewer medication errors. Consent records, audit log, PII redaction before cloud calls, no dosing, disclaimer on every screen |
| **Scalability / NRB** | Stateless API, async workers, containerised deploy; NRB family view; built by the team itself, no NRB/mentor contribution to date |
| **Presentation** | 3-minute video with five segments; live demo with ready judge accounts |

## Data & AI approach
openFDA labels + DDInter + curated brand sample → parse → clean → store (Postgres + pgvector). Retrieval returns chunk IDs as citations. Deterministic MCP tools are shared by the agents and the Verifier; PII is redacted before cloud calls.

## AI tools & process (AI-DLC)
Built with **Claude (Anthropic)** guided by rule files in `.claude/rules/`; docs-first, 14-day roadmap, PR + lead review, pytest, human-reviewed AI code. In the product: Gemini `gemini-3.8-flash` (scan, fallback `gemini-3.6-flash`), Ollama `bge-m3` + `qwen3.5:2b`.

## Measured outcomes
One synthetic demo run (analysis #3): 6 drugs, 15 pairs checked — 2 major, 5 moderate, 1 minor, 7 unknown/no record; 11 findings verified against a cited record, 4 unverified. These are run outputs, **not accuracy figures**: no accuracy is claimed until the pharmacist-reviewed test set is run. Target: 100% of warnings carry a cited source.

## Limits & next
Brand mapping is a sample (unverified until pharmacist review); public data has gaps; scans need human confirmation; not a diagnosis/dosing tool; no clinical validation yet. Next: verified brand list, independent evaluation, licensed data, ESP32 vitals (firmware ready, not integrated), federated learning.