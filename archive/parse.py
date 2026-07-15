#!/usr/bin/env python3
"""
CityGML Parser
Parses CityGML 2.0 files (including Energy ADE) and prints a human-readable tree.

Usage:
    python3 parse.py models/FZK-Haus-LoD3-KIT-IAI-KHH-B36-V1.gml
    python3 parse.py models/FZKHouseLoD3-ADE.gml --mode tree
    python3 parse.py models/FZKHouseLoD3-ADE.gml --mode json
    python3 parse.py models/FZKHouseLoD3-ADE.gml --mode summary
"""

import sys
import json
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

# ── Namespace map ────────────────────────────────────────────────────────────
NS = {
    "core":   "http://www.opengis.net/citygml/2.0",
    "bldg":   "http://www.opengis.net/citygml/building/2.0",
    "gml":    "http://www.opengis.net/gml",
    "energy": "http://www.sig3d.org/citygml/2.0/energy/2.0",
    "gen":    "http://www.opengis.net/citygml/generics/2.0",
    "genobj": "http://www.opengis.net/citygml/generics/2.0",
    "xAL":    "urn:oasis:names:tc:ciq:xsdschema:xAL:2.0",
    "xlink":  "http://www.w3.org/1999/xlink",
}

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


def short_attribs(attribs: dict) -> dict:
    return {short_tag(k): v for k, v in attribs.items()}


def parse_pos_list(text: str) -> list[list[float]]:
    """Parse a gml:posList (flat list of floats) into [[x,y,z], ...]."""
    nums = [float(n) for n in text.split()]
    return [nums[i:i+3] for i in range(0, len(nums), 3)]


def elem_text(el: ET.Element) -> str | None:
    t = (el.text or "").strip()
    return t if t else None


# ── Core extraction ───────────────────────────────────────────────────────────

def parse_linear_ring(el: ET.Element) -> dict:
    ring = {"id": el.get("{http://www.opengis.net/gml}id"), "points": []}
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
    poly = {"id": el.get("{http://www.opengis.net/gml}id"), "exterior": None, "interior": []}
    ext = el.find("gml:exterior/gml:LinearRing", NS)
    if ext is not None:
        poly["exterior"] = parse_linear_ring(ext)
    for interior in el.findall("gml:interior/gml:LinearRing", NS):
        poly["interior"].append(parse_linear_ring(interior))
    return poly


def collect_polygons(el: ET.Element) -> list[dict]:
    """Recursively find all gml:Polygon elements under el."""
    polys = []
    for poly_el in el.iter("{http://www.opengis.net/gml}Polygon"):
        polys.append(parse_polygon(poly_el))
    return polys


def parse_envelope(el: ET.Element) -> dict | None:
    env = el.find("gml:boundedBy/gml:Envelope", NS)
    if env is None:
        return None
    lo = env.find("gml:lowerCorner", NS)
    hi = env.find("gml:upperCorner", NS)
    return {
        "srs": env.get("srsName"),
        "lower": lo.text.strip() if lo is not None and lo.text else None,
        "upper": hi.text.strip() if hi is not None and hi.text else None,
    }


def parse_opening(el: ET.Element) -> dict:
    tag = short_tag(el.tag)  # e.g. bldg:Window / bldg:Door
    opening = {
        "type": tag,
        "id": el.get("{http://www.opengis.net/gml}id"),
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
        "id": el.get("{http://www.opengis.net/gml}id"),
        "name": None,
        "bbox": parse_envelope(el),
        "polygons": [],
        "openings": [],
    }
    name_el = el.find("gml:name", NS)
    if name_el is not None:
        surface["name"] = elem_text(name_el)

    # collect polygons from the lod geometry (exclude opening sub-elements)
    for lod_tag in ["bldg:lod2MultiSurface", "bldg:lod3MultiSurface", "bldg:lod4MultiSurface"]:
        lod_el = el.find(lod_tag, NS)
        if lod_el is not None:
            surface["polygons"] = collect_polygons(lod_el)
            break

    # openings (Window / Door)
    for op_prop in el.findall("bldg:opening", NS):
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
        "id": el.get("{http://www.opengis.net/gml}id"),
        "name": text_of(el, "gml:name"),
        "conductivity": text_of(el, "energy:conductivity"),
        "density": text_of(el, "energy:density"),
        "specificHeat": text_of(el, "energy:specificHeat"),
    }


