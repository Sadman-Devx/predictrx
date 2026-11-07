# Data pipeline: ingest → parse → clean → store → analytics

Scripts live here; large raw/processed files do not (git-ignored under `data/raw`, `data/processed`).
The n8n workflow (`automation/n8n/`) can orchestrate these steps, but each step must also run from the command line.

| Stage | Script (to write) | Input → Output |
|---|---|---|
| Ingest | `ingest_openfda.py`, `ingest_ddinter.py`, `ingest_brands.py` | source → `data/raw/` |
| Parse | `parse_labels.py`, `parse_interactions.py` | raw → structured JSON/CSV |
| Clean | `clean.py` | normalize names (lower-case, salts), dedupe by `content_hash`, drop malformed rows |
| Store | `load.py` | upsert `Drug`, `Interaction`, `KnowledgeDocument`, `Chunk` (+ embeddings), `GraphEdge` |
| Analytics | `report.py` | coverage: drugs per source, interactions by severity, unresolved-brand rate |

Owner: Lead Dev (Day 3). Record every source's license in `../SOURCES.md` first.
