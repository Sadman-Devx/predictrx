# PredictRx

PredictRx is a Bangla-first, evidence-cited medication-safety decision-support platform for
clinicians and caregivers. It accepts prescription photos or typed/selected medicines, resolves
Bangladesh-used brand names to generics, retrieves open drug-label and interaction evidence, and
returns a traceable multi-agent analysis.

> **Safety note:** PredictRx is not a diagnosis, prescription, or dosing tool. It does not replace
> a pharmacist or doctor. Public data can be incomplete, and a "no interaction found" result is
> never the same as proof that a combination is safe.

## Repository at a glance

```text
Predictrx
├── backend/          Django REST API, Celery, LangGraph agents, RAG and models
├── frontend/         React 19 + Vite + TypeScript, Bangla-first UI
├── mcp-server/       DB-backed MCP SSE server for deterministic drug tools
├── data/             Source licenses and openFDA/DDInter/brand ingestion pipeline
├── automation/n8n/   Optional n8n data-ingestion workflow exports
├── deploy/           Docker Compose and Azure/Caddy production deployment guide
├── docs/             PRD, architecture, backend design, UX and safety rules
├── design/           Figma exports and design links
├── firmware/         ESP32/MAX30102 vitals prototype (outside the demo flow)
└── submission/       Congress summary, form text and demo video script
```

## Features

- Prescription image upload and vision-based draft extraction, followed by human review
- Manual brand/generic drug search and medication entry
- Brand-to-generic resolution with exact, fuzzy and unresolved result states
- PostgreSQL/pgvector knowledge search with semantic chunking, contextual prefixes and graph edges
- LangGraph analysis pipeline: Resolver → Clinical Notes → Drug Interaction → Advisory → Verifier
- OpenFDA/DDInter-backed citations, confidence, verification status and visible agent traces
- Doctor, patient, caregiver/family, follow-up and what-if simulation views
- JWT authentication, refresh-cookie sessions, email OTP verification and social sign-in hooks
- Consent, family sharing, audit records and clinician-owned follow-up tasks
- Django admin for drugs, mappings, users and evaluation review
- Optional ESP32 vitals ingest module
- Bangla and English i18n

## Architecture

```text
React/Vite Browser
        │
        │ REST / JSON
        ▼
Django/DRF API ───── PostgreSQL + pgvector
        │                     │
        │ enqueue             │ data/evidence
        ▼                     │
Redis + Celery workers        │
        │                     │
        └──── LangGraph agents│
                 │           │
                 ├─ RAG ─────┘
                 └─ MCP tools ─► predictRx MCP server (SSE)
                                      │
                                      └─ Drug, BrandMapping, Interaction tables
```

The frontend never connects to the database or an LLM directly. Celery owns slow OCR/analysis work.
Cloud providers are optional; local Ollama models can handle supported sensitive-text workflows.
For more detail, read [the architecture](docs/architecture.md) and
[backend design](docs/backend-design.md).

## Technology

| Area | Stack |
|---|---|
| Frontend | React 19, Vite 8, TypeScript 7, React Router 7 |
| Backend | Django 5.2, Django REST Framework, SimpleJWT, drf-spectacular |
| Database | PostgreSQL 16, pgvector, pgvector HNSW index |
| Async work | Celery 5, Redis 7 |
| AI | LangGraph, Anthropic-compatible cloud LLM option, Ollama, RAG |
| MCP | Python MCP server over SSE; stdio transport is also supported |
| Testing | pytest, pytest-django, factory_boy |
| Admin | Django Admin, django-unfold optional skin |
| Deployment | Docker Compose, Caddy, Microsoft Azure VM |

## Prerequisites

- Windows 10/11 with PowerShell
- Python 3.12
- Node.js 22 and npm
- Docker Desktop
- Git

## Quick start (Windows)

Run commands from the repository root unless a step says otherwise.

### 1. Environment

```powershell
Copy-Item .env.example .env
```

Edit `.env` and keep secrets out of Git. At minimum, verify the local database, Redis and API URLs.
Never put placeholder text into an API-key variable: leave the key empty to disable that provider.

### 2. Infrastructure

```powershell
cd backend
docker compose up -d db redis ollama mailpit
docker compose ps
```

Optional local services are also available:

```powershell
# Pull the embedding model
docker compose exec ollama ollama pull bge-m3

# Mailpit inbox
Start-Process http://localhost:8025
```

Mailpit SMTP uses port `1025`; the web inbox is at `http://localhost:8025`.

### 3. Backend

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements/local.txt

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Backend endpoints:

- API: `http://localhost:8000/api/`
- Swagger UI: `http://localhost:8000/api/docs/`
- OpenAPI schema: `http://localhost:8000/api/schema/`
- Django admin: `http://localhost:8000/admin/`
- Health: `http://localhost:8000/api/health/`

