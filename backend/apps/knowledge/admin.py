from django.contrib import admin

from .models import Chunk, GraphEdge, KnowledgeDocument

admin.site.register([KnowledgeDocument, GraphEdge])


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "section", "token_count")
    exclude = ("embedding",)
