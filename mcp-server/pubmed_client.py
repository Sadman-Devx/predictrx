"""Restricted, general-topic client for the hosted PubMed MCP server."""
import json
import os
from typing import Literal

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ResearchTopic = Literal["drug_interactions", "medication_safety", "clinical_pharmacology"]

PUBMED_URL = "https://pubmed.caseyjhand.com/mcp"
TOPIC_QUERIES: dict[ResearchTopic, str] = {
    "drug_interactions": '"Drug Interactions"[MeSH Terms] AND systematic[sb]',
    "medication_safety": '"Medication Errors"[MeSH Terms] AND systematic[sb]',
    "clinical_pharmacology": '"Clinical Pharmacology"[MeSH Terms] AND systematic[sb]',
}


async def search_literature(topic: ResearchTopic) -> dict:
    """Search with a fixed general query; callers cannot pass patient or arbitrary text."""
    query = TOPIC_QUERIES[topic]
    async with streamablehttp_client(os.environ.get("PUBMED_MCP_URL", PUBMED_URL)) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "pubmed_search_articles",
                {"query": query, "maxResults": 5, "summaryCount": 5},
            )

    if getattr(result, "isError", False):
        raise RuntimeError("PubMed MCP search failed")
    data = getattr(result, "structuredContent", None)
    if not data:
        text = next(
            (item.text for item in (getattr(result, "content", None) or []) if getattr(item, "type", "") == "text"),
            None,
        )
        if text is None:
            raise RuntimeError("PubMed MCP returned no content")
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise RuntimeError("PubMed MCP returned non-JSON content") from exc
    if isinstance(data, dict) and set(data) == {"result"} and isinstance(data["result"], dict):
        data = data["result"]
    if not isinstance(data, dict):
        raise RuntimeError("PubMed MCP returned an unexpected response")
    return {"topic": topic, "query": query, "research_only": True, "results": data}
