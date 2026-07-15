"""Parser package — auto-dispatching entry point.

Dialect detection routes each file to the correct version-specific parser.
Energy ADE enrichment is composed on top of the base CityGML parser.
"""

from __future__ import annotations

from pathlib import Path

from api.dialect import detect_dialect, DialectInfo

from .base import NS  # re-export for graph.py / legacy callers
from . import citygml_20, citygml_30
from . import energy_ade_20, energy_ade_30

__all__ = [
    "parse_file",
    "NS",
    "citygml_20",
    "citygml_30",
    "energy_ade_20",
    "energy_ade_30",
]


def _make_energy_enricher(dialect: DialectInfo):
    """Return the correct enrich_building callable (or None) for the dialect."""
    if dialect.energy_ade == "3.0":
        return energy_ade_30.enrich_building
    if dialect.energy_ade == "2.0":
        return energy_ade_20.enrich_building
    return None


def parse_file(path: str, *, force_citygml: str | None = None) -> dict:
    """Parse a CityGML file, auto-detecting version unless *force_citygml* is set.

    Args:
        path: Absolute or relative path to the GML/XML file.
        force_citygml: ``"2.0"`` or ``"3.0"`` to bypass auto-detection.

    Returns:
        A model dict with keys: file, id, bbox, buildings.
    """
    dialect       = detect_dialect(path)
    enrich        = _make_energy_enricher(dialect)
    citygml_ver   = force_citygml or dialect.citygml

    if citygml_ver == "3.0":
        return citygml_30.parse_file(path, enrich_energy=enrich)

    # Default: CityGML 2.0 (also handles files with no detected version)
    return citygml_20.parse_file(path, enrich_energy=enrich)
