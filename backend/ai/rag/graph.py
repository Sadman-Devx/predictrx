"""Graph RAG helper: expand from a drug pair to connected chunks via GraphEdge. TODO (lead)."""
from apps.knowledge.models import GraphEdge


def neighbors(src_type: str, src_id: int, relation: str | None = None):
    qs = GraphEdge.objects.filter(src_type=src_type, src_id=src_id)
    return qs.filter(relation=relation) if relation else qs
