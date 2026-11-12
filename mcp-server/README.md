# PredictRx MCP Server

Custom MCP server exposing deterministic drug tools to the LangGraph agents **and** to the Verifier.

| Tool | Input | Output |
|---|---|---|
| `resolve_brand` | brand string, optional strength | generic, confidence **+ basis** (`match_type` exact/generic/fuzzy, `source`, `verified`) — or `unresolved` (+ `reason`, optional `candidates`) |
| `lookup_drug` | generic name | record + sources — or `not_found` |
| `check_interaction` | two generic names | severity, mechanism, management, source — or `no_record` (+ `reason`; never means "safe") |

## Transport
- **SSE (default, used in the app):** `python server.py` → `http://localhost:8001/sse`
- **Stdio (for local clients such as an IDE/desktop client):** `MCP_TRANSPORT=stdio python server.py`

## Host vs. client (for the Congress notes)
- **MCP server:** this folder.
- **MCP host / client:** the LangGraph worker in `backend/ai/` (it connects to `MCP_SERVER_URL`).
- **External MCP:** one public MCP server is also used as a client (choose during build, document here:
  name, URL, what it is used for).

## Data access
The tools call `apps.drugs.services` (same functions as the REST API), so the server needs the repo's `backend/` code,
the same `.env` (`DATABASE_URL`, `REDIS_URL`) and the tables loaded (`data/pipeline/load.py`, `load_brands.py`).

## Run
```bash
cd mcp-server
pip install -r requirements.txt
python server.py                 # SSE on :8001
python test_client.py            # second terminal: calls every tool over SSE, exits 0 on success
```

## Status
Day 4: DB-backed. Response shapes are a contract (Verifier + tests depend on them) — add keys, never change meaning.
Brand rows in the sample sheet are **unreviewed** (`verified=false`) until a pharmacist/mentor checks them.
