"""PredictRx custom MCP server (SSE transport) — answers from the real database.

Tools:
  resolve_brand(brand, strength?)   -> generic + confidence + verified flag, or status "unresolved" (+ suggestions)
  lookup_drug(generic_name)         -> record + counts of sources, or "not_found"
  check_interaction(drug_a, drug_b) -> severity + evidence refs (+ label passages), or "no_record"
  check_interactions(drugs)         -> every pair of a medication list in one call

The Verifier agent calls the SAME tools, independent of the LLM's wording.

IMPORTANT: run this with the BACKEND virtualenv (it imports the Django app) and with Postgres running:
    python mcp-server/server.py                  (SSE, default)
    MCP_TRANSPORT=stdio python mcp-server/server.py
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "data" / "pipeline"))
from common import django_setup  # noqa: E402

django_setup()

from asgiref.sync import sync_to_async  # noqa: E402
from django.db import close_old_connections  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

from apps.drugs import services  # noqa: E402

mcp = FastMCP(
    "predictrx-drug-tools",
    host=os.environ.get("MCP_SERVER_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_SERVER_PORT", "8001")),
)


def _in_thread(fn, *args, **kwargs):
    """Django's ORM is synchronous: run it in a worker thread and keep DB connections tidy."""
    def inner():
        close_old_connections()
        try:
            return fn(*args, **kwargs)
        finally:
            close_old_connections()

    return sync_to_async(inner, thread_sensitive=True)()


@mcp.tool()
async def resolve_brand(brand: str, strength: str | None = None) -> dict:
    """Resolve a locally used brand name (or generic/alias) to ONE generic drug. Never guesses: ambiguous or
    fuzzy-only input comes back as status 'unresolved' with candidates/suggestions for a human to confirm."""
    return await _in_thread(services.resolve_brand, brand, strength)


@mcp.tool()
async def lookup_drug(generic_name: str) -> dict:
    """Basic record for a drug: aliases, formulation variants, and which sources mention it."""
    return await _in_thread(services.lookup_drug, generic_name)


@mcp.tool()
async def check_interaction(drug_a: str, drug_b: str) -> dict:
    """Interaction record for a drug pair. 'no_record' means no evidence found — NOT that the pair is safe.
    Severity 'unknown' means a record exists with no severity — also NOT safe."""
    return await _in_thread(services.check_interaction, drug_a, drug_b)


@mcp.tool()
async def check_interactions(drugs: list[str]) -> dict:
    """Check every pair in a medication list (2–12 names). Unresolved names are reported, never dropped."""
    return await _in_thread(services.check_interactions, drugs)


if __name__ == "__main__":
    mcp.run(transport=os.environ.get("MCP_TRANSPORT", "sse"))