"""Energy ADE 3.0 parser.

Schema reference: http://www.citygml.org/ade/energy/3.0
Namespace prefix: nrg3

Key schema differences from ADE 2.0:
- Construction  → LayeredConstruction (nrg3:)
- Layer path    → nrg3:layer/nrg3:Layer  (not layerComponent/LayerComponent)
- Material href → no leading '#' in xlink:href
- SolidMaterial → nrg3:thermalConductivity / nrg3:specificHeatCapacity
- ThermalBoundary → embedded building surface element with nrg3:bdgBdrySurf* props
- Volumes/Areas  → nrg3:QualifiedVolume / nrg3:QualifiedArea
- Global objects → inside nrg3:*Library containers in cityObjectMember
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .base import NS, _gml_id, elem_text, text_of, short_tag

_XLINK = "{http://www.w3.org/1999/xlink}href"


# ── Materials ─────────────────────────────────────────────────────────────────

def parse_solid_material(el: ET.Element | None) -> dict | None:
    if el is None:
        return None
    return {
        "id":           _gml_id(el),
        "name":         text_of(el, "gml:name"),
        # ADE 3.0 renames conductivity and specificHeat
        "conductivity": text_of(el, "nrg3:thermalConductivity"),
        "density":      text_of(el, "nrg3:density"),
        "specificHeat": text_of(el, "nrg3:specificHeatCapacity"),
    }


def parse_gas(el: ET.Element | None) -> dict | None:
    if el is None:
        return None
    return {
        "id":          _gml_id(el),
        "name":        text_of(el, "gml:name"),
        "isVentilated": text_of(el, "nrg3:isVentilated"),
        "rValue":      text_of(el, "nrg3:rValue"),
    }


def _parse_layer(el: ET.Element) -> dict:
    mat_el   = el.find("nrg3:material", NS)
    material = mat_el.get(_XLINK) if mat_el is not None else None
    return {
        "thickness": text_of(el, "nrg3:thickness"),
        # ADE 3.0 material xlink:href has NO leading '#'
        "material":  material,
    }


def parse_layered_construction(el: ET.Element) -> dict:
    return {
        "id":     _gml_id(el),
        "name":   text_of(el, "gml:name"),
        "uValue": text_of(el, "nrg3:uValue"),
        "layers": [
            _parse_layer(layer_el)
            for layer_el in el.findall("nrg3:layer/nrg3:Layer", NS)
        ],
    }


def _parse_wrapped_opening(el: ET.Element) -> dict:
    """Parse a Window/Door element wrapped by a thermal boundary."""
    c_ref = el.find("nrg3:layeredConstruction", NS)
    if c_ref is None:
        c_ref = el.find("energy:construction/energy:Construction", NS)
    name_el = el.find("gml:name", NS) or el.find("gml32:name", NS)
    return {
        "id":           _gml_id(el),
        "name":         elem_text(name_el) if name_el is not None else None,
        "area":         text_of(el, "nrg3:bdgOpnArea") or text_of(el, "energy:area"),
        "uValue":       text_of(el, "nrg3:bdgOpnUValue") or text_of(el, "energy:uValue"),
        "glazingRatio": text_of(el, "nrg3:bdgOpnGlazingRatio") or text_of(el, "energy:glazingRatio"),
        "construction": c_ref.get(_XLINK) if c_ref is not None else None,
    }


# ── Thermal boundaries ────────────────────────────────────────────────────────

def parse_thermal_boundary(surf_el: ET.Element) -> dict:
    """Parse a building surface element used as a thermal boundary.

    In ADE 3.0 the nrg3:thermalBoundary property wraps a regular bldg/con
    surface element (e.g. bldg:GroundSurface).  Energy attributes are carried
    as nrg3:bdgBdrySurf* child elements on that surface element.
    """
    name_el = surf_el.find("gml:name", NS) or surf_el.find("gml32:name", NS)
    c_ref   = surf_el.find("nrg3:layeredConstruction", NS)
    return {
        "id":          _gml_id(surf_el),
        "type":        short_tag(surf_el.tag),
        "name":        elem_text(name_el) if name_el is not None else None,
        "azimuth":     text_of(surf_el, "nrg3:bdgBdrySurfAzimuth"),
        "inclination": text_of(surf_el, "nrg3:bdgBdrySurfInclination"),
        "area":        text_of(surf_el, "nrg3:bdgBdrySurfTotalSurfaceArea"),
        # construction href keeps its '#' prefix as in ADE 2.0
        "construction":    c_ref.get(_XLINK) if c_ref is not None else None,
        "thermalOpenings": [
            _parse_wrapped_opening(opening_el)
            for opening_prop in list(surf_el.findall("bldg:opening", NS)) + list(surf_el.findall("con:filling", NS))
            for opening_el in opening_prop
        ],
        "surfaceGeometry": None,
    }


# ── Zones ─────────────────────────────────────────────────────────────────────

def parse_thermal_zone(el: ET.Element) -> dict:
    tz: dict = {
        "id":                _gml_id(el),
        "isHeated":          text_of(el, "nrg3:isHeated"),
        "isCooled":          text_of(el, "nrg3:isCooled"),
        "volumes":           [],
        "floorAreas":        [],
        "thermalBoundaries": [],
        "usageZones":        [],
        "usageZoneRefs":     [],
    }
    for vol_el in el.findall("nrg3:volume/nrg3:QualifiedVolume", NS):
        tz["volumes"].append({
            "type":  text_of(vol_el, "nrg3:type"),
            "value": text_of(vol_el, "nrg3:value"),
        })
    for area_el in el.findall("nrg3:area/nrg3:QualifiedArea", NS):
        tz["floorAreas"].append({
            "type":  text_of(area_el, "nrg3:type"),
            "value": text_of(area_el, "nrg3:value"),
        })
    # nrg3:thermalBoundary wraps a building surface element directly
    for tb_prop in el.findall("nrg3:thermalBoundary", NS):
        for surf_el in tb_prop:
            tz["thermalBoundaries"].append(parse_thermal_boundary(surf_el))
    for uz_el in el.findall("nrg3:usageZone", NS):
        href = uz_el.get(_XLINK)
        if href:
            tz["usageZoneRefs"].append(href.lstrip("#"))
    return tz


def parse_usage_zone(el: ET.Element) -> dict:
    uz: dict = {
        "id":                       _gml_id(el),
        "type":                     text_of(el, "nrg3:usageZoneClass") or text_of(el, "nrg3:usageZoneType"),
        "isHeated":                 text_of(el, "nrg3:isHeated"),
        "isCooled":                 text_of(el, "nrg3:isCooled"),
        "isVentilated":             None,
        "isMechanicallyVentilated": None,
        "floorAreas":               [],
        "occupancySchedules":       [],
        "heatingSchedule":          None,
        "coolingSchedule":          None,
        "ventilationSchedule":      None,
        "electricalAppliances":     [],
    }
    for area_el in el.findall("nrg3:area/nrg3:QualifiedArea", NS):
        uz["floorAreas"].append({
            "type":  text_of(area_el, "nrg3:type"),
            "value": text_of(area_el, "nrg3:value"),
        })
    for tag, key in (
        ("nrg3:heatingSchedule",     "heatingSchedule"),
        ("nrg3:coolingSchedule",     "coolingSchedule"),
        ("nrg3:ventilationSchedule", "ventilationSchedule"),
    ):
        s_el = el.find(tag, NS)
        if s_el is not None:
            href = s_el.get(_XLINK)
            if href:
                uz[key] = {"scheduleType": "xlink:ref", "name": href.lstrip("#")}
    return uz


# ── Building enrichment ───────────────────────────────────────────────────────

def enrich_building(el: ET.Element, building: dict) -> None:
    """Add Energy ADE 3.0 thermal data in-place to a building dict."""
    for tz_el in el.findall("nrg3:thermalZone/nrg3:ThermalZone", NS):
        building["energy"]["thermalZones"].append(parse_thermal_zone(tz_el))
    for uz_el in el.findall("nrg3:usageZone/nrg3:UsageZone", NS):
        building["energy"]["usageZones"].append(parse_usage_zone(uz_el))
    for area_el in el.findall("nrg3:bdgFloorArea/nrg3:QualifiedArea", NS):
        building["energy"]["floorAreas"].append({
            "type":  text_of(area_el, "nrg3:type"),
            "value": text_of(area_el, "nrg3:value"),
        })


# ── Global object collector ───────────────────────────────────────────────────

def collect_global_objects(root: ET.Element) -> dict:
    """Return a {gml_id: parsed_object} dict for top-level ADE 3.0 objects.

    ADE 3.0 places constructions and materials inside library container objects
    (nrg3:LayeredConstructionLibrary, nrg3:MaterialLibrary) which are themselves
    inside core:cityObjectMember elements.
    """
    result: dict = {}

    def _ingest(child: ET.Element) -> None:
        gml_id = _gml_id(child)
        local  = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if local == "LayeredConstruction":
            obj = parse_layered_construction(child)
            obj["_class"] = "Construction"
            if gml_id:
                result[gml_id] = obj

        elif local == "SolidMaterial":
            obj = parse_solid_material(child) or {}
            obj["_class"] = "SolidMaterial"
            if gml_id:
                result[gml_id] = obj

        elif local == "Gas":
            obj = parse_gas(child) or {}
            obj["_class"] = "Gas"
            if gml_id:
                result[gml_id] = obj

        # Library containers — descend into their libraryMember children
        elif local in (
            "LayeredConstructionLibrary", "MaterialLibrary",
            "ConstructionLibrary", "GasLibrary", "SolidMaterialLibrary",
        ):
            for lib_member in child.findall("nrg3:libraryMember", NS):
                for grandchild in lib_member:
                    _ingest(grandchild)

    for wrapper in (
        "gml:featureMember", "gml32:featureMember",
        "core:cityObjectMember", "core3:cityObjectMember",
    ):
        for member in root.findall(wrapper, NS):
            for child in member:
                _ingest(child)

    return result