def parse_construction(el: ET.Element) -> dict:
    c = {
        "id": el.get("{http://www.opengis.net/gml}id"),
        "name": text_of(el, "gml:name"),
        "uValue": text_of(el, "energy:uValue"),
        "layers": [],
    }
    for layer_el in el.findall("energy:layer/energy:Layer/energy:layerComponent/energy:LayerComponent", NS):
        c["layers"].append(parse_layer_component(layer_el))
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
        "id": el.get("{http://www.opengis.net/gml}id"),
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
        "id": el.get("{http://www.opengis.net/gml}id"),
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
            "id": ea_el.get("{http://www.opengis.net/gml}id"),
            "heatDissipation": hd,
            "operationSchedule": parse_schedule(ea_el.find("energy:operationSchedule", NS)),
        })
    return uz


def parse_thermal_zone(el: ET.Element) -> dict:
    tz = {
        "id": el.get("{http://www.opengis.net/gml}id"),
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


def parse_building(el: ET.Element) -> dict:
    building = {
        "id": el.get("{http://www.opengis.net/gml}id"),
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

    name_el = el.find("gml:name", NS)
    if name_el is not None:
        building["name"] = elem_text(name_el)

    desc_el = el.find("gml:description", NS)
    if desc_el is not None:
        building["description"] = elem_text(desc_el)

    # Simple scalar attributes
    for attr, path in [
        ("function",             "bldg:function"),
        ("yearOfConstruction",   "bldg:yearOfConstruction"),
        ("roofType",             "bldg:roofType"),
        ("measuredHeight",       "bldg:measuredHeight"),
        ("storeysAboveGround",   "bldg:storeysAboveGround"),
        ("storeysBelowGround",   "bldg:storeysBelowGround"),
        ("creationDate",         "core:creationDate"),
        ("relativeToTerrain",    "core:relativeToTerrain"),
        ("class",                "bldg:class"),
        ("usage",                "bldg:usage"),
    ]:
        found = el.find(path, NS)
        if found is not None and found.text:
            building["attributes"][attr] = found.text.strip()

    # Address
    addr_el = el.find("bldg:address/core:Address", NS)
    if addr_el is not None:
        building["address"] = parse_address(addr_el)

    # Boundary surfaces
    SURFACE_TYPES = [
        "bldg:WallSurface", "bldg:RoofSurface", "bldg:GroundSurface",
        "bldg:ClosureSurface", "bldg:InteriorWallSurface",
        "bldg:CeilingSurface", "bldg:FloorSurface",
        "bldg:OuterCeilingSurface", "bldg:OuterFloorSurface",
    ]
    for bounded_by in el.findall("bldg:boundedBy", NS):
        for surf_type in SURFACE_TYPES:
            surf_el = bounded_by.find(surf_type, NS)
            if surf_el is not None:
                building["surfaces"].append(parse_surface(surf_el))

    # Energy ADE
    for tz_el in el.findall("energy:thermalZone/energy:ThermalZone", NS):
        building["energy"]["thermalZones"].append(parse_thermal_zone(tz_el))

    # Building-level UsageZones (defined here, referenced by ThermalZone via xlink)
    for uz_el in el.findall("energy:usageZone/energy:UsageZone", NS):
        building["energy"]["usageZones"].append(parse_usage_zone(uz_el))

    # Building-level floor areas
    for fa_el in el.findall("energy:floorArea/energy:FloorArea", NS):
        building["energy"]["floorAreas"].append({
            "type": text_of(fa_el, "energy:type"),
            "value": text_of(fa_el, "energy:value"),
        })

    return building


def parse_file(path: str) -> dict:
    tree = ET.parse(path)
    root = tree.getroot()

    model = {
        "file": str(path),
        "id": root.get("{http://www.opengis.net/gml}id"),
        "bbox": parse_envelope(root),
        "buildings": [],
    }

    for member in root.findall("core:cityObjectMember", NS):
        bldg_el = member.find("bldg:Building", NS)
        if bldg_el is not None:
            model["buildings"].append(parse_building(bldg_el))

    # Also check gml:featureMember (some files use this)
    for member in root.findall("gml:featureMember", NS):
        bldg_el = member.find("bldg:Building", NS)
        if bldg_el is not None:
            model["buildings"].append(parse_building(bldg_el))

    return model


# ── Pretty-print tree ─────────────────────────────────────────────────────────

def _indent(level: int) -> str:
    return "  " * level


def print_tree(model: dict):
    print(f"📁 File: {model['file']}")
    if model["bbox"]:
        bb = model["bbox"]
        print(f"   BBox: {bb['lower']} → {bb['upper']}  [{bb['srs']}]")
    print()

    for b in model["buildings"]:
        print(f"🏠 Building  id={b['id']}")
        if b["name"]:
            print(f"   name: {b['name']}")
        if b["description"]:
            print(f"   description: {b['description']}")
        if b["bbox"]:
            bb = b["bbox"]
            print(f"   bbox: {bb['lower']} → {bb['upper']}")
        for k, v in b["attributes"].items():
            print(f"   {k}: {v}")
        for k, v in b["generic_attributes"].items():
            print(f"   [generic] {k}: {v}")
        if b["address"]:
            addr = b["address"]
            parts = [addr.get("street",""), addr.get("number",""), addr.get("postcode",""), addr.get("city","")]
            print(f"   address: {' '.join(p for p in parts if p)}")

        # Surfaces
        walls   = [s for s in b["surfaces"] if "Wall"   in s["type"]]
        roofs   = [s for s in b["surfaces"] if "Roof"   in s["type"]]
        grounds = [s for s in b["surfaces"] if "Ground" in s["type"]]
        others  = [s for s in b["surfaces"] if s not in walls + roofs + grounds]

        for group_label, group in [
            ("WallSurface", walls),
            ("RoofSurface", roofs),
            ("GroundSurface", grounds),
            ("Other surfaces", others),
        ]:
            if not group:
                continue
            print(f"\n   ── {group_label} ({len(group)}) ──")
            for s in group:
                name = s["name"] or "(unnamed)"
                n_polys = len(s["polygons"])
                n_open  = len(s["openings"])
                print(f"   │  {s['type']}  id={s['id']}")
                print(f"   │    name: {name}")
                print(f"   │    polygons: {n_polys}")
                if s["bbox"]:
                    bb = s["bbox"]
                    print(f"   │    bbox: {bb['lower']} → {bb['upper']}")
                if s["openings"]:
                    print(f"   │    openings ({n_open}):")
                    for o in s["openings"]:
                        o_name = o["name"] or "(unnamed)"
                        print(f"   │      {o['type']}  id={o['id']}  name={o_name}  polygons={len(o['polygons'])}")

        # Energy ADE
        tz_list = b["energy"]["thermalZones"]
        if tz_list:
            print(f"\n   ── Energy ADE: ThermalZones ({len(tz_list)}) ──")
            for tz in tz_list:
                print(f"   │  ThermalZone  id={tz['id']}")
                print(f"   │    isHeated={tz['isHeated']}  isCooled={tz['isCooled']}")
                for v in tz["volumes"]:
                    print(f"   │    volume [{v['type']}]: {v['value']}")
                for fa in tz["floorAreas"]:
                    print(f"   │    floorArea [{fa['type']}]: {fa['value']}")

                if tz["thermalBoundaries"]:
                    print(f"   │    ThermalBoundaries ({len(tz['thermalBoundaries'])}):")
                    for tb in tz["thermalBoundaries"]:
                        print(f"   │      ThermalBoundary  id={tb['id']}")
                        print(f"   │        type={tb['type']}  azimuth={tb['azimuth']}  inclination={tb['inclination']}")
                        print(f"   │        area={tb['area']}")
                        if isinstance(tb["construction"], dict):
                            c = tb["construction"]
                            print(f"   │        construction: {c.get('name')} (uValue={c.get('uValue')})")
                            for layer in c.get("layers", []):
                                mat = layer.get("material") or {}
                                print(f"   │          layer: thickness={layer['thickness']}  material={mat.get('name')}  λ={mat.get('conductivity')}  ρ={mat.get('density')}")
                        elif isinstance(tb["construction"], str):
                            print(f"   │        construction: → {tb['construction']}")
                        for to in tb["thermalOpenings"]:
                            print(f"   │        ThermalOpening  area={to['area']}  uValue={to['uValue']}  glazingRatio={to['glazingRatio']}")
                            if to["opticalProperties"]:
                                for k, v in to["opticalProperties"].items():
                                    print(f"   │          {k}: {v}")

                if tz["usageZones"]:
                    print(f"   │    UsageZones ({len(tz['usageZones'])}):")
                    for uz in tz["usageZones"]:
                        print(f"   │      UsageZone  id={uz['id']}  type={uz['type']}")
                        print(f"   │        isHeated={uz['isHeated']}  isCooled={uz['isCooled']}")
                        print(f"   │        isVentilated={uz['isVentilated']}  isMechanicallyVentilated={uz['isMechanicallyVentilated']}")
                        for fa in uz["floorAreas"]:
                            print(f"   │        floorArea [{fa['type']}]: {fa['value']}")
                        if uz["heatingSchedule"]:
                            print(f"   │        heatingSchedule: {uz['heatingSchedule'].get('scheduleType')}")
                        if uz["coolingSchedule"]:
                            print(f"   │        coolingSchedule: {uz['coolingSchedule'].get('scheduleType')}")
                        if uz["ventilationSchedule"]:
                            print(f"   │        ventilationSchedule: {uz['ventilationSchedule'].get('scheduleType')}")
                        for ea in uz["electricalAppliances"]:
                            print(f"   │        ElectricalAppliances  heatDissipation={ea['heatDissipation']}")
        print()


def print_summary(model: dict):
    print(f"File: {model['file']}")
    print(f"Buildings: {len(model['buildings'])}")
    for b in model["buildings"]:
        print(f"\nBuilding: {b['name'] or b['id']}")
        surface_counts = {}
        opening_counts = {}
        poly_counts = {}
        for s in b["surfaces"]:
            t = s["type"].split(":")[-1]
            surface_counts[t] = surface_counts.get(t, 0) + 1
            poly_counts[t] = poly_counts.get(t, 0) + len(s["polygons"])
            for o in s["openings"]:
                ot = o["type"].split(":")[-1]
                opening_counts[ot] = opening_counts.get(ot, 0) + 1
        print("  Surfaces:")
        for t, n in sorted(surface_counts.items()):
            print(f"    {t}: {n}  ({poly_counts[t]} polygons)")
        if opening_counts:
            print("  Openings:")
            for t, n in sorted(opening_counts.items()):
                print(f"    {t}: {n}")
        tz_count = len(b["energy"]["thermalZones"])
        if tz_count:
            tb_total = sum(len(tz["thermalBoundaries"]) for tz in b["energy"]["thermalZones"])
            uz_total = sum(len(tz["usageZones"]) for tz in b["energy"]["thermalZones"])
            print(f"  Energy ADE:")
            print(f"    ThermalZones: {tz_count}")
            print(f"    ThermalBoundaries: {tb_total}")
            print(f"    UsageZones: {uz_total}")
        for k, v in b["attributes"].items():
            print(f"  {k}: {v}")
        for k, v in b["generic_attributes"].items():
            print(f"  [generic] {k}: {v}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CityGML 2.0 parser (including Energy ADE)")
    parser.add_argument("file", help="Path to .gml file")
    parser.add_argument("--mode", choices=["tree", "summary", "json"], default="tree",
                        help="Output mode (default: tree)")
    parser.add_argument("--indent", type=int, default=2,
                        help="JSON indent level (only for --mode json)")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    model = parse_file(str(path))

    if args.mode == "json":
        print(json.dumps(model, indent=args.indent, ensure_ascii=False))
    elif args.mode == "summary":
        print_summary(model)
    else:
        print_tree(model)


if __name__ == "__main__":
    main()