Start Celery in a second activated terminal:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
celery -A config worker -l info
```

### 4. MCP server

In a third terminal:

```powershell
cd mcp-server
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python server.py
```

The SSE endpoint is `http://localhost:8001/sse`. The server uses the repository database and
`apps.drugs.services`, so migrations and drug data must already exist. See
[the MCP server guide](mcp-server/README.md).

### 5. Frontend

In a fourth terminal:

```powershell
cd frontend
Copy-Item .env.example .env
npm ci
npm run dev
```

Open `http://localhost:5173`.

Google sign-in is optional. Set the same public Google Web client ID in the root `.env`
as `GOOGLE_CLIENT_ID` and in `frontend/.env` as `VITE_GOOGLE_CLIENT_ID`. Add
`http://localhost:5173` to the OAuth client's authorized JavaScript origins.

### 6. Run the full stack in Docker

For an API/worker container profile after local setup:

```powershell
cd backend
docker compose --profile full up --build
```

The compose profile starts PostgreSQL, Redis, Ollama, Django API and Celery worker together.
The MCP server and frontend are still started separately for local development.

## Data pipeline

The data pipeline is intentionally script-first and independently runnable.
Large raw/processed datasets are git-ignored.

```powershell
# Light openFDA demo: ingest, parse, clean, load and report
python data/pipeline/run_all.py --limit 10

# Reuse already downloaded openFDA raw files
python data/pipeline/run_all.py --skip-ingest

# Include registered DDInter files
python data/pipeline/run_all.py --skip-ingest --with-ddinter

# Build RAG embeddings from the Django app
cd backend
python manage.py index_knowledge
```

Source and license status is recorded in [data/SOURCES.md](data/SOURCES.md). Brand mapping
sheets are currently unreviewed: do not load or present mappings as verified until
row-level sources and access dates are recorded and a pharmacist reviews them.

## Tests and validation

Run the backend and frontend checks from the repository root:

```powershell
cd backend
pytest -q

cd ../frontend
npm ci
npm run typecheck
npm run build
```

The GitHub Actions workflow runs both suites on pull requests and pushes to `main`/`dev`.

Useful backend checks:

```powershell
cd backend
python manage.py check
python manage.py run_pipeline --help
python manage.py run_eval --help
```

## Main API areas

| Area | Main routes |
|---|---|
| Authentication | `/api/auth/register/`, `/api/auth/login/`, `/api/auth/verify-email/` |
| Patients and consent | `/api/patients/` and related family endpoints |
| Prescription scans | `/api/prescriptions/scan/` |
| Drugs and interactions | `/api/drugs/`, `/api/drugs/search/`, `/api/interactions/check/` |
| Analysis | `/api/analysis/`, `/api/analysis/{id}/`, `/api/analysis/{id}/trace/` |
| What-if simulation | `/api/twin/` and `/api/analysis/{id}/twin/` |
| Follow-ups | `/api/followups/` |
| Evaluation | `/api/evaluation/` |
| System | `/api/health/`, `/api/schema/`, `/api/docs/` |

Exact request/response fields should be checked against the live Swagger schema.

## Deployment

The production reference is Azure VM + Docker Compose + Caddy:

- Follow [deploy/README.md](deploy/README.md)
- Copy [deploy/env.production.example](deploy/env.production.example) to the repository root `.env`
- Never commit `.env`, public data dumps, private prescription images or real patient records
- Restore only approved knowledge-table data
- Test public DNS, HTTPS, email OTP, mobile UI and reboot recovery before sharing the URL

## Safety and data rules

- Synthetic or explicitly consented data only in demos
- No diagnosis, dosing, start/stop, or "safe" claims
- Every warning needs a source
- No source or no record means unverified/insufficient evidence, not a safe result
- PII must be redacted before cloud-provider calls
- Patient and family access is consent-gated and audited
- DDInter is CC BY-NC-SA 4.0 and is only suitable for a non-commercial prototype without permission
- openFDA data remains unvalidated and must carry its medical-decision disclaimer

Read [docs/rule.md](docs/rule.md), [docs/PRD.md](docs/PRD.md),
[data/SOURCES.md](data/SOURCES.md) and [CONTRIBUTING.md](CONTRIBUTING.md) before modifying product behavior.

## Current validation status

The repository contains implemented Django models/APIs, the React flows, RAG/indexing code,
Celery/LangGraph analysis and DB-backed MCP tools. This is not yet clinical or production validation:

- Brand mappings require provenance and pharmacist review
- Independent, pharmacist-labeled evaluation sets and measured KPI reports are not included
- Embeddings must match `EMBEDDING_MODEL` and `EMBEDDING_DIM`
- Clinical wording, browser/mobile QA and cloud deployment remain human-verified tasks
- ESP32 is a roadmap prototype, not part of the core demo

Do not invent review sign-off or accuracy metrics.

## Team workflow

- `main`: tested, demo-ready
- `dev`: integration branch
- `feature/<area>-<name>`: feature work
- Open a PR into `dev`; the lead developer reviews it before merge
- Run backend and frontend checks before opening a PR
- Feature freeze: 16 November; bug fixes only afterward
