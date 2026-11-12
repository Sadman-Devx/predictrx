from django.core.management.base import BaseCommand, CommandError

from ai.rag import graph, indexer
from ai.rag.contextual import VALID_MODES
from ai.rag.embeddings import EmbeddingError


class Command(BaseCommand):
    help = (
        "Index the knowledge base for RAG: contextual prefix + embedding for every chunk that has none yet, "
        "then rebuild the graph edges. Safe to re-run (idempotent). Needs Ollama and EMBEDDING_MODEL for the "
        "embedding step."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None, help="embed at most N chunks this run")
        parser.add_argument("--batch-size", type=int, default=indexer.DEFAULT_BATCH)
        parser.add_argument("--reembed", action="store_true",
                            help="re-embed ALL chunks (after changing the embedding model, prefix mode or chunking)")
        parser.add_argument("--drug", default=None, help="only chunks of this drug's labels (generic name)")
        parser.add_argument("--context-mode", choices=VALID_MODES, default=None,
                            help="prefix mode (default: RAG_CONTEXT_MODE from settings)")
        parser.add_argument("--skip-embeddings", action="store_true", help="only rebuild the graph edges")
        parser.add_argument("--skip-graph", action="store_true", help="only embed chunks")

    def handle(self, *args, **opts):
        if opts["skip_embeddings"] and opts["skip_graph"]:
            raise CommandError("Nothing to do: both --skip-embeddings and --skip-graph were given.")

        if not opts["skip_embeddings"]:
            self.stdout.write("Embedding chunks ...")
            try:
                stats = indexer.index_pending(
                    batch_size=opts["batch_size"], limit=opts["limit"], reembed=opts["reembed"],
                    drug=opts["drug"], context_mode=opts["context_mode"],
                    progress=lambda s: self.stdout.write(f"  embedded {s.chunks_embedded}/{s.pending_before}"),
                )
            except EmbeddingError as exc:
                raise CommandError(
                    f"{exc}\nChecks: is Ollama running (docker compose up -d), is EMBEDDING_MODEL set and pulled, "
                    f"does its output size equal EMBEDDING_DIM?"
                ) from exc
            self.stdout.write(self.style.SUCCESS(
                f"embeddings: {stats.chunks_embedded} chunks embedded "
                f"({stats.prefixes_generated} prefixes written, {stats.pending_before} were pending)"
            ))

        if not opts["skip_graph"]:
            self.stdout.write("Building graph edges ...")
            g = graph.rebuild_edges()
            self.stdout.write(self.style.SUCCESS(
                f"graph: {g['documents']} documents, {g['chunks']} chunks -> {g['mention_edges']} mention edges, "
                f"{g['pair_edges']} drug-pair edges ({g['known_names']} drug names known)"
            ))