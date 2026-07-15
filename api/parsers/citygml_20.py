"""CityGML 2.0 building parser.

Schema reference:
  http://www.opengis.net/citygml/building/2.0
  http://www.opengis.net/citygml/2.0

Parsed elements
───────────────
Building
  → boundedBy → WallSurface / RoofSurface / GroundSurface /
                ClosureSurface / InteriorWallSurface /
                CeilingSurface / FloorSurface /
                OuterCeilingSurface / OuterFloorSurface
      → lod[2-4]MultiSurface → gml:Polygon geometry
      → opening → Window / Door
  → address → core:Address → xAL
  → generics (gen:stringAttribute / gen:measureAttribute)
  → energy enrichment delegated to a caller-supplied callback
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

from .base import (
    NS, _gml_id, elem_text, text_of,
    parse_envelope, collect_polygons, short_tag,
    _name_el, _desc_el,
)


# ── Address ───────────────────────────────────────────────────────────────────

def parse_address(el: ET.Element) -> dict:
    addr: dict = {}
    xal = el.find(".//xAL:AddressDetails", NS)
    if xal is None:
        return addr
    for path, key in [
        ("xAL:Locality/xAL:LocalityName",                                  "city"),
        ("xAL:Locality/xAL:PostalCode/xAL:PostalCodeNumber",               "postcode"),
        ("xAL:Locality/xAL:Thoroughfare/xAL:ThoroughfareName",             "street"),
        ("xAL:Locality/xAL:Thoroughfare/xAL:ThoroughfareNumber",           "number"),
    ]:
        found = xal.find(path, NS)
        if found is not None and found.text:
            addr[key] = found.text.strip()
    return addr


# ── Generic attributes ────────────────────────────────────────────────────────

def parse_generic_attrs(el: ET.Element) -> dict:
    attrs: dict = {}
    for prefix in ("gen", "gen"):
        for attr_el in el.findall(f"{prefix}:stringAttribute", NS):
            name  = attr_el.get("name")
            val_el = attr_el.find(f"{prefix}:value", NS)
            if name and val_el is not None:
                attrs[name] = elem_text(val_el)
        for attr_el in el.findall(f"{prefix}:measureAttribute", NS):
            name  = attr_el.get("name")
            val_el = attr_el.find(f"{prefix}:value", NS)
            if name and val_el is not None:
                attrs[name] = {"value": elem_text(val_el), "uom": val_el.get("uom")}
    return attrs


# ── Openings ──────────────────────────────────────────────────────────────────

def parse_opening(el: ET.Element) -> dict:
    """Parse a bldg:Window or bldg:Door element."""
    name_el = el.find("gml:name", NS)
    return {
        "type":     short_tag(el.tag),
        "id":       _gml_id(el),
        "name":     elem_text(name_el) if name_el is not None else None,
        "polygons": collect_polygons(el),
    }


# ── Boundary surfaces ─────────────────────────────────────────────────────────

_LOD_TAGS = (
    "bldg:lod2MultiSurface",
    "bldg:lod3MultiSurface",
    "bldg:lod4MultiSurface",
)

_SURFACE_TYPES = (
    "bldg:WallSurface",
    "bldg:RoofSurface",
    "bldg:GroundSurface",
    "bldg:ClosureSurface",
    "bldg:InteriorWallSurface",
    "bldg:CeilingSurface",
    "bldg:FloorSurface",
    "bldg:OuterCeilingSurface",
    "bldg:OuterFloorSurface",
)


def parse_surface(el: ET.Element) -> dict:
    name_el = el.find("gml:name", NS)
    surface: dict = {
        "type":     short_tag(el.tag),
        "id":       _gml_id(el),
        "name":     elem_text(name_el) if name_el is not None else None,
        "bbox":     parse_envelope(el),
        "polygons": [],
        "openings": [],
    }
    for lod_tag in _LOD_TAGS:
        lod_el = el.find(lod_tag, NS)
        if lod_el is not None:
            surface["polygons"] = collect_polygons(lod_el)
            break
    for op_prop in el.findall("bldg:opening", NS):
        for child in op_prop:
            surface["openings"].append(parse_opening(child))
    return surface


# ── Building ──────────────────────────────────────────────────────────────────

def _empty_building() -> dict:
    return {
        "id":                None,
        "name":              None,
        "description":       None,
        "bbox":              None,
        "attributes":        {},
        "generic_attributes": {},
        "address":           None,
        "surfaces":          [],
        # CityGML 3.0 additions kept for structural consistency
        "storeys":           [],
        "constructiveElements": [],
        "energy": {
            "thermalZones": [],
            "usageZones":   [],
            "floorAreas":   [],
        },
    }


def parse_building(
    el: ET.Element,
    enrich_energy: Callable[[ET.Element, dict], None] | None = None,
) -> dict:
    building = _empty_building()
    building["id"]          = _gml_id(el)
    building["bbox"]        = parse_envelope(el)
    building["generic_attributes"] = parse_generic_attrs(el)

    n = _name_el(el)
    if n is not None:
        building["name"] = elem_text(n)
    d = _desc_el(el)
    if d is not None:
        building["description"] = elem_text(d)

    # Scalar attributes defined in the building/2.0 schema
    for attr, path in (
        ("function",           "bldg:function"),
        ("yearOfConstruction", "bldg:yearOfConstruction"),
        ("roofType",           "bldg:roofType"),
        ("measuredHeight",     "bldg:measuredHeight"),
        ("storeysAboveGround", "bldg:storeysAboveGround"),
        ("storeysBelowGround", "bldg:storeysBelowGround"),
        ("creationDate",       "core:creationDate"),
        ("relativeToTerrain",  "core:relativeToTerrain"),
        ("class",              "bldg:class"),
        ("usage",              "bldg:usage"),
    ):
        found = el.find(path, NS)
        if found is not None and found.text:
            building["attributes"][attr] = found.text.strip()

    addr_el = el.find("bldg:address/core:Address", NS)
    if addr_el is not None:
        building["address"] = parse_address(addr_el)

    for bounded_by in el.findall("bldg:boundedBy", NS):
        for surf_type in _SURFACE_TYPES:
            surf_el = bounded_by.find(surf_type, NS)
            if surf_el is not None:
                building["surfaces"].append(parse_surface(surf_el))

    if enrich_energy is not None:
        enrich_energy(el, building)

    return building


# ── File entry point ──────────────────────────────────────────────────────────

def parse_file(
    path: str,
    enrich_energy: Callable[[ET.Element, dict], None] | None = None,
) -> dict:
    root = ET.parse(path).getroot()
    model: dict = {
        "file":      str(path),
        "id":        _gml_id(root),
        "bbox":      parse_envelope(root),
        "buildings": [],
    }
    for member in root.findall("core:cityObjectMember", NS):
        bldg_el = member.find("bldg:Building", NS)
        if bldg_el is not None:
            model["buildings"].append(parse_building(bldg_el, enrich_energy))
    # Some files use gml:featureMember at the top level
    for member in root.findall("gml:featureMember", NS):
        bldg_el = member.find("bldg:Building", NS)
        if bldg_el is not None:
            model["buildings"].append(parse_building(bldg_el, enrich_energy))
    return model
