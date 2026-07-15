"""Shared namespace registry and low-level XML utilities.

All version-specific parsers import from here; nothing in this module
is schema-version-specific.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

# ── Namespace registry ────────────────────────────────────────────────────────
NS: dict[str, str] = {
    # GML
    "gml":    "http://www.opengis.net/gml",        # GML 3.1 (CityGML 2.0)
    "gml32":  "http://www.opengis.net/gml/3.2",    # GML 3.2 (CityGML 3.0)
    "xlink":  "http://www.w3.org/1999/xlink",
    # CityGML 2.0
    "core":   "http://www.opengis.net/citygml/2.0",
    "bldg":   "http://www.opengis.net/citygml/building/2.0",
    "gen":    "http://www.opengis.net/citygml/generics/2.0",
    "xAL":    "urn:oasis:names:tc:ciq:xsdschema:xAL:2.0",
    # CityGML 3.0
    "core3":  "http://www.opengis.net/citygml/3.0",
    "bldg3":  "http://www.opengis.net/citygml/building/3.0",
    "con":    "http://www.opengis.net/citygml/construction/3.0",
    "gen3":   "http://www.opengis.net/citygml/generics/3.0",
    # Energy ADE 2.0
    "energy": "http://www.sig3d.org/citygml/2.0/energy/2.0",
    # Energy ADE 3.0
    "nrg3":   "http://www.citygml.org/ade/energy/3.0",
}

# Reverse map used by short_tag()
_URI_TO_PREFIX: dict[str, str] = {v: k for k, v in NS.items()}
# Canonical prefixes for aliases
_URI_TO_PREFIX["http://www.opengis.net/citygml/generics/2.0"] = "gen"

# gml:id appears in two namespaces depending on GML version
_GML_ID_ATTRS = (
    "{http://www.opengis.net/gml}id",
    "{http://www.opengis.net/gml/3.2}id",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gml_id(el: ET.Element) -> str | None:
    """Return gml:id regardless of GML 3.1 vs 3.2 namespace."""
    for attr in _GML_ID_ATTRS:
        v = el.get(attr)
        if v:
            return v
    return None


def short_tag(tag: str) -> str:
    """Convert {uri}localname → prefix:localname."""
    if tag.startswith("{"):
        uri, local = tag[1:].split("}", 1)
        prefix = _URI_TO_PREFIX.get(uri, uri.split("/")[-1])
        return f"{prefix}:{local}"
    return tag


def elem_text(el: ET.Element) -> str | None:
    t = (el.text or "").strip()
    return t if t else None


def text_of(parent: ET.Element, path: str) -> str | None:
    el = parent.find(path, NS)
    return elem_text(el) if el is not None else None


def _name_el(el: ET.Element) -> ET.Element | None:
    return el.find("gml:name", NS) or el.find("gml32:name", NS)


def _desc_el(el: ET.Element) -> ET.Element | None:
    return el.find("gml:description", NS) or el.find("gml32:description", NS)


# ── Geometry ─────────────────────────────────────────────────────────────────

def parse_pos_list(text: str) -> list[list[float]]:
    nums = [float(n) for n in text.split()]
    return [nums[i:i + 3] for i in range(0, len(nums), 3)]


def parse_linear_ring(el: ET.Element) -> dict:
    ring: dict = {"id": _gml_id(el), "points": []}
    pos_list = el.find("gml:posList", NS) or el.find("gml32:posList", NS)
    if pos_list is not None and pos_list.text:
        ring["points"] = parse_pos_list(pos_list.text)
    else:
        for pos in list(el.findall("gml:pos", NS)) + list(el.findall("gml32:pos", NS)):
            if pos.text:
                ring["points"].append([float(n) for n in pos.text.split()])
    return ring


def parse_polygon(el: ET.Element) -> dict:
    poly: dict = {"id": _gml_id(el), "exterior": None, "interior": []}
    ext = (el.find("gml:exterior/gml:LinearRing", NS)
           or el.find("gml32:exterior/gml32:LinearRing", NS))
    if ext is not None:
        poly["exterior"] = parse_linear_ring(ext)
    for interior in (list(el.findall("gml:interior/gml:LinearRing", NS))
                     + list(el.findall("gml32:interior/gml32:LinearRing", NS))):
        poly["interior"].append(parse_linear_ring(interior))
    return poly


def collect_polygons(el: ET.Element) -> list[dict]:
    """Recursively collect all gml:Polygon elements (GML 3.1 and 3.2)."""
    polys: list[dict] = []
    for uri in ("http://www.opengis.net/gml", "http://www.opengis.net/gml/3.2"):
        for poly_el in el.iter(f"{{{uri}}}Polygon"):
            polys.append(parse_polygon(poly_el))
    return polys


def parse_envelope(el: ET.Element) -> dict | None:
    env = (el.find("gml:boundedBy/gml:Envelope", NS)
           or el.find("gml32:boundedBy/gml32:Envelope", NS))
    if env is None:
        return None
    lo = env.find("gml:lowerCorner", NS) or env.find("gml32:lowerCorner", NS)
    hi = env.find("gml:upperCorner", NS) or env.find("gml32:upperCorner", NS)
    return {
        "srs":   env.get("srsName"),
        "lower": lo.text.strip() if lo is not None and lo.text else None,
        "upper": hi.text.strip() if hi is not None and hi.text else None,
    }
