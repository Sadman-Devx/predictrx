# Data pipeline: ingest → parse → clean → store → analytics

Run everything with the **backend virtualenv active**, from the repo root. Raw/processed files live in
`data/raw/` and `data/processed/` (git-ignored). Licence notes: `../SOURCES.md`.

| Stage | Script | Input → Output |
|---|---|---|
| Ingest | `ingest_openfda.py` | openFDA API → `data/raw/openfda/<drug>.json` |
| Parse | `parse_labels.py` | raw → `data/processed/openfda_parsed.jsonl` (named sections only) |
| Clean | `clean.py` | keep single-ingredient labels for seed drugs, dedupe, add licence note → `openfda_clean.jsonl` |
| Store | `load.py` | upsert `Drug`, `KnowledgeDocument`, `Chunk` |
| RAG index | `cd backend && python manage.py index_knowledge` | chunk embeddings and graph edges (requires PostgreSQL/pgvector and configured Ollama embedding model) |
| Analytics | `report.py` | coverage report |
| DDInter ingest | `ingest_ddinter.py` | registers the CSVs you downloaded (no scraping) → `data/raw/ddinter/` + manifest |
| DDInter parse | `parse_interactions.py` | 8 CSVs → unique drug pairs (`ddinter_drugs/pairs.jsonl`) |
| DDInter store | `load_ddinter.py` | `Drug` + `Interaction` (severity only; idempotent; `--replace` to reload) |
| All | `run_all.py` | openFDA steps in order (`--with-ddinter` adds the DDInter steps) |

## Run
```bash
# needs: docker compose up -d db (backend/), migrate done, OPENFDA_API_KEY in .env (optional but recommended)
python data/pipeline/run_all.py --limit 10
# or step by step:
python data/pipeline/ingest_openfda.py --limit 10 --delay 0.5
python data/pipeline/parse_labels.py && python data/pipeline/clean.py
python data/pipeline/load.py && python data/pipeline/report.py
```
Safe to re-run: `load.py` is idempotent (documents keyed by `content_hash`).
Add/remove drugs by editing `seed_drugs.txt` (`us_generic_name | alias1, alias2`).

Brand mappings are loaded separately with `python data/pipeline/load_brands.py --dry-run` before
`python data/pipeline/load_brands.py`. Each row must include a concrete source reference and access date.
Imports always remain unverified; review and verification happen in Django admin. The committed sample
sheet contains pending provenance and should not be loaded as real data.

## DDInter
```bash
python data/pipeline/ingest_ddinter.py --from "<folder with the 8 CSVs>" --version "<version shown on the site>"
python data/pipeline/parse_interactions.py && python data/pipeline/load_ddinter.py && python data/pipeline/report.py
```
Use `--dry-run` with `load_ddinter.py` to validate the processed JSONL shape without database writes.
The download files contain only: `DDInterID_A, Drug_A, DDInterID_B, Drug_B, Level`. No mechanism / management / references.
So `Interaction.mechanism` and `.management` stay empty for DDInter rows; explanations come from openFDA label chunks.

## Data and runtime limits
- RAG indexing code exists, but it requires a running PostgreSQL/pgvector database and an embedding model
  configured to match `EMBEDDING_DIM`; passing unit tests does not establish a successful production index.
- The committed brand sheet is a draft with missing references/access dates. It must remain unloaded until
  its real supporting records are documented and a pharmacist reviews it.

## Tests
`cd backend && pytest tests/test_pipeline.py` — uses a hand-made fixture with synthetic text (not real label content).