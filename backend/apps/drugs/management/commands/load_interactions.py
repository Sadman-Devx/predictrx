import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

DEFAULT_DIR = Path(settings.REPO_ROOT) / "data" / "processed"
PIPELINE_LOADER = Path(settings.REPO_ROOT) / "data" / "pipeline" / "load_ddinter.py"


class Command(BaseCommand):
    help = "Load validated DDInter drug/interactions JSONL from the processed data directory."

    def add_arguments(self, parser):
        parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
        parser.add_argument("--replace", action="store_true", help="delete existing DDInter interactions before loading")
        parser.add_argument("--dry-run", action="store_true", help="validate processed files without writing")

    def handle(self, *args, **opts):
        path: Path = opts["dir"]
        for name in ("ddinter_drugs.jsonl", "ddinter_pairs.jsonl"):
            if not (path / name).is_file():
                raise CommandError(f"Input not found: {path / name}. Run data/pipeline/parse_interactions.py first.")
        command = [sys.executable, str(PIPELINE_LOADER), "--dir", str(path)]
        if opts["replace"]:
            command.append("--replace")
        if opts["dry_run"]:
            command.append("--dry-run")
        result = subprocess.run(command, cwd=settings.REPO_ROOT, capture_output=True, text=True, check=False)
        if result.stdout:
            self.stdout.write(result.stdout, ending="")
        if result.returncode:
            raise CommandError(result.stderr.strip() or f"DDInter loader exited with status {result.returncode}")