# PredictRx — 1-page summary

**Track:** HealthTech · International AI Builders Congress 2026 · **Team:** 5 · **Market:** Bangladesh (NRB family use-case)
**Repo:** github.com/Sadman-Devx/predictrx · **Live demo:** https://predictrx-assi.malaysiawest.cloudapp.azure.com · **Video:** [TBD] · **Figma:** https://www.figma.com/design/5fV8aTEasT6l4AY8xWPIqj/PredictRx-%E2%80%93-Smart-Healthcare-Management-System

## Problem
Patients in Bangladesh take medicines by **brand name** and carry paper prescriptions, while interaction databases are in English and keyed by generic name. Doctors have little time; families abroad (NRBs) cannot see risk in a parent's medication list. Black-box alerts without sources are hard to trust.

## Solution
PredictRx is a **Bangla-first, evidence-cited medication-safety assistant** (decision support, not diagnosis). A doctor or caregiver uploads a prescription photo or types a list; a multi-agent pipeline resolves brand → generic, checks interactions, and a **Verifier agent** cross-checks every finding. Each warning shows mechanism, **source, confidence and verification status**. No source → "insufficient evidence". Outputs: doctor view, plain-Bangla patient card (no dosing), and a consent-gated NRB family view, plus a small what-if view.

## How it maps to the judging criteria
| Criterion | What we built |
|---|---|
| **Innovation (20)** | Prescription scan with human confirmation; brand→generic resolver that never guesses; Verifier agent; evidence-cited, honest-about-unknown output |
| **Technical (20)** | LangGraph multi-agent pipeline; RAG with semantic chunking, contextual prefixes and graph links on Postgres + pgvector; custom **MCP server (SSE)** + external PubMed MCP utility; Celery/Redis async; Ollama `bge-m3` embeddings; Gemini for vision; n8n ingest pipeline; Docker on Azure |
| **Business / Global (20)** | Clinic/hospital SaaS and NRB family subscription; licensed-data upgrade path (DDInter is non-commercial); expandable to other South Asian markets |
| **Impact / Ethics (20)** | Goal: fewer medication errors. Consent + audit log, PII redaction before cloud calls, no dosing, disclaimer on every screen, synthetic demo data, simulated data labelled |
| **Scalability / NRB (10)** | Stateless API, async workers, containerised deploy; NRB family guardian view; built by the team itself, no NRB/mentor contribution to date |
| **Presentation (10)** | 3-minute video following the five required segments; live demo with ready-made judge accounts |

## Data & AI approach
openFDA labels + DDInter + curated brand sample → parse → clean → store (Postgres + pgvector). Retrieval returns chunk IDs as citations. Deterministic MCP tools are shared by agents and the Verifier; PII is redacted before cloud calls.

## AI tools & process (AI-DLC)
Built with **Claude (Anthropic)** guided by rule files in `.claude/rules/`; docs-first, 14-day roadmap, PR + lead review, pytest, human-reviewed AI code. In the product: Gemini `gemini-3.8-flash` (scan, fallback `gemini-3.6-flash`), Ollama `bge-m3` + `qwen3.5:2b`.

## Measured outcomes
[TBD — fill only from a recorded run on the pharmacist-reviewed test set: n = __, recall = __, precision = __, brand-resolution accuracy = __.] Target: **100% of warnings carry a cited source**. No accuracy claim is made without a measured test set.

## Limits & next
Brand mapping is a sample (unverified until pharmacist review); public data has coverage gaps; scans need human confirmation; not a diagnosis/dosing tool. Next: verified brand mapping, independent evaluation, licensed data, ESP32 vitals, federated learning.