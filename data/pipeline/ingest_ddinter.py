"""Stage 1 — INGEST (DDInter): register the downloaded DDInter CSV files in data/raw/ddinter/.

We do NOT scrape the DDInter website. Download the files yourself from the site's official download page,
then point this script at the folder. It copies the files, checks the header, and writes manifest.json
(which version, when, checksums) so SOURCES.md can be filled truthfully.

Run:  python data/pipeline/ingest_ddinter.py --from "C:/Users/me/Downloads" --version "<version shown on the site>"
"""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from common import RAW_DIR

EXPECTED_HEADER = ["DDInterID_A", "Drug_A", "DDInterID_B", "Drug_B", "Level"]
PATTERN = "ddinter_downloads_code_*.csv"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="src", type=Path, required=True, help="folder containing the downloaded CSV files")
    ap.add_argument("--version", required=True,
                    help="DDInter version/label you downloaded from (e.g. '1.0' or '2.0'); recorded in manifest.json")
    ap.add_argument("--source-url", default="", help="page you downloaded from (for the record)")
    args = ap.parse_args()

    files = sorted(args.src.glob(PATTERN))
    if not files:
        raise SystemExit(f"No files matching {PATTERN} in {args.src}")

    dest = RAW_DIR / "ddinter"
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {"version": args.version, "source_url": args.source_url,
                "registered_at": datetime.now(timezone.utc).isoformat(), "files": []}
    for f in files:
        header = f.read_text(encoding="utf-8").splitlines()[0].split(",")
        if header != EXPECTED_HEADER:
            raise SystemExit(f"{f.name}: unexpected header {header}; expected {EXPECTED_HEADER}")
        target = dest / f.name
        shutil.copy2(f, target)
        data = target.read_bytes()
        manifest["files"].append({"name": f.name, "sha256": hashlib.sha256(data).hexdigest(),
                                  "rows": data.count(b"\n") - 1})
        print(f"  registered {f.name}: {manifest['files'][-1]['rows']} rows")
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"done: {len(files)} files -> {dest}  (version recorded: {args.version!r})")
    print("Now record the version, date and licence check in data/SOURCES.md. Do NOT commit these files.")


if __name__ == "__main__":
    main()