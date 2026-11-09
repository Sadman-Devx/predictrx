"""Stage 1 — INGEST: download drug labels from openFDA for the drugs in seed_drugs.txt.

Output: data/raw/openfda/<drug>.json  (git-ignored)
Uses the free API key from .env (OPENFDA_API_KEY) if present. Respect openFDA's rate limits (see
https://open.fda.gov/apis/authentication); the --delay flag spaces requests out.

Run:  python data/pipeline/ingest_openfda.py --limit 10
"""
import argparse
import json
import os
import time
from datetime import datetime, timezone

import httpx

from common import RAW_DIR, load_env, read_seed, slugify

API_URL = "https://api.fda.gov/drug/label.json"


def fetch(client: httpx.Client, name: str, limit: int, api_key: str | None) -> dict | None:
    params = {"search": f'openfda.generic_name:"{name}"', "limit": limit}
    if api_key:
        params["api_key"] = api_key
    for attempt in range(5):
        r = client.get(API_URL, params=params, timeout=30)
        if r.status_code == 404:  # openFDA answers 404 when nothing matches
            return None
        if r.status_code == 429:  # rate limited -> back off
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"openFDA kept rate-limiting the request for {name!r}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=10, help="labels per drug (many are combinations; clean.py filters)")
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between requests")
    ap.add_argument("--force", action="store_true", help="re-download files that already exist")
    ap.add_argument("--only", help="only this generic name")
    args = ap.parse_args()

    load_env()
    api_key = os.environ.get("OPENFDA_API_KEY") or None
    if not api_key:
        print("WARNING: no OPENFDA_API_KEY in .env — using the lower anonymous limits.")

    out_dir = RAW_DIR / "openfda"
    out_dir.mkdir(parents=True, exist_ok=True)
    seed = [d for d in read_seed() if not args.only or d["name"] == args.only.lower()]

    ok = missing = skipped = 0
    with httpx.Client() as client:
        for drug in seed:
            target = out_dir / f"{slugify(drug['name'])}.json"
            if target.exists() and not args.force:
                skipped += 1
                continue
            data = fetch(client, drug["name"], args.limit, api_key)
            if data is None:
                print(f"  no labels found: {drug['name']}")
                missing += 1
            else:
                payload = {
                    "query_name": drug["name"],
                    "aliases": drug["aliases"],
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "meta": data.get("meta", {}),
                    "results": data.get("results", []),
                }
                target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                print(f"  saved {drug['name']}: {len(payload['results'])} labels")
                ok += 1
            time.sleep(args.delay)
    print(f"done: saved={ok} no_match={missing} skipped_existing={skipped}")


if __name__ == "__main__":
    main()