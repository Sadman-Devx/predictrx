"""PredictRx custom MCP server (SSE transport).

Tools (deterministic, backed by the Django tables through apps.drugs.services — the same functions the REST API uses):
  resolve_brand(brand, strength?)  -> generic + confidence + basis (match_type/source/verified), or {"status": "unresolved"}
  lookup_drug(generic_name)        -> basic record + source list, or {"status": "not_found"}
  check_interaction(drug_a, drug_b)-> severity/mechanism/management/source, or {"status": "no_record"}

The Verifier agent calls the SAME tools, so a finding can be checked independently of the LLM's wording.
"no_record" means "no evidence found" — never "safe".

Run (SSE):   python server.py            -> http://localhost:8001/sse
Run (stdio): MCP_TRANSPORT=stdio python server.py
Needs: the repo's backend/ code, the same .env (DATABASE_URL, REDIS_URL) as the API, and `pip install -r requirements.txt`.
"""
import os
import sys
from pathlib import Path

# ---- Django bootstrap (the server reads the same tables as the API) ----
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django  # noqa: E402

django.setup()

from asgiref.sync import sync_to_async  # noqa: E402
from django.db import close_old_connections  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

from apps.drugs import services  # noqa: E402

mcp = FastMCP(
    "predictrx-drug-tools",
    host=os.environ.get("MCP_SERVER_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_SERVER_PORT", "8001")),
)


def _run_db(fn, *args) -> dict:
    """Run a blocking ORM function; close the connection afterwards so a long-lived server never holds a stale one."""
    close_old_connections()
    try:
        return fn(*args)
    finally:
        close_old_connections()


async def _call(fn, *args) -> dict:
    # The ORM refuses to run inside the event loop; hand it to a worker thread.
    return await sync_to_async(_run_db, thread_sensitive=True)(fn, *args)


@mcp.tool()
async def resolve_brand(brand: str, strength: str | None = None) -> dict:
    """Resolve a locally used brand name to a generic drug name. Never guesses: returns 'unresolved' if unknown
    or ambiguous. A 'fuzzy' match_type means a typo-match: confirm with the user."""
    return await _call(services.resolve_brand, brand, strength)


@mcp.tool()
async def lookup_drug(generic_name: str) -> dict:
    """Basic record for a generic drug name (or alias), with the sources that mention it."""
    return await _call(services.lookup_drug, generic_name)


@mcp.tool()
async def check_interaction(drug_a: str, drug_b: str) -> dict:
    """Interaction record for a pair of GENERIC names. 'no_record' means no evidence found — NOT that the pair is safe."""
    return await _call(services.check_interaction, drug_a, drug_b)


if __name__ == "__main__":
    mcp.run(transport=os.environ.get("MCP_TRANSPORT", "sse"))
