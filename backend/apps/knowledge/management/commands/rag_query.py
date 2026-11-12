from django.core.management.base import BaseCommand, CommandError

from ai.rag.retriever import retrieve_for_pair


class Command(BaseCommand):
    help = (
        "Manual check of RAG retrieval for a drug pair: prints the chunk IDs (the future `evidence` entries), "
        "whether each passage really names both drugs, and how it was found (vector / graph)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--a", required=True, help="first drug (generic name or alias)")
        parser.add_argument("--b", required=True, help="second drug (generic name or alias)")
        parser.add_argument("-k", type=int, default=5)
        parser.add_argument("--full", action="store_true", help="print the whole passage, not a short preview")

    def handle(self, *args, **opts):
        result = retrieve_for_pair(opts["a"], opts["b"], k=opts["k"])
        self.stdout.write(f"pair: {opts['a']} + {opts['b']}   mode: {result.mode}   chunks: {len(result.chunks)}"
                          f"   citable (name both drugs): {len(result.evidence_chunks)}")
        for warning in result.warnings:
            self.stdout.write(self.style.WARNING(f"warning: {warning}"))
        if result.mode == "none" and not result.chunks:
            raise CommandError("No passages found. This is 'insufficient evidence', not 'safe'.")
        for c in result.chunks:
            dist = "-" if c.distance is None else f"{c.distance:.3f}"
            flag = "CITABLE" if c.supports_pair else "context"
            self.stdout.write(f"\n#{c.chunk_id}  [{flag}]  {c.drug} / {c.section or 'general'}  "
                              f"via={'+'.join(c.via)}  distance={dist}")
            self.stdout.write(f"  evidence: {c.as_evidence()}")
            self.stdout.write("  " + (c.text if opts["full"] else c.text[:240] + ("..." if len(c.text) > 240 else "")))