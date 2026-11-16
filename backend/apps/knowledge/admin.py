from django.contrib import admin

from core.admin_base import BaseModelAdmin

from .models import Chunk, GraphEdge, KnowledgeDocument


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(BaseModelAdmin):
    list_display = ("id", "title", "source", "drug", "license_note", "fetched_at")
    list_filter = ("source",)
    search_fields = ("title", "drug__generic_name")
    list_select_related = ("drug",)
    raw_id_fields = ("drug",)


@admin.register(GraphEdge)
class GraphEdgeAdmin(BaseModelAdmin):
    list_display = ("id", "src_type", "src_id", "relation", "dst_type", "dst_id")
    list_filter = ("relation", "src_type", "dst_type")
    raw_id_fields = ("chunk",)
    show_full_result_count = False  # large table


@admin.register(Chunk)
class ChunkAdmin(BaseModelAdmin):
    list_display = ("id", "document", "section", "token_count")
    list_select_related = ("document",)
    search_fields = ("document__title", "section")
    raw_id_fields = ("document",)
    exclude = ("embedding",)
    show_full_result_count = False  # large table
