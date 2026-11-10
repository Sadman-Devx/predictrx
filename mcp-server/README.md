# PredictRx MCP Server

Custom MCP server exposing deterministic drug tools to the LangGraph agents **and** to the Verifier.

| Tool | Input | Output |
|---|---|---|
| `resolve_brand` | brand/generic text, optional strength | `resolved` (generic, method, confidence, verified) — or `unresolved` + candidates/suggestions |
| `lookup_drug` | generic name or brand | record, aliases, formulation variants, source counts — or `not_found` |
| `check_interaction` | two names | `found` (severity, evidence refs, label passages) / `no_record` / `unresolved_input` / `invalid` |
| `check_interactions` | list of names | every pair + summary counts |

Severity comes from DDInter (download files carry severity only — no mechanism/management text);
explanations come from openFDA label passages. `no_record` and `unknown` are never "safe".

## Transport
- **SSE (default, used in the app):** `python server.py` → `http://localhost:8001/sse`
- **Stdio (for local clients such as an IDE/desktop client):** `MCP_TRANSPORT=stdio python server.py`

## Host vs. client (for the Congress notes)
- **MCP server:** this folder.
- **MCP host / client:** the LangGraph worker in `backend/ai/` (it connects to `MCP_SERVER_URL`).
- **External MCP:** one public MCP server is also used as a client (choose during build, document here:
  name, URL, what it is used for).

## Run
**Run it with the backend virtualenv** (it imports the Django app) and Postgres running:
```bash
cd backend && source .venv/Scripts/activate      # Git Bash on Windows
cd .. && python mcp-server/server.py             # http://localhost:8001/sse
```

## Status
Real data (Drug / BrandMapping / Interaction / label chunks). Response shapes are covered by `backend/tests/test_resolver.py`.