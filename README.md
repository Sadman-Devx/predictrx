# PredictRx

Bangla-first, evidence-cited **medication-safety decision support** for doctors and caregivers.
Prescription photo → brand→generic resolver → multi-agent analysis (LangGraph) → verified, source-cited findings.
**Not a diagnosis or dosing tool.**

International AI Builders Congress 2026 · HealthTech · standard team build · submission target **20 Nov 2026**.

## Read first
`docs/PRD.md` · `docs/architecture.md` · `docs/backend-design.md` · `docs/design.md` · `docs/roadmap.md` (who does what, which day) · `docs/rule.md`

## Repo layout
```
backend/      Django + DRF, Celery, pgvector, LangGraph pipeline (ai/)
frontend/     React + Vite + TypeScript, Bangla-first (i18n)
mcp-server/   Custom MCP server (SSE) — drug tools + allowlisted PubMed research search
data/         Pipeline scripts + SOURCES.md (licenses)
automation/   n8n workflow exports
firmware/     ESP32 vitals sketch (roadmap, not in the demo)
deploy/       Run notes + Cloudflare Tunnel
submission/   Congress pack (summary, video script, form text, checklist)
docs/         The six design docs
.claude/rules AI-DLC rules for the team
```

## Quick start
```bash
cp .env.example .env                         # edit values; never commit .env

# 1) infrastructure
cd backend && docker compose up -d           # Postgres+pgvector, Redis, Ollama

# 2) backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/local.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver                   # http://localhost:8000  (API docs: /api/docs/)
celery -A config worker -l info              # separate terminal

# 3) MCP server (separate terminal)
cd ../mcp-server && pip install -r requirements.txt && python server.py

# 4) frontend (separate terminal)
cd ../frontend && npm install && npm run dev # http://localhost:5173
```
To enable Google sign-in, set the same Google Web client ID as `GOOGLE_CLIENT_ID` in the repository `.env` and
`VITE_GOOGLE_CLIENT_ID` in `frontend/.env` (see `frontend/.env.example`). Add each frontend origin, such as
`http://localhost:5173`, to the Google OAuth client's authorized JavaScript origins, then restart Django and Vite.
The Google ID-token flow does not need a client secret.

Run tests: `cd backend && pytest`

## Implementation and remaining validation
The repository contains Django APIs and models for drugs, interactions, analysis, patients, consent, family
sharing and clinician-owned follow-up tasks; RAG/indexing and evaluation code; the LangGraph analysis pipeline; a
DB-backed local MCP server; and the React clinician/family flows, including the What-if simulation and follow-up
board. The optional PubMed MCP utility accepts only
fixed, general research topics and is excluded from clinical-analysis tools.

Code being present is not the same as clinical or production validation. In particular:
- The committed brand-mapping sheet has pending provenance and must not be loaded until exact source references
  and access dates are recorded; a pharmacist must review mappings in Django admin.
- Independent pharmacist/reviewer-labeled evaluation cases and measured KPI results are not supplied. Do not
  invent labels, review sign-off, or metrics.
- RAG indexing needs a working PostgreSQL/pgvector database and an embedding model matching `EMBEDDING_DIM`.
- Clinical wording, mobile/browser QA, and deployment/demo readiness require separate human verification.

## Branching
`main` (tested) ← `dev` ← `feature/<name>`. PR + Lead review. Feature freeze: **16 Nov**.

## Data & safety
See `data/SOURCES.md` (verify every license) and `docs/rule.md`. Use synthetic or consented data only.
