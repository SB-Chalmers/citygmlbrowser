"""Ökobaudat REST API client.

Ökobaudat is the German Federal Ministry EPD database.
EPD IDs are UUIDs like "8be9edb5-c5b9-4be1-bfb8-b096f24a183b".

API reference: https://github.com/ocni-dtu/okobau_example
OpenAPI docs:  https://oekobaudat.de/api

Data is fetched live on demand and cached in-process.  If you need offline
use, call download_epd(uuid) once per EPD and store the JSON under
data/oekobaudat/<uuid>.json — get_gwp() will prefer the local file.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path

# ── Ökobaudat API ──────────────────────────────────────────────────────────────

_BASE_URL = "https://oekobaudat.de/OEKOBAU.DAT/resource"

# Optional local cache directory (relative to repo root)
_LOCAL_CACHE = Path(__file__).parent.parent.parent / "data" / "oekobaudat"

# ILCD indicator UUIDs for Global Warming Potential
# AR4: 93a60a56-a3c8-11da-a746-0800200b9a66
# AR5 GWP-GHG: 6a37f984-a4b3-458a-a20a-64418c145fa2
_GWP_INDICATOR_IDS: frozenset[str] = frozenset({
    "93a60a56-a3c8-11da-a746-0800200b9a66",
    "6a37f984-a4b3-458a-a20a-64418c145fa2",
})

# Module code normalisations (Ökobaudat uses various spellings)
_A1A3_CODES: frozenset[str] = frozenset({"A1-3", "A1A2A3", "A1-A3", "A1,A2,A3"})
_A4_CODES:   frozenset[str] = frozenset({"A4"})
_A51_CODES:  frozenset[str] = frozenset({"A5", "A5.1"})


# ── Fetch / cache ──────────────────────────────────────────────────────────────

def _local_path(uuid: str) -> Path:
    return _LOCAL_CACHE / f"{uuid}.json"


def download_epd(uuid: str, overwrite: bool = False) -> Path:
    """Download a single EPD from Ökobaudat and save to the local cache.

    Returns the path to the saved file.
    """
    dest = _local_path(uuid)
    if dest.exists() and not overwrite:
        return dest
    _LOCAL_CACHE.mkdir(parents=True, exist_ok=True)
    url = f"{_BASE_URL}/processes/{uuid}?format=json&view=extended"
    with urllib.request.urlopen(url, timeout=20) as resp:
        data = json.load(resp)
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


@lru_cache(maxsize=256)
def _fetch(uuid: str) -> dict | None:
    """Return the extended EPD JSON for *uuid*, from cache or API."""
    local = _local_path(uuid)
    if local.exists():
        return json.loads(local.read_text(encoding="utf-8"))
    try:
        url = f"{_BASE_URL}/processes/{uuid}?format=json&view=extended"
        with urllib.request.urlopen(url, timeout=20) as resp:
            return json.load(resp)
    except Exception:
        return None


# ── GWP extraction ─────────────────────────────────────────────────────────────

def _is_gwp_indicator(result: dict) -> bool:
    """Return True if this LCIA result is the total GWP/Climate change indicator."""
    ref = result.get("referenceToLCIAMethodDataSet", {})

    # Try UUID match first (older stocks populate @refObjectId)
    uid = ref.get("@refObjectId", "")
    if uid in _GWP_INDICATOR_IDS:
        return True

    # Fall back to name match across all language entries.
    # EN 15804:A1 (Sphera):  "Climate change"
    # EN 15804:A2 (various): "Global Warming Potential - total (GWP-total)"
    #                         "Global warming potential except emissions and uptake of biogenic carbon"
    # Exclude sub-categories: biogenic, fossil, luluc, land use
    _EXCLUDE = {"biogenic", "fossil", "luluc", "land use", "land-use"}
    desc = ref.get("shortDescription", [])
    if isinstance(desc, dict):
        desc = [desc]
    for d in desc:
        name = d.get("value", "").strip().lower()
        if not name:
            continue
        if name == "climate change":
            return True
        if "gwp-total" in name:
            return True
        if "global warming potential - total" in name:
            return True
        # Catch "global warming potential except biogenic..." patterns
        if ("global warming" in name and
                not any(ex in name for ex in _EXCLUDE)):
            return True
    return False


def _extract_gwp(data: dict) -> dict:
    """Parse ILCD-format extended EPD JSON and return GWP dict."""
    gwp: dict[str, object] = {
        "A1-A3": None, "A4": None, "A5.1": None,
        "WasteFactor": None,
        "name": (data.get("processInformation", {})
                     .get("dataSetInformation", {})
                     .get("name", {})
                     .get("baseName", [{}])[0]
                     .get("value", "")),
    }

    lcia_results = (data.get("LCIAResults") or {}).get("LCIAResult", [])
    if isinstance(lcia_results, dict):
        lcia_results = [lcia_results]

    for result in lcia_results:
        if not _is_gwp_indicator(result):
            continue

        anies = (result.get("other") or {}).get("anies", [])
        if isinstance(anies, dict):
            anies = [anies]

        for amount in anies:
            module = str(amount.get("module", "")).strip()
            # Ökobaudat uses "value" key (not "$" as in some ILCD variants)
            raw = amount.get("value") or amount.get("$")
            if raw is None or module == "":
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if module in _A1A3_CODES:
                gwp["A1-A3"] = value
            elif module in _A4_CODES:
                gwp["A4"] = value
            elif module in _A51_CODES:
                gwp["A5.1"] = value
        break  # only parse the first matching indicator

    return gwp


# ── Public API ─────────────────────────────────────────────────────────────────

def get_gwp(uuid: str) -> dict | None:
    """Return GWP data for an Ökobaudat EPD UUID.

    Parameters
    ----------
    uuid : str
        EPD UUID, e.g. ``"8be9edb5-c5b9-4be1-bfb8-b096f24a183b"``.

    Returns
    -------
    dict | None
        ``{"A1-A3": float|None, "A4": float|None, "A5.1": float|None,
           "WasteFactor": None, "name": str}``
        or ``None`` if the UUID cannot be fetched.

    Notes
    -----
    WasteFactor is always None for Ökobaudat — the database does not
    include construction-waste factors.  Apply a default (1.0) or a
    project-specific value externally.
    """
    data = _fetch(uuid)
    if data is None:
        return None
    return _extract_gwp(data)


def _catalog_path() -> Path:
    return _LOCAL_CACHE / "catalog.json"


def build_catalog(force: bool = False) -> Path:
    """Download the full Ökobaudat process list and save to a local catalog.

    Fetches the full list twice — once in German (default) and once in English
    — and merges both names into each entry so ``search_epds()`` can match
    either language.

    Parameters
    ----------
    force : bool
        Re-download even if the catalog already exists (default False).

    Returns
    -------
    Path
        Path to the saved catalog file.
    """
    dest = _catalog_path()
    if dest.exists() and not force:
        return dest

    _LOCAL_CACHE.mkdir(parents=True, exist_ok=True)
    page_size = 500

    def _fetch_all(lang: str | None = None) -> dict[str, dict]:
        """Return {uuid: entry} for all entries in the given language."""
        index: dict[str, dict] = {}
        start = 0
        while True:
            params = f"format=json&pageSize={page_size}&startIndex={start}"
            if lang:
                params += f"&lang={lang}"
            url = f"{_BASE_URL}/processes?{params}"
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = json.load(resp)
            entries = data.get("data", [])
            total   = data.get("totalCount", 0)
            for e in entries:
                uuid = e.get("uuid")
                if uuid:
                    index[uuid] = e
            start += len(entries)
            if not entries or start >= total:
                break
        return index

    # Two passes: German names (default) + English names (lang=en)
    de_index = _fetch_all(lang=None)
    en_index = _fetch_all(lang="en")

    # Merge: German entry is base; add name_en from English pass where available
    merged: list[dict] = []
    for uuid, entry in de_index.items():
        e = dict(entry)
        en_entry = en_index.get(uuid, {})
        e["name_en"] = en_entry.get("name") or ""   # English name (empty if unavailable)
        # "name" stays as German (or best available if DE entry lacks it)
        if not e.get("name") and en_entry.get("name"):
            e["name"] = en_entry["name"]
        merged.append(e)

    dest.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
    return dest


@lru_cache(maxsize=1)
def _load_catalog() -> list[dict]:
    """Load the local catalog, building it on first call if absent."""
    p = _catalog_path()
    if not p.exists():
        build_catalog()
    return json.loads(p.read_text(encoding="utf-8"))


def search_epds(query: str, limit: int = 20) -> list[dict]:
    """Search Ökobaudat EPDs by keyword (client-side, uses local catalog cache).

    On first call the catalog is downloaded from Ökobaudat (~70 HTTP requests,
    saves to ``data/oekobaudat/catalog.json``).  All subsequent calls are
    instant.  Re-run ``build_catalog(force=True)`` to refresh.

    Matches against the EPD name **and** the classification/category path.
    Ökobaudat EPD names are predominantly German; try German terms (e.g.
    ``"Wärmepumpe"``) for the best coverage alongside English equivalents.

    Parameters
    ----------
    query : str
        Case-insensitive substring; works on both EPD name and category path.
    limit : int
        Maximum number of results to return (default 20).

    Returns
    -------
    list[dict]
        Each item has ``{"uuid": str, "name": str, "category": str,
        "owner": str, "refYear": int}``.

    Examples
    --------
    >>> from scripts.databases.oekobaudat import search_epds
    >>> for r in search_epds("Wärmepumpe", limit=5):
    ...     print(r["uuid"], r["name"])
    >>> for r in search_epds("Heizung", limit=5):   # by category
    ...     print(r["uuid"], r["name"])
    """
    catalog = _load_catalog()
    q = query.lower()
    results = []

    for e in catalog:
        name_de = str(e.get("name", ""))
        name_en = str(e.get("name_en", ""))
        cat      = str(e.get("classific", ""))

        if (q not in name_de.lower() and
                q not in name_en.lower() and
                q not in cat.lower()):
            continue

        # Display the English name when available, fall back to German
        display_name = name_en.strip() if name_en.strip() else name_de.strip()

        results.append({
            "uuid":     e.get("uuid", ""),
            "name":     display_name,
            "name_de":  name_de.strip(),
            "category": cat,
            "owner":    e.get("owner", ""),
            "refYear":  e.get("refYear"),
        })
        if len(results) >= limit:
            break

    return results


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    def _usage():
        print("Usage:")
        print("  python -m scripts.databases.oekobaudat build-catalog [--force]")
        print("  python -m scripts.databases.oekobaudat search <query> [limit]")
        print("  python -m scripts.databases.oekobaudat gwp <uuid>")
        print()
        print("Examples:")
        print("  python -m scripts.databases.oekobaudat build-catalog")
        print("  python -m scripts.databases.oekobaudat search 'heat pump' 10")
        print("  python -m scripts.databases.oekobaudat gwp 1cd6b257-a4f8-4509-a83b-492cd34c7d98")
        raise SystemExit(1)

    args = sys.argv[1:]
    if not args:
        _usage()

    cmd = args[0].lower()

    if cmd in ("build-catalog", "build_catalog"):
        force = "--force" in args
        print(f"Building Ökobaudat catalog (force={force}) …")
        p = build_catalog(force=force)
        import os
        size_kb = os.path.getsize(p) // 1024
        entries = len(json.loads(p.read_text()))
        print(f"  Saved {entries} entries to {p}  ({size_kb} KB)")

    elif cmd == "search":
        if len(args) < 2:
            _usage()
        q = args[1]
        n = int(args[2]) if len(args) > 2 else 20
        print(f"\nSearching Ökobaudat for: {q!r}  (max {n} results)\n")
        hits = search_epds(q, limit=n)
        if not hits:
            print("  No results found. Try a German term (e.g. 'Wärmepumpe', 'Heizung').")
        else:
            for h in hits:
                print(f"  {h['uuid']}  {h['name']}")
                print(f"    Category : {h['category']}")
                print(f"    Owner    : {h['owner']}  ({h['refYear']})")
                print()

    elif cmd == "gwp":
        if len(args) < 2:
            _usage()
        uuid = args[1]
        print(f"\nFetching GWP for: {uuid}\n")
        r = get_gwp(uuid)
        if r is None:
            print("  ERROR: UUID not found or fetch failed.")
        else:
            print(f"  Name   : {r['name']}")
            print(f"  A1-A3  : {r['A1-A3']} kgCO₂eq")
            print(f"  A4     : {r['A4']} kgCO₂eq")
            print(f"  A5.1   : {r['A5.1']} kgCO₂eq")

    else:
        _usage()
