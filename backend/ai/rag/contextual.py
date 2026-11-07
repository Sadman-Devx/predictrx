"""Contextual RAG: build a short prefix describing where a chunk comes from, embed prefix + text together.

TODO (lead): generate the prefix with the local/cloud model; the template below is the deterministic fallback.
"""


def context_prefix(*, drug_name: str, section: str, source: str) -> str:
    return f"Source: {source}. Drug: {drug_name}. Section: {section or 'general'}."
