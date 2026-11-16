from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.drugs.importers import parse_brand_rows, save_brand_rows


class Command(BaseCommand):
    help = ("Load a curated brand->generic CSV. Every row needs source, source_ref, source_accessed and confidence; "
            "only Django admin review can set verified=True.")

    def add_arguments(self, parser):
        parser.add_argument("--path", type=Path, required=True)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--skip-bad", action="store_true")

    def handle(self, *args, **opts):
        try:
            parsed = parse_brand_rows(opts["path"])
        except FileNotFoundError as exc:
            raise CommandError(f"Input not found: {exc}") from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        for line, brand, message in parsed["errors"]:
            self.stdout.write(f"  line {line} ({brand or '?'}): {message}")
        if parsed["errors"] and not opts["skip_bad"]:
            raise CommandError(f"{len(parsed['errors'])} invalid rows. Nothing was loaded.")
        if opts["dry_run"]:
            self.stdout.write(f"DRY RUN: {len(parsed['ok'])} valid rows; nothing written.")
            return
        stats = save_brand_rows(parsed)
        self.stdout.write(f"brand mappings: created={stats['created']} updated={stats['updated']} "
                          f"rejected={len(parsed['errors'])}")