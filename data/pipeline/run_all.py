"""Run the whole openFDA pipeline in order: ingest -> parse -> clean -> load -> report.

  python data/pipeline/run_all.py --limit 10
  python data/pipeline/run_all.py --skip-ingest      # reuse files already in data/raw
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def run(script: str, *extra: str) -> None:
    print(f"\n>>> {script} {' '.join(extra)}")
    subprocess.run([sys.executable, str(HERE / script), *extra], check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", default="10")
    ap.add_argument("--delay", default="0.5")
    ap.add_argument("--skip-ingest", action="store_true")
    ap.add_argument("--with-ddinter", action="store_true",
                    help="also parse+load DDInter (files must already be registered with ingest_ddinter.py)")
    args = ap.parse_args()
    if not args.skip_ingest:
        run("ingest_openfda.py", "--limit", args.limit, "--delay", args.delay)
    run("parse_labels.py")
    run("clean.py")
    run("load.py")
    if args.with_ddinter:
        run("parse_interactions.py")
        run("load_ddinter.py")
    run("report.py")


if __name__ == "__main__":
    main()