from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.drugs import services

from ._reporting import print_stats


class Command(BaseCommand):
    help = ("Load the curated brand->generic sheet (CSV). Columns: brand_name, strength, dosage_form, "
            "generic_name, source, confidence. Every row is stored with verified=False.")

    def add_arguments(self, parser):
        parser.add_argument("--path", type=Path, required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        try:
            stats = services.import_brand_mappings(services.iter_rows(opts["path"], "csv"), dry_run=opts["dry_run"])
        except FileNotFoundError as exc:
            raise CommandError(f"Input not found: {exc}") from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        print_stats(self, stats, label="brand mappings")