"""PredictRx custom MCP server (SSE transport).

Tools (deterministic, backed by the database in the real implementation):
  resolve_brand(brand, strength?)  -> generic name + confidence + verified flag, or {"status": "unresolved"}
  lookup_drug(generic_name)        -> basic record + source list, or {"status": "not_found"}
  check_interaction(drug_a, drug_b)-> severity/mechanism/management/source, or {"status": "no_record"}

The Verifier agent calls the SAME tools, so a finding can be checked independently of the LLM's wording.

Run (SSE):   python server.py
Run (stdio): MCP_TRANSPORT=stdio python server.py

TODO (lead dev): replace the in-memory SAMPLE_* data with queries against the Django tables
(drugs.BrandMapping, drugs.Interaction). Keep the response shapes below unchanged.
"""
import os

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "predictrx-drug-tools",
    host=os.environ.get("MCP_SERVER_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_SERVER_PORT", "8001")),
)

# ---- Placeholder data so the tools are callable on day 1. NOT clinical data. Replace with DB queries. ----
SAMPLE_BRANDS = {"napa": {"generic": "paracetamol", "confidence": 0.99, "verified": False,
                          "source": "placeholder-sample"}}
SAMPLE_INTERACTIONS: dict[frozenset, dict] = {}


def _norm(s: str) -> str:
    return s.strip().lower()


@mcp.tool()
def resolve_brand(brand: str, strength: str | None = None) -> dict:
    """Resolve a locally used brand name to a generic drug name. Never guesses: returns 'unresolved' if unknown."""
    hit = SAMPLE_BRANDS.get(_norm(brand).split()[0] if brand.strip() else "")
    if not hit:
        return {"status": "unresolved", "input": brand}
    return {"status": "resolved", "input": brand, **hit}


@mcp.tool()
def lookup_drug(generic_name: str) -> dict:
    """Basic record for a generic drug name, with the sources that mention it."""
    # TODO: query drugs.Drug + knowledge.KnowledgeDocument
    return {"status": "not_found", "input": generic_name}


@mcp.tool()
def check_interaction(drug_a: str, drug_b: str) -> dict:
    """Interaction record for a drug pair. 'no_record' means no evidence found — NOT that the pair is safe."""
    rec = SAMPLE_INTERACTIONS.get(frozenset({_norm(drug_a), _norm(drug_b)}))
    if not rec:
        return {"status": "no_record", "drug_a": drug_a, "drug_b": drug_b,
                "note": "No interaction record found. This does not mean the combination is safe."}
    return {"status": "found", **rec}


if __name__ == "__main__":
    mcp.run(transport=os.environ.get("MCP_TRANSPORT", "sse"))
