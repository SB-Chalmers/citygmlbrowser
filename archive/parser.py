"""CityGML 2.0 (incl. Energy ADE) parser.

Self-contained parsing logic for the CityGML Browser API. Produces a
hierarchical Python dict model from a CityGML file. No CLI or I/O side effects.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

# ── Namespace map ────────────────────────────────────────────────────────────
NS = {
    # CityGML 2.0
    "core":   "http://www.opengis.net/citygml/2.0",
    "bldg":   "http://www.opengis.net/citygml/building/2.0",
    "gml":    "http://www.opengis.net/gml",
    "energy": "http://www.sig3d.org/citygml/2.0/energy/2.0",
    "gen":    "http://www.opengis.net/citygml/generics/2.0",
    "genobj": "http://www.opengis.net/citygml/generics/2.0",
    "xAL":    "urn:oasis:names:tc:ciq:xsdschema:xAL:2.0",
    "xlink":  "http://www.w3.org/1999/xlink",
    # Energy ADE 3.0
    "nrg3":   "http://www.citygml.org/ade/energy/3.0",
    # CityGML 3.0
    "core3":  "http://www.opengis.net/citygml/3.0",
    "bldg3":  "http://www.opengis.net/citygml/building/3.0",
    "con":    "http://www.opengis.net/citygml/construction/3.0",
    "gml32":  "http://www.opengis.net/gml/3.2",
    "gen3":   "http://www.opengis.net/citygml/generics/3.0",
}

GML_ID_ATTRS = [
    "{http://www.opengis.net/gml}id",
    "{http://www.opengis.net/gml/3.2}id",
]


def _gml_id(el: ET.Element) -> str | None:
    """Return the gml:id attribute regardless of GML namespace version."""
    for attr in GML_ID_ATTRS:
        v = el.get(attr)
        if v:
            return v
    return None


# Reverse map: full URI → prefix
URI_TO_PREFIX = {v: k for k, v in NS.items()}
# dedupe genobj → gen
URI_TO_PREFIX["http://www.opengis.net/citygml/generics/2.0"] = "gen"


def short_tag(tag: str) -> str:
    """Convert {uri}localname → prefix:localname."""
    if tag.startswith("{"):
        uri, local = tag[1:].split("}", 1)
        prefix = URI_TO_PREFIX.get(uri, uri.split("/")[-1])
        return f"{prefix}:{local}"
    return tag


def parse_pos_list(text: str) -> list[list[float]]:
    """Parse a gml:posList (flat list of floats) into [[x,y,z], ...]."""
    nums = [float(n) for n in text.split()]
    return [nums[i:i + 3] for i in range(0, len(nums), 3)]


def elem_text(el: ET.Element) -> str | None:
    t = (el.text or "").strip()
    return t if t else None


# ── Core extraction ───────────────────────────────────────────────────────────

def parse_linear_ring(el: ET.Element) -> dict:
    ring = {"id": _gml_id(el), "points": []}
    pos_list = el.find("gml:posList", NS)
    if pos_list is not None and pos_list.text:
        ring["points"] = parse_pos_list(pos_list.text)
    else:
        # fallback: individual gml:pos elements
        for pos in el.findall("gml:pos", NS):
            if pos.text:
                ring["points"].append([float(n) for n in pos.text.split()])
    return ring


def parse_polygon(el: ET.Element) -> dict:
    poly = {"id": _gml_id(el), "exterior": None, "interior": []}
    ext = el.find("gml:exterior/gml:LinearRing", NS)
    if ext is not None:
        poly["exterior"] = parse_linear_ring(ext)
    for interior in el.findall("gml:interior/gml:LinearRing", NS):
        poly["interior"].append(parse_linear_ring(interior))
    return poly


def collect_polygons(el: ET.Element) -> list[dict]:
    """Recursively find all gml:Polygon elements under el (GML 3.1 and 3.2)."""
    polys = []
    for uri in ("http://www.opengis.net/gml", "http://www.opengis.net/gml/3.2"):
        for poly_el in el.iter(f"{{{uri}}}Polygon"):
            polys.append(parse_polygon(poly_el))
    return polys


def parse_envelope(el: ET.Element) -> dict | None:
    # Try GML 3.1 first, then GML 3.2
    env = el.find("gml:boundedBy/gml:Envelope", NS)
    if env is None:
        env = el.find("gml32:boundedBy/gml32:Envelope", NS)
    if env is None:
        return None
    lo = env.find("gml:lowerCorner", NS) or env.find("gml32:lowerCorner", NS)
    hi = env.find("gml:upperCorner", NS) or env.find("gml32:upperCorner", NS)
    return {
        "srs": env.get("srsName"),
        "lower": lo.text.strip() if lo is not None and lo.text else None,
        "upper": hi.text.strip() if hi is not None and hi.text else None,
    }


def parse_opening(el: ET.Element) -> dict:
    tag = short_tag(el.tag)  # e.g. bldg:Window / bldg:Door / con:Window / con:Door
    opening = {
        "type": tag,
        "id": _gml_id(el),
        "name": None,
        "polygons": [],
    }
    name_el = el.find("gml:name", NS)
    if name_el is not None:
        opening["name"] = elem_text(name_el)
    opening["polygons"] = collect_polygons(el)
    return opening


def parse_surface(el: ET.Element) -> dict:
    tag = short_tag(el.tag)
    surface = {
        "type": tag,
        "id": _gml_id(el),
        "name": None,
        "bbox": parse_envelope(el),
        "polygons": [],
        "openings": [],
    }
    name_el = el.find("gml:name", NS) or el.find("gml32:name", NS)
    if name_el is not None:
        surface["name"] = elem_text(name_el)

    # collect polygons from the lod geometry (CityGML 2.0 and 3.0 lod tags)
    for lod_tag in [
        "bldg:lod2MultiSurface", "bldg:lod3MultiSurface", "bldg:lod4MultiSurface",
        "con:lod2MultiSurface", "con:lod3MultiSurface",
    ]:
        lod_el = el.find(lod_tag, NS)
        if lod_el is not None:
            surface["polygons"] = collect_polygons(lod_el)
            break

    # openings: CityGML 2.0 (bldg:opening) and 3.0 (con:opening)
    for op_prop_tag in ("bldg:opening", "con:opening"):
        for op_prop in el.findall(op_prop_tag, NS):
            for child in op_prop:
                surface["openings"].append(parse_opening(child))

    return surface


def parse_address(el: ET.Element) -> dict:
    addr = {}
    xal = el.find(".//xAL:AddressDetails", NS)
    if xal is None:
        return addr
    for path, key in [
        ("xAL:Locality/xAL:LocalityName", "city"),
        ("xAL:Locality/xAL:PostalCode/xAL:PostalCodeNumber", "postcode"),
        ("xAL:Locality/xAL:Thoroughfare/xAL:ThoroughfareName", "street"),
        ("xAL:Locality/xAL:Thoroughfare/xAL:ThoroughfareNumber", "number"),
    ]:
        found = xal.find(path, NS)
        if found is not None and found.text:
            addr[key] = found.text.strip()
    return addr


def parse_generic_attrs(el: ET.Element) -> dict:
    attrs = {}
    for ns_prefix in ["gen", "genobj"]:
        for attr_el in el.findall(f"{ns_prefix}:stringAttribute", NS):
            name = attr_el.get("name")
            val_el = attr_el.find(f"{ns_prefix}:value", NS)
            if name and val_el is not None:
                attrs[name] = elem_text(val_el)
        for attr_el in el.findall(f"{ns_prefix}:measureAttribute", NS):
            name = attr_el.get("name")
            val_el = attr_el.find(f"{ns_prefix}:value", NS)
            if name and val_el is not None:
                attrs[name] = {"value": elem_text(val_el), "uom": val_el.get("uom")}
    return attrs


# ── Energy ADE ────────────────────────────────────────────────────────────────

def text_of(parent: ET.Element, path: str) -> str | None:
    el = parent.find(path, NS)
    return elem_text(el) if el is not None else None


def parse_layer_component(el: ET.Element) -> dict:
    mat_container = el.find("energy:material", NS)
    material = None
    if mat_container is not None:
        # xlink:href on the property element itself (e.g. <energy:material xlink:href="#id"/>)
        href = mat_container.get("{http://www.w3.org/1999/xlink}href")
        if href:
            material = href
        else:
            # Inline SolidMaterial or Gas child
            for mat_el in mat_container:
                if "SolidMaterial" in mat_el.tag or "Gas" in mat_el.tag:
                    material = _parse_solid_material(mat_el)
                    break
    return {
        "thickness": text_of(el, "energy:thickness"),
        "material": material,
    }


def _parse_solid_material(el: ET.Element | None) -> dict | None:
    if el is None:
        return None
    return {
        "id": _gml_id(el),
        "name": text_of(el, "gml:name"),
        "conductivity": text_of(el, "energy:conductivity"),
        "density": text_of(el, "energy:density"),
        "specificHeat": text_of(el, "energy:specificHeat"),
    }


def _parse_solid_material_nrg3(el: ET.Element | None) -> dict | None:
    if el is None:
        return None
    return {
        "id": _gml_id(el),
        "name": text_of(el, "gml:name"),
        "conductivity": text_of(el, "nrg3:thermalConductivity"),
        "density": text_of(el, "nrg3:density"),
        "specificHeat": text_of(el, "nrg3:specificHeatCapacity"),
    }


def _parse_gas_nrg3(el: ET.Element | None) -> dict | None:
    if el is None:
        return None
    return {
        "id": _gml_id(el),
        "name": text_of(el, "gml:name"),
        "isVentilated": text_of(el, "nrg3:isVentilated"),
        "rValue": text_of(el, "nrg3:rValue"),
    }


def parse_construction(el: ET.Element) -> dict:
    c = {
        "id": _gml_id(el),
        "name": text_of(el, "gml:name"),
        "uValue": text_of(el, "energy:uValue"),
        "layers": [],
    }
    for layer_el in el.findall("energy:layer/energy:Layer/energy:layerComponent/energy:LayerComponent", NS):
        c["layers"].append(parse_layer_component(layer_el))
    return c


def _parse_layer_nrg3(el: ET.Element) -> dict:
    mat_el = el.find("nrg3:material", NS)
    material: str | None = None
    if mat_el is not None:
        href = mat_el.get("{http://www.w3.org/1999/xlink}href")
        if href:
            # ADE 3.0 material hrefs do NOT have a leading '#'
            material = href
    return {
        "thickness": text_of(el, "nrg3:thickness"),
        "material": material,
    }


def parse_layered_construction(el: ET.Element) -> dict:
    c = {
        "id": _gml_id(el),
        "name": text_of(el, "gml:name"),
        "uValue": text_of(el, "nrg3:uValue"),
        "layers": [],
    }
    for layer_el in el.findall("nrg3:layer/nrg3:Layer", NS):
        c["layers"].append(_parse_layer_nrg3(layer_el))
    return c


def parse_optical_props(el: ET.Element | None) -> dict | None:
    if el is None:
        return None
    result = {}
    for t_el in el.findall("energy:transmittance/energy:Transmittance", NS):
        wl = text_of(t_el, "energy:wavelengthRange")
        frac = text_of(t_el, "energy:fraction")
        result[f"transmittance_{wl}"] = frac
    return result or None


def parse_thermal_opening(el: ET.Element) -> dict:
    return {
        "id": el.get("{http://www.opengis.net/gml}id"),
        "area": text_of(el, "energy:area"),
        "uValue": text_of(el, "energy:uValue"),
        "glazingRatio": text_of(el, "energy:glazingRatio"),
        "construction": _parse_construction_ref_or_inline(el),
        "opticalProperties": parse_optical_props(el.find("energy:opticalProperties/energy:OpticalProperties", NS)),
    }


def _parse_construction_ref_or_inline(el: ET.Element) -> str | dict | None:
    c_el = el.find("energy:construction/energy:Construction", NS)
    if c_el is not None:
        return parse_construction(c_el)
    c_ref = el.find("energy:construction", NS)
    if c_ref is not None:
        href = c_ref.get("{http://www.w3.org/1999/xlink}href")
        return href
    return None


def parse_thermal_boundary(el: ET.Element) -> dict:
    tb = {
        "id": _gml_id(el),
        "type": text_of(el, "energy:thermalBoundaryType"),
        "azimuth": text_of(el, "energy:azimuth"),
        "inclination": text_of(el, "energy:inclination"),
        "area": text_of(el, "energy:area"),
        "construction": _parse_construction_ref_or_inline(el),
        "thermalOpenings": [],
        "surfaceGeometry": None,
    }
    for to_el in el.findall("energy:contains/energy:ThermalOpening", NS):
        tb["thermalOpenings"].append(parse_thermal_opening(to_el))
    sg = el.find("energy:surfaceGeometry", NS)
    if sg is not None:
        tb["surfaceGeometry"] = {"href": sg.get("{http://www.w3.org/1999/xlink}href")}
    return tb


def parse_thermal_boundary_nrg3(surf_el: ET.Element) -> dict:
    """Parse a bldg/con surface element acting as a thermal boundary in ADE 3.0.

    In ADE 3.0, nrg3:thermalBoundary wraps a regular building surface element
    (e.g. bldg:WallSurface) which carries nrg3:bdgBdrySurf* properties.
    """
    tag = short_tag(surf_el.tag)
    tb = {
        "id": _gml_id(surf_el),
        "type": tag,
        "name": None,
        "azimuth": text_of(surf_el, "nrg3:bdgBdrySurfAzimuth"),
        "inclination": text_of(surf_el, "nrg3:bdgBdrySurfInclination"),
        "area": text_of(surf_el, "nrg3:bdgBdrySurfTotalSurfaceArea"),
        "construction": None,
        "thermalOpenings": [],
        "surfaceGeometry": None,
    }
    name_el = surf_el.find("gml:name", NS) or surf_el.find("gml32:name", NS)
    if name_el is not None:
        tb["name"] = elem_text(name_el)
    c_ref = surf_el.find("nrg3:layeredConstruction", NS)
    if c_ref is not None:
        href = c_ref.get("{http://www.w3.org/1999/xlink}href")
        tb["construction"] = href  # '#id_xxx' format
    return tb


def parse_schedule(el: ET.Element) -> dict | None:
    """Parse any schedule type (DailyPatternSchedule, RegularTimeSeries, etc.)."""
    if el is None:
        return None
    sched_el = next(iter(el), None)
    if sched_el is None:
        return None
    tag = short_tag(sched_el.tag)
    name_el = sched_el.find("gml:name", NS)
    result = {
        "scheduleType": tag,
        "name": name_el.text.strip() if name_el is not None and name_el.text else None,
    }
    # DailyPatternSchedule → periodOfYear → PeriodOfYear → dailySchedule → DailySchedule
    for pop_el in sched_el.findall("energy:periodOfYear/energy:PeriodOfYear", NS):
        for dp in pop_el.findall("energy:dailySchedule/energy:DailySchedule", NS):
            day_type = text_of(dp, "energy:dayType") or "typicalDay"
            sched_inner = dp.find("energy:schedule", NS)
            if sched_inner is not None:
                ts = sched_inner.find("energy:RegularTimeSeries", NS)
                if ts is not None:
                    vals_el = ts.find("energy:values", NS)
                    desc_el = ts.find(
                        "energy:variableProperties/energy:TimeValuesProperties/energy:thematicDescription", NS
                    )
                    result[f"schedule_{day_type}"] = {
                        "timeInterval": text_of(ts, "energy:timeInterval"),
                        "values": vals_el.text.strip() if vals_el is not None and vals_el.text else None,
                        "uom": vals_el.get("uom") if vals_el is not None else None,
                        "description": desc_el.text.strip() if desc_el is not None and desc_el.text else None,
                    }
    return result


def parse_usage_zone(el: ET.Element) -> dict:
    uz = {
        "id": _gml_id(el),
        "type": text_of(el, "energy:usageZoneType"),
        "isHeated": text_of(el, "energy:isHeated"),
        "isCooled": text_of(el, "energy:isCooled"),
        "isVentilated": text_of(el, "energy:isVentilated"),
        "isMechanicallyVentilated": text_of(el, "energy:isMechanicallyVentilated"),
        "floorAreas": [],
        "occupancySchedules": [],
        "heatingSchedule": parse_schedule(el.find("energy:heatingSchedule", NS)),
        "coolingSchedule": parse_schedule(el.find("energy:coolingSchedule", NS)),
        "ventilationSchedule": parse_schedule(el.find("energy:ventilationSchedule", NS)),
        "electricalAppliances": [],
    }
    for fa_el in el.findall("energy:floorArea/energy:FloorArea", NS):
        uz["floorAreas"].append({
            "type": text_of(fa_el, "energy:type"),
            "value": text_of(fa_el, "energy:value"),
        })
    for ea_el in el.findall("energy:equippedWith/energy:ElectricalAppliances", NS):
        hd_el = ea_el.find("energy:heatDissipation/energy:HeatExchangeType", NS)
        hd = None
        if hd_el is not None:
            hd = {
                "totalValue": text_of(hd_el, "energy:totalValue"),
                "convectiveFraction": text_of(hd_el, "energy:convectiveFraction"),
                "radiantFraction": text_of(hd_el, "energy:radiantFraction"),
            }
        uz["electricalAppliances"].append({
            "id": _gml_id(ea_el),
            "heatDissipation": hd,
            "operationSchedule": parse_schedule(ea_el.find("energy:operationSchedule", NS)),
        })
    return uz


def parse_usage_zone_nrg3(el: ET.Element) -> dict:
    uz = {
        "id": _gml_id(el),
        "type": text_of(el, "nrg3:usageZoneClass") or text_of(el, "nrg3:usageZoneType"),
        "isHeated": text_of(el, "nrg3:isHeated"),
        "isCooled": text_of(el, "nrg3:isCooled"),
        "isVentilated": None,
        "isMechanicallyVentilated": None,
        "floorAreas": [],
        "occupancySchedules": [],
        "heatingSchedule": None,
        "coolingSchedule": None,
        "ventilationSchedule": None,
        "electricalAppliances": [],
    }
    for area_el in el.findall("nrg3:area/nrg3:QualifiedArea", NS):
        uz["floorAreas"].append({
            "type": text_of(area_el, "nrg3:type"),
            "value": text_of(area_el, "nrg3:value"),
        })
    # Schedule references (xlink href to schedule objects)
    for sched_tag, key in [
        ("nrg3:heatingSchedule", "heatingSchedule"),
        ("nrg3:coolingSchedule", "coolingSchedule"),
        ("nrg3:ventilationSchedule", "ventilationSchedule"),
    ]:
        s_el = el.find(sched_tag, NS)
        if s_el is not None:
            href = s_el.get("{http://www.w3.org/1999/xlink}href")
            if href:
                uz[key] = {"scheduleType": "xlink:ref", "name": href.lstrip("#")}
    return uz


def parse_thermal_zone(el: ET.Element) -> dict:
    tz = {
        "id": _gml_id(el),
        "isHeated": text_of(el, "energy:isHeated"),
        "isCooled": text_of(el, "energy:isCooled"),
        "volumes": [],
        "floorAreas": [],
        "thermalBoundaries": [],
        "usageZones": [],
        "usageZoneRefs": [],
    }
    for vol_el in el.findall("energy:volume/energy:VolumeType", NS):
        tz["volumes"].append({
            "type": text_of(vol_el, "energy:type"),
            "value": text_of(vol_el, "energy:value"),
        })
    for fa_el in el.findall("energy:floorArea/energy:FloorArea", NS):
        tz["floorAreas"].append({
            "type": text_of(fa_el, "energy:type"),
            "value": text_of(fa_el, "energy:value"),
        })
    for tb_el in el.findall("energy:boundedBy/energy:ThermalBoundary", NS):
        tz["thermalBoundaries"].append(parse_thermal_boundary(tb_el))
    for c_el in el.findall("energy:contains", NS):
        href = c_el.get("{http://www.w3.org/1999/xlink}href")
        if href:
            tz["usageZoneRefs"].append(href.lstrip("#"))
    for uz_el in el.findall("energy:contains/energy:UsageZone", NS):
        tz["usageZones"].append(parse_usage_zone(uz_el))
    return tz


def parse_thermal_zone_nrg3(el: ET.Element) -> dict:
    tz = {
        "id": _gml_id(el),
        "isHeated": text_of(el, "nrg3:isHeated"),
        "isCooled": text_of(el, "nrg3:isCooled"),
        "volumes": [],
        "floorAreas": [],
        "thermalBoundaries": [],
        "usageZones": [],
        "usageZoneRefs": [],
    }
    for vol_el in el.findall("nrg3:volume/nrg3:QualifiedVolume", NS):
        tz["volumes"].append({
            "type": text_of(vol_el, "nrg3:type"),
            "value": text_of(vol_el, "nrg3:value"),
        })
    for area_el in el.findall("nrg3:area/nrg3:QualifiedArea", NS):
        tz["floorAreas"].append({
            "type": text_of(area_el, "nrg3:type"),
            "value": text_of(area_el, "nrg3:value"),
        })
    # In ADE 3.0, thermalBoundary wraps a building surface element
    for tb_prop in el.findall("nrg3:thermalBoundary", NS):
        for surf_el in tb_prop:
            tz["thermalBoundaries"].append(parse_thermal_boundary_nrg3(surf_el))
    for uz_el in el.findall("nrg3:usageZone", NS):
        href = uz_el.get("{http://www.w3.org/1999/xlink}href")
        if href:
            tz["usageZoneRefs"].append(href.lstrip("#"))
    return tz


def parse_building(el: ET.Element) -> dict:
    building = {
        "id": _gml_id(el),
        "name": None,
        "description": None,
        "bbox": parse_envelope(el),
        "attributes": {},
        "generic_attributes": parse_generic_attrs(el),
        "address": None,
        "surfaces": [],
        "energy": {
            "thermalZones": [],
            "usageZones": [],
            "floorAreas": [],
        },
    }

    name_el = el.find("gml:name", NS) or el.find("gml32:name", NS)
    if name_el is not None:
        building["name"] = elem_text(name_el)

    desc_el = el.find("gml:description", NS) or el.find("gml32:description", NS)
    if desc_el is not None:
        building["description"] = elem_text(desc_el)

    # Simple scalar attributes (CityGML 2.0 and 3.0 paths)
    for attr, paths in [
        ("function",             ["bldg:function",           "bldg3:function"]),
        ("yearOfConstruction",   ["bldg:yearOfConstruction", "bldg3:yearOfConstruction"]),
        ("roofType",             ["bldg:roofType",           "bldg3:roofType"]),
        ("measuredHeight",       ["bldg:measuredHeight",     "bldg3:measuredHeight"]),
        ("storeysAboveGround",   ["bldg:storeysAboveGround", "bldg3:storeysAboveGround"]),
        ("storeysBelowGround",   ["bldg:storeysBelowGround", "bldg3:storeysBelowGround"]),
        ("creationDate",         ["core:creationDate",       "core3:creationDate"]),
        ("relativeToTerrain",    ["core:relativeToTerrain",  "core3:relativeToTerrain"]),
        ("class",                ["bldg:class",              "bldg3:class"]),
        ("usage",                ["bldg:usage",              "bldg3:usage"]),
    ]:
        for path in paths:
            found = el.find(path, NS)
            if found is not None and found.text:
                building["attributes"][attr] = found.text.strip()
                break

    # Address (CityGML 2.0)
    addr_el = el.find("bldg:address/core:Address", NS)
    if addr_el is not None:
        building["address"] = parse_address(addr_el)

    # Boundary surfaces — CityGML 2.0: bldg:boundedBy
    SURFACE_TYPES_V2 = [
        "bldg:WallSurface", "bldg:RoofSurface", "bldg:GroundSurface",
        "bldg:ClosureSurface", "bldg:InteriorWallSurface",
        "bldg:CeilingSurface", "bldg:FloorSurface",
        "bldg:OuterCeilingSurface", "bldg:OuterFloorSurface",
    ]
    for bounded_by in el.findall("bldg:boundedBy", NS):
        for surf_type in SURFACE_TYPES_V2:
            surf_el = bounded_by.find(surf_type, NS)
            if surf_el is not None:
                building["surfaces"].append(parse_surface(surf_el))

    # Boundary surfaces — CityGML 3.0: bldg3:boundary / con:* surface types
    SURFACE_TYPES_V3 = [
        "con:WallSurface", "con:RoofSurface", "con:GroundSurface",
        "con:ClosureSurface", "con:InteriorWallSurface",
        "con:CeilingSurface", "con:FloorSurface",
        "con:OuterCeilingSurface", "con:OuterFloorSurface",
    ]
    for boundary in el.findall("bldg3:boundary", NS):
        for surf_type in SURFACE_TYPES_V3:
            surf_el = boundary.find(surf_type, NS)
            if surf_el is not None:
                building["surfaces"].append(parse_surface(surf_el))

    # Energy ADE 2.0
    for tz_el in el.findall("energy:thermalZone/energy:ThermalZone", NS):
        building["energy"]["thermalZones"].append(parse_thermal_zone(tz_el))
    for uz_el in el.findall("energy:usageZone/energy:UsageZone", NS):
        building["energy"]["usageZones"].append(parse_usage_zone(uz_el))
    for fa_el in el.findall("energy:floorArea/energy:FloorArea", NS):
        building["energy"]["floorAreas"].append({
            "type": text_of(fa_el, "energy:type"),
            "value": text_of(fa_el, "energy:value"),
        })

    # Energy ADE 3.0
    for tz_el in el.findall("nrg3:thermalZone/nrg3:ThermalZone", NS):
        building["energy"]["thermalZones"].append(parse_thermal_zone_nrg3(tz_el))
    for uz_el in el.findall("nrg3:usageZone/nrg3:UsageZone", NS):
        building["energy"]["usageZones"].append(parse_usage_zone_nrg3(uz_el))
    for area_el in el.findall("nrg3:bdgFloorArea/nrg3:QualifiedArea", NS):
        building["energy"]["floorAreas"].append({
            "type": text_of(area_el, "nrg3:type"),
            "value": text_of(area_el, "nrg3:value"),
        })

    return building


def parse_file(path: str) -> dict:
    tree = ET.parse(path)
    root = tree.getroot()

    model = {
        "file": str(path),
        "id": _gml_id(root),
        "bbox": parse_envelope(root),
        "buildings": [],
    }

    # CityGML 2.0: core:cityObjectMember
    for member in root.findall("core:cityObjectMember", NS):
        bldg_el = member.find("bldg:Building", NS)
        if bldg_el is not None:
            model["buildings"].append(parse_building(bldg_el))

    # CityGML 3.0: core3:cityObjectMember
    for member in root.findall("core3:cityObjectMember", NS):
        for bldg_tag in ("bldg3:Building", "bldg:Building"):
            bldg_el = member.find(bldg_tag, NS)
            if bldg_el is not None:
                model["buildings"].append(parse_building(bldg_el))
                break

    # GML featureMember (used by some files for both global objects and buildings)
    for member in root.findall("gml:featureMember", NS):
        bldg_el = member.find("bldg:Building", NS)
        if bldg_el is not None:
            model["buildings"].append(parse_building(bldg_el))
    for member in root.findall("gml32:featureMember", NS):
        for bldg_tag in ("bldg3:Building", "bldg:Building"):
            bldg_el = member.find(bldg_tag, NS)
            if bldg_el is not None:
                model["buildings"].append(parse_building(bldg_el))
                break

    return model
