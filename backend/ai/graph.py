"""LangGraph pipeline: Resolver -> Clinical Notes -> Drug Interaction -> Advisory -> Verifier.

The nodes are stubs that keep the contract (state shape + trace entries). The lead dev fills in the logic.
Persisting `trace` to AgentTrace rows and `findings` to RiskFinding rows is done by the Celery task (analysis app).
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
