"""download_boverket.py — Download the Boverket Klimatdatabas v2 to a local JSON file.

Usage:
    python scripts/download_boverket.py [output_path]

Defaults to data/boverket_klimatdatabas.json. Fetches all material resources
from the public Boverket API (EN 15804 GWP data + reference service lives) so
the LCA ADE environmentalId values can be resolved offline.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

BASE_URL = "https://api.boverket.se/klimatdatabas/api/Klimat/v2/GetAllResources"
DB_VERSION = "latest"
CULTURE = "en"
RESPONSE_TYPE = "json"
TIMEOUT = 60
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0

DEFAULT_OUTPUT = Path("data/boverket_klimatdatabas.json")


def fetch() -> dict:
    url = f"{BASE_URL}/{DB_VERSION}/{CULTURE}/{RESPONSE_TYPE}"
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[{attempt}/{MAX_RETRIES}] GET {url}")
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 — retry on any transient error
            last_exc = exc
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                print(f"  failed ({exc}); retrying in {wait:.1f}s")
                time.sleep(wait)
    raise SystemExit(f"All {MAX_RETRIES} attempts failed: {last_exc}")


def main(argv: list[str]) -> int:
    out_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUTPUT
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = fetch()
    resources = data.get("Resources", data) if isinstance(data, dict) else data
    count = len(resources) if isinstance(resources, list) else "unknown"

    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"Wrote {out_path} ({size_kb:.0f} KB, {count} resources).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
