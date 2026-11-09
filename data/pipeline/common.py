"""Shared helpers for the data pipeline (ingest → parse → clean → store → analytics).

Run the scripts with the backend virtualenv active:  python data/pipeline/<script>.py
Raw/processed files live under data/raw and data/processed (git-ignored).
"""
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
SEED_FILE = Path(__file__).with_name("seed_drugs.txt")

LICENSE_OPENFDA = "CC0 1.0 (openFDA label data). Not validated for medical-care decisions."


def load_env() -> None:
    """Load KEY=VALUE pairs from the repo-root .env into os.environ (without overriding real env vars)."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def django_setup() -> None:
    """Configure Django so scripts can use the ORM. Call once from a script's main()."""
    load_env()
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    os.environ.setdefault("DJANGO_LOCMEM_CACHE", "1")  # pipeline never needs Redis
    import django

    django.setup()


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def read_seed(path: Path = SEED_FILE) -> list[dict]:
    """Parse seed_drugs.txt -> [{"name": "acetaminophen", "aliases": ["paracetamol"]}, ...]."""
    drugs = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, _, alias_part = line.partition("|")
        aliases = [a.strip().lower() for a in alias_part.split(",") if a.strip()]
        drugs.append({"name": name.strip().lower(), "aliases": aliases})
    return drugs


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]