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
mcp-server/   Custom MCP server (SSE) — resolve_brand, lookup_drug, check_interaction
data/         Pipeline scripts + SOURCES.md (licenses)
automation/   n8n workflow exports
firmware/     ESP32 vitals sketch (roadmap, not in the demo)
deploy/       Run notes + Cloudflare Tunnel
submission/   Congress pack (summary, video script, form text, checklist)
docs/         The six design docs
.cursor/rules AI-DLC rules for the team
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
Run tests: `cd backend && pytest`

## What the scaffold already contains
- Django project, custom email-login `User` (roles), JWT auth, audit log, consent/family models, drug/brand/interaction
  models, RAG tables (pgvector), analysis/trace/finding models, eval models, ESP32 `vitals` app (roadmap).
- `RiskFinding` refuses to save a severity without evidence. Output guardrails + PII redaction with tests.
- LangGraph pipeline with five **stub** agents that keep the trace contract.
- MCP server (SSE) with three tools returning **placeholder** data.
- React shell: Bangla/English toggle, design tokens, severity badge (colour + shape + text), disclaimer strip, login.

## What is NOT done (by design — see roadmap)
Agent logic, RAG ingestion/retrieval, real MCP data, OCR, API endpoints beyond auth/health, real screens, deployment.

## Branching
`main` (tested) ← `dev` ← `feature/<name>`. PR + Lead review. Feature freeze: **16 Nov**.

## Data & safety
See `data/SOURCES.md` (verify every license) and `docs/rule.md`. Use synthetic or consented data only.
