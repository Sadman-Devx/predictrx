# PredictRx MCP Server

Custom MCP server exposing deterministic drug tools to the LangGraph agents **and** to the Verifier.

| Tool | Input | Output |
|---|---|---|
| `resolve_brand` | brand string, optional strength | generic, confidence, verified flag — or `unresolved` |
| `lookup_drug` | generic name | record + sources — or `not_found` |
| `check_interaction` | two generic names | severity, mechanism, management, source — or `no_record` |

## Transport
- **SSE (default, used in the app):** `python server.py` → `http://localhost:8001/sse`
- **Stdio (for local clients such as an IDE/desktop client):** `MCP_TRANSPORT=stdio python server.py`

## Host vs. client (for the Congress notes)
- **MCP server:** this folder.
- **MCP host / client:** the LangGraph worker in `backend/ai/` (it connects to `MCP_SERVER_URL`).
- **External MCP:** one public MCP server is also used as a client (choose during build, document here:
  name, URL, what it is used for).

## Run
```bash
cd mcp-server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

## Status
Placeholder data only (`SAMPLE_*`). The lead dev replaces it with queries against the Django tables.
Response shapes must not change — the Verifier and the tests depend on them.
