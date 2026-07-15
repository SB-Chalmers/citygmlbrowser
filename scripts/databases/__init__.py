"""EPD database registry.

Each database module exposes a single function:

    get_gwp(resource_id: str) -> dict | None

The returned dict has keys:
    "A1-A3"      float | None   — GWP product stage  (kg CO₂eq / inventory unit)
    "A4"         float | None   — GWP transport to site
    "A5.1"       float | None   — GWP construction process
    "WasteFactor" float | None  — on-site waste multiplier (e.g. 1.05)

Returns None when the resource_id cannot be resolved.

Supported source names (used in lca:environmentalId/@source):
    "boverket"   — Boverket Klimatdatabas v2 (local JSON)
    "oekobaudat" — Ökobaudat REST API (German EPD platform, UUID-based)
"""

from __future__ import annotations

from . import boverket, oekobaudat

DATABASES: dict[str, object] = {
    "boverket":   boverket,
    "oekobaudat": oekobaudat,
}


def lookup_gwp(resource_id: str, source: str = "boverket") -> dict | None:
    """Dispatch a GWP lookup to the appropriate EPD database.

    Parameters
    ----------
    resource_id : str
        Database-specific identifier (integer string for Boverket, UUID for
        Ökobaudat).
    source : str
        One of the keys in DATABASES, or ``"placeholder"`` to skip.
        Defaults to "boverket" for backward compatibility with existing GML
        files that lack a source attribute.

    Returns
    -------
    dict | None
        GWP dict or None if not found / source is placeholder.
    """
    if source == "placeholder":
        return None
    db = DATABASES.get(source)
    if db is None:
        raise ValueError(f"Unknown EPD database source: {source!r}. "
                         f"Available: {list(DATABASES)} + 'placeholder'")
    return db.get_gwp(resource_id)
