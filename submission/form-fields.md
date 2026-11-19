# Portal form text — International AI Builders Congress 2026 (HealthTech)

> Fill everything marked `[TBD]` / `[CONFIRM]` with **real** facts before pasting. Character minimums: token optimization ≥ 50, AI-DLC ≥ 100, other notes ≥ 80. Counts below are approximate — paste into a counter before submitting.

## Basics
- **Project name:** PredictRx
- **Track:** HealthTech (standard team build)
- **One-line description:** Bangla-first, evidence-cited medication-safety decision support for doctors and caregivers: prescription photo → brand-to-generic resolver → multi-agent analysis → verified, source-cited findings.
- **Team size:** 5 (confirm against the portal's member list)
- **Female member(s):** 1 (one female member in the team of 5)
- **NRB / mentor contribution:** None. The team built the project on its own (no NRB or mentor contribution).

## Links
| Field | Value |
|---|---|
| Demo video (YouTube) | [TBD] |
| GitHub (public) | https://github.com/Sadman-Devx/predictrx |
| Live demo | https://predictrx-assi.malaysiawest.cloudapp.azure.com (confirm it opens from a phone on mobile data) |
| Figma | https://www.figma.com/design/5fV8aTEasT6l4AY8xWPIqj/PredictRx-%E2%80%93-Smart-Healthcare-Management-System?node-id=0-1&t=Q0qGxheA9FT3uQgG-1 (open it logged out to confirm it works) |
| Supporting link 1 | [TBD — e.g. docs/PRD.md on GitHub] |
| Supporting link 2 | [TBD — e.g. docs/architecture.md on GitHub] |
| Supporting link 3 | [TBD — e.g. mcp-server/README.md on GitHub] |

Judge access: put the demo doctor and family logins **only in the portal notes** (never in the repo): `[TBD — email / password]`.

## Token optimization note (≥ 50 chars)
```
Deterministic tools (MCP check_interaction/resolve_brand) and a Redis cache do lookups instead of the LLM; label chunks are retrieved by ID so only relevant passages reach the prompt; embeddings run locally on Ollama (bge-m3) and are stored in pgvector, so they are never recomputed; the what-if twin uses no LLM at all.
```
> Confirm each clause is true in the final build before submitting; delete any that is not.

## AI-DLC note (≥ 100 chars)
```
We followed a docs-first AI-assisted development life cycle: six design docs (PRD, architecture, backend-design, design, roadmap, rule) were written before coding, and AI-assistant rule files in the repo (project, backend, frontend, AI-safety) kept generated code consistent with them. Work followed a 14-day roadmap with a "done when" check per day, feature freeze on 16 Nov, feature-branch → PR → lead review → dev → main, pytest tests (guardrails, PII redaction, verifier), and a CHANGELOG. AI-generated code was reviewed by a human before merge. AI coding tool used: Claude (Anthropic), guided by the rule files in `.claude/rules/`.
```

## Stack & AI tools (paste into the stack field)
- **LLM:** Gemini `gemini-3.8-flash` (prescription scan, vision), fallback `gemini-3.6-flash`; local model `qwen3.5:2b` via Ollama for sensitive text where local mode is enabled
- **Embeddings:** Ollama `bge-m3` (1024-dim, batch size 48), stored in Postgres + pgvector
- **Agents:** LangGraph — Resolver → Clinical Notes → Drug Interaction → Advisory → Verifier
- **RAG:** semantic chunking + contextual chunk prefixes + graph RAG (drug ↔ interaction ↔ section edges); retrieval returns chunk IDs used as citations
- **MCP:** custom server over **SSE** (`resolve_brand`, `lookup_drug`, `check_interaction`); host/client = the LangGraph worker. External MCP: `cyanheads/pubmed-mcp-server` for a research-only literature utility (`search_pubmed_literature`), not used in clinical analysis
- **Automation:** n8n ingest workflow (exports in `automation/n8n/`)
- **Backend / frontend:** Django + DRF, Celery + Redis · React + Vite + TypeScript, Bangla/English i18n
- **Hosting:** Microsoft Azure VM, Docker Compose, Caddy (HTTPS). final URL is the Azure one; a Cloudflare quick tunnel is only a backup
- **AI coding tool:** Claude (Anthropic)

## Data lifecycle
ingest (openFDA drug labels, DDInter interactions, curated brand sample) → parse → clean → store (Postgres + pgvector; embeddings in `Chunk.embedding`) → index → analytics/coverage report. Scripts in `data/pipeline/`, n8n export in `automation/n8n/`.

## Hosting / tunnel notes
Microsoft Azure VM (size: [TBD], region: Malaysia West), Docker Compose, Caddy for HTTPS. Public URL: https://predictrx-assi.malaysiawest.cloudapp.azure.com. Kept running by: [TBD] until: [TBD]. Data restored from a dump of the knowledge tables only (no user data). Fallback: pre-recorded demo video + screenshots.

## Other notes (≥ 80 chars)
```
Decision support only — no diagnosis or dosing. Every warning shows its source or says "insufficient evidence". Demo uses synthetic data (badge shown). Limits: brand mapping is a sample (unverified until pharmacist review); DDInter is CC BY-NC-SA (prototype use with attribution; a licensed source is needed commercially); accuracy figures are reported only from a pharmacist-reviewed test set. Judge demo accounts are in the portal notes.
```

## Measurable outcomes
Fill **only** from a recorded eval run on the reviewed test split:
- Test-set size (n): [TBD]
- Interaction recall: [TBD] · Precision: [TBD]
- Brand-resolution accuracy (held-out): [TBD]
- Warnings with a cited source: [TBD — target 100%, verified by the automated check]

If the reviewed set is not ready, write: "Evaluation framework implemented (dev/test split, recall/precision runner); measured results will be published once the pharmacist-reviewed test set is complete." Do **not** use numbers from `data/fixtures/eval_cases.csv` — it holds draft, unreviewed cases.

## Final check before pressing Submit
- [ ] Deadline re-confirmed on the live portal
- [ ] Every `[TBD]` / `[CONFIRM]` above is resolved or deleted
- [ ] All links open in a private window / second account
- [ ] Character minimums met (token ≥ 50, AI-DLC ≥ 100, other ≥ 80)
- [ ] Team / female / NRB fields match reality (1 female member; no NRB/mentor contribution); checked by a second person
- [ ] Screenshot of the submission confirmation saved