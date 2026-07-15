"""CityGML 3.0 building parser.

Schema reference:
  http://www.opengis.net/citygml/building/3.0
  http://www.opengis.net/citygml/construction/3.0
  http://www.opengis.net/citygml/3.0

Key schema differences from CityGML 2.0
────────────────────────────────────────
• GML namespace is gml/3.2 instead of gml
• Building boundary surfaces replaced by:
    bldg:buildingSubdivision → bldg:Storey
      → bldg:buildingConstructiveElement → bldg:BuildingConstructiveElement
  BuildingConstructiveElement (BCE) carries:
    - bldg:class  ("Wall", "Slab", "Roof", …)
    - core3:lod2Solid / core3:lod3Solid  (solid geometry)
    - con:filling → con:Window / con:Door  (openings)
• Building-level BCEs also allowed directly without a Storey wrapper
• con:height replaces bldg:measuredHeight
• Address uses xAL version 3 (urn:oasis:names:tc:ciq:xal:3)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Callable

from .base import (
    NS, _gml_id, elem_text, text_of,
    parse_envelope, collect_polygons, short_tag,
    _name_el, _desc_el,
)

_XLINK = "{http://www.w3.org/1999/xlink}href"


# ── Openings (con:Window / con:Door) ─────────────────────────────────────────

def parse_opening(el: ET.Element) -> dict:
    """Parse a con:Window or con:Door element."""
    name_el = _name_el(el)
    return {
        "type":     short_tag(el.tag),
        "id":       _gml_id(el),
        "name":     elem_text(name_el) if name_el is not None else None,
        "polygons": collect_polygons(el),
    }


# ── BuildingConstructiveElement ───────────────────────────────────────────────

_LOD_SOLID_TAGS = ("core3:lod2Solid", "core3:lod3Solid", "core3:lod1Solid")


def parse_constructive_element(el: ET.Element) -> dict:
    """Parse a bldg:BuildingConstructiveElement.

    Schema: AbstractConstructiveElement (con module) extended by
    AbstractBuildingSubdivision (bldg module).
    """
    name_el = _name_el(el)
    bce: dict = {
        "id":                 _gml_id(el),
        "name":               elem_text(name_el) if name_el is not None else None,
        "class":              text_of(el, "bldg3:class"),
        "isStructuralElement": text_of(el, "con:isStructuralElement"),
        "polygons":           [],
        "openings":           [],
    }
    # Solid geometry — collect all polygons from the first present LoD
    for lod_tag in _LOD_SOLID_TAGS:
        lod_el = el.find(lod_tag, NS)
        if lod_el is not None:
            bce["polygons"] = collect_polygons(lod_el)
            break
    # Openings: con:filling → con:Window / con:Door
    for filling in el.findall("con:filling", NS):
        for child in filling:
            bce["openings"].append(parse_opening(child))
    return bce


# ── Storey ────────────────────────────────────────────────────────────────────

def parse_storey(el: ET.Element) -> dict:
    """Parse a bldg:Storey element."""
    name_el = _name_el(el)
    storey: dict = {
        "id":                  _gml_id(el),
        "name":                elem_text(name_el) if name_el is not None else None,
        "class":               text_of(el, "bldg3:class"),
        "constructiveElements": [],
    }
    for bce_prop in el.findall("bldg3:buildingConstructiveElement", NS):
        for bce_el in bce_prop.findall("bldg3:BuildingConstructiveElement", NS):
            storey["constructiveElements"].append(parse_constructive_element(bce_el))
    return storey


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
        "surfaces":          [],          # empty for pure CityGML 3.0
        "storeys":           [],
        "constructiveElements": [],       # building-level BCEs (no Storey wrapper)
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
    building["id"]   = _gml_id(el)
    building["bbox"] = parse_envelope(el)

    n = _name_el(el)
    if n is not None:
        building["name"] = elem_text(n)
    d = _desc_el(el)
    if d is not None:
        building["description"] = elem_text(d)

    # Scalar attributes — both bldg3: and the unchanged bldg: paths (files vary)
    for attr, paths in (
        ("function",           ("bldg3:function",           "bldg:function")),
        ("yearOfConstruction", ("bldg3:yearOfConstruction", "bldg:yearOfConstruction")),
        ("roofType",           ("bldg3:roofType",           "bldg:roofType")),
        ("storeysAboveGround", ("bldg3:storeysAboveGround", "bldg:storeysAboveGround")),
        ("storeysBelowGround", ("bldg3:storeysBelowGround", "bldg:storeysBelowGround")),
        ("creationDate",       ("core3:creationDate",       "core:creationDate")),
        ("class",              ("bldg3:class",              "bldg:class")),
        ("usage",              ("bldg3:usage",              "bldg:usage")),
    ):
        for path in paths:
            found = el.find(path, NS)
            if found is not None and found.text:
                building["attributes"][attr] = found.text.strip()
                break

    # con:height replaces bldg:measuredHeight in 3.0
    for h_el in el.findall("con:height/con:Height", NS):
        val = text_of(h_el, "con:value")
        ref = text_of(h_el, "con:highReference")
        if val:
            key = f"height_{ref}" if ref else "height"
            building["attributes"][key] = val

    # Storeys
    for sub_el in el.findall("bldg3:buildingSubdivision", NS):
        for storey_el in sub_el.findall("bldg3:Storey", NS):
            building["storeys"].append(parse_storey(storey_el))

    # Building-level constructive elements (no Storey wrapper)
    for bce_prop in el.findall("bldg3:buildingConstructiveElement", NS):
        for bce_el in bce_prop.findall("bldg3:BuildingConstructiveElement", NS):
            building["constructiveElements"].append(parse_constructive_element(bce_el))

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
    for member in root.findall("core3:cityObjectMember", NS):
        # In CityGML 3.0 files, bldg: prefix resolves to building/3.0
        for tag in ("bldg3:Building", "bldg:Building"):
            bldg_el = member.find(tag, NS)
            if bldg_el is not None:
                model["buildings"].append(parse_building(bldg_el, enrich_energy))
                break
    # GML featureMember fallback
    for member in root.findall("gml32:featureMember", NS):
        for tag in ("bldg3:Building", "bldg:Building"):
            bldg_el = member.find(tag, NS)
            if bldg_el is not None:
                model["buildings"].append(parse_building(bldg_el, enrich_energy))
                break
    return model
