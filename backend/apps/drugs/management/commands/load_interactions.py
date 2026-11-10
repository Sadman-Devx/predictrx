from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.drugs import services

from ._reporting import print_stats

DEFAULT_PATH = Path(settings.REPO_ROOT) / "data" / "processed" / "ddinter_clean.jsonl"


class Command(BaseCommand):
    help = "Load drug-drug interactions (idempotent). --format ddinter-csv reads raw DDInter downloads."

    def add_arguments(self, parser):
        parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
        parser.add_argument("--format", choices=services.INPUT_FORMATS, default=None)
        parser.add_argument("--dry-run", action="store_true", help="validate and count, write nothing")

    def handle(self, *args, **opts):
        path: Path = opts["path"]
        fmt = opts["format"] or services.detect_format(path)
        if fmt == "csv":
            fmt = "ddinter-csv"
        try:
            stats = services.import_interactions(services.iter_rows(path, fmt), dry_run=opts["dry_run"])
        except FileNotFoundError as exc:
            raise CommandError(f"Input not found: {exc}. Run the pipeline first (data/pipeline/README.md).") from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        print_stats(self, stats, label="interactions")