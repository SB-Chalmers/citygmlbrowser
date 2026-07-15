"""Boverket Klimatdatabas v2 — local JSON lookup.

ResourceIds are large integers like 6000000029.
GWP values sit inside DataItems[n].DataValueItems, keyed by DataModuleCode.

The database JSON is expected at  data/boverket_klimatdatabas.json
relative to the repository root, downloaded via scripts/download_boverket.py.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# Resolve path relative to this file: scripts/databases/ → ../../data/
_DB_PATH = Path(__file__).parent.parent.parent / "data" / "boverket_klimatdatabas.json"


@lru_cache(maxsize=1)
def _load() -> dict[str, dict]:
    """Load and index the Boverket JSON by string ResourceId (lazy, cached)."""
    with _DB_PATH.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return {
        str(r["ResourceId"]): r
        for r in raw.get("Resources", [])
        if r.get("ResourceId")
    }


def get_gwp(resource_id: str) -> dict | None:
    """Return GWP data for a Boverket ResourceId.

    Parameters
    ----------
    resource_id : str
        Integer ResourceId as a string, e.g. ``"6000000029"``.

    Returns
    -------
    dict | None
        ``{"A1-A3": float|None, "A4": float|None, "A5.1": float|None,
           "WasteFactor": float|None, "name": str}``
        or ``None`` if the id is not in the database.
    """
    record = _load().get(str(resource_id))
    if record is None:
        return None

    gwp: dict[str, object] = {
        "A1-A3":       None,
        "A4":          None,
        "A5.1":        None,
        "WasteFactor": record.get("WasteFactor"),
        "name":        record.get("Name", ""),
    }

    for item in record.get("DataItems", []):
        if item.get("PropertyCode") != "GWP-GHG AR4":
            continue
        for dv in item.get("DataValueItems", []):
            code = dv.get("DataModuleCode", "")
            val  = dv.get("Value")
            if val is None:
                continue
            try:
                val = float(val)
            except (ValueError, TypeError):
                continue
            if code == "A1-A3 Typical":
                gwp["A1-A3"] = val
            elif code == "A1-A3 Conservative" and gwp["A1-A3"] is None:
                # fall back to conservative only if typical absent
                gwp["A1-A3"] = val
            elif code == "A4":
                gwp["A4"] = val
            elif code == "A5.1":
                gwp["A5.1"] = val

    return gwp
