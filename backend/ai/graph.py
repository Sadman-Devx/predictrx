"""LangGraph pipeline: Resolver -> Clinical Notes -> Drug Interaction -> Advisory -> Verifier.

Each node is a plain function `run(state) -> partial state` in `ai/agents/`:

    resolver          groups medications by drug, cross-checks `resolve_brand` (MCP), turns unresolved items into gaps
    clinical_notes    lab flags from the clinician-entered ranges, optional local-model condition phrases
    drug_interaction  `check_interaction` (MCP) + RAG label passages -> findings with evidence references
    advisory          doctor summary (EN/BN) and Bangla patient card, written from the findings only
    verifier          re-checks every finding and enforces the output guardrail (Day 7; still a stub today)

State rules:
  * every node returns only the keys it changes; `trace` is merged with `operator.add`, so each node appends
    its own AgentTrace-shaped entry and nothing is overwritten;
  * the graph is strictly linear (no loops, no conditional edges); the runner also sets a hard recursion limit;
  * the graph never touches the database for results: `apps/analysis/runner.py` persists `findings` to
    RiskFinding rows, `trace` to AgentTrace rows and `summaries` to RiskSummary, after its own safety checks.
"""
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from .agents import advisory, clinical_notes, drug_interaction, resolver, verifier


class PipelineState(TypedDict, total=False):
    medications: list
    patient_context: dict
    resolved_drugs: list
    gaps: list
    retrieved_chunks: list
    findings: list
    summaries: dict
    violations: list
    trace: Annotated[list, operator.add]  # every node appends its trace entry


def build_graph():
    g = StateGraph(PipelineState)
    g.add_node("resolver", resolver.run)
    g.add_node("clinical_notes", clinical_notes.run)
    g.add_node("drug_interaction", drug_interaction.run)
    g.add_node("advisory", advisory.run)
    g.add_node("verifier", verifier.run)
    g.add_edge(START, "resolver")
    g.add_edge("resolver", "clinical_notes")
    g.add_edge("clinical_notes", "drug_interaction")
    g.add_edge("drug_interaction", "advisory")
    g.add_edge("advisory", "verifier")
    g.add_edge("verifier", END)
    return g.compile()