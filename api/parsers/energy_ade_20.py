"""Energy ADE 2.0 parser.

Schema reference: http://www.sig3d.org/citygml/2.0/energy/2.0
Namespace prefix: energy
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .base import NS, _gml_id, elem_text, text_of, collect_polygons


# ── Material / Construction ───────────────────────────────────────────────────

def parse_solid_material(el: ET.Element | None) -> dict | None:
    if el is None:
        return None
    return {
        "id":           _gml_id(el),
        "name":         text_of(el, "gml:name"),
        "conductivity": text_of(el, "energy:conductivity"),
        "density":      text_of(el, "energy:density"),
        "specificHeat": text_of(el, "energy:specificHeat"),
    }


def parse_gas(el: ET.Element) -> dict:
    return {
        "id":          _gml_id(el),
        "name":        text_of(el, "gml:name"),
        "description": text_of(el, "gml:description"),
        "isVentilated": text_of(el, "energy:isVentilated"),
        "rValue":      text_of(el, "energy:rValue"),
    }


def parse_layer_component(el: ET.Element) -> dict:
    mat_container = el.find("energy:material", NS)
    material = None
    if mat_container is not None:
        href = mat_container.get("{http://www.w3.org/1999/xlink}href")
        if href:
            material = href
        else:
            for mat_el in mat_container:
                if "SolidMaterial" in mat_el.tag or "Gas" in mat_el.tag:
                    material = parse_solid_material(mat_el)
                    break
    return {
        "thickness": text_of(el, "energy:thickness"),
        "material":  material,
    }


def parse_construction(el: ET.Element) -> dict:
    return {
        "id":     _gml_id(el),
        "name":   text_of(el, "gml:name"),
        "uValue": text_of(el, "energy:uValue"),
        "layers": [
            parse_layer_component(lc)
            for lc in el.findall(
                "energy:layer/energy:Layer/energy:layerComponent/energy:LayerComponent",
                NS,
            )
        ],
    }


def _construction_ref_or_inline(el: ET.Element) -> str | dict | None:
    c_el = el.find("energy:construction/energy:Construction", NS)
    if c_el is not None:
        return parse_construction(c_el)
    c_ref = el.find("energy:construction", NS)
    if c_ref is not None:
        return c_ref.get("{http://www.w3.org/1999/xlink}href")
    return None


# ── Optical / Openings ────────────────────────────────────────────────────────

def parse_optical_props(el: ET.Element | None) -> dict | None:
    if el is None:
        return None
    result: dict = {}
    for t_el in el.findall("energy:transmittance/energy:Transmittance", NS):
        wl   = text_of(t_el, "energy:wavelengthRange")
        frac = text_of(t_el, "energy:fraction")
        result[f"transmittance_{wl}"] = frac
    return result or None


def parse_thermal_opening(el: ET.Element) -> dict:
    return {
        "id":               _gml_id(el),
        "area":             text_of(el, "energy:area"),
        "uValue":           text_of(el, "energy:uValue"),
        "glazingRatio":     text_of(el, "energy:glazingRatio"),
        "construction":     _construction_ref_or_inline(el),
        "opticalProperties": parse_optical_props(
            el.find("energy:opticalProperties/energy:OpticalProperties", NS)
        ),
    }


# ── Boundaries ────────────────────────────────────────────────────────────────

def parse_thermal_boundary(el: ET.Element) -> dict:
    tb: dict = {
        "id":               _gml_id(el),
        "type":             text_of(el, "energy:thermalBoundaryType"),
        "azimuth":          text_of(el, "energy:azimuth"),
        "inclination":      text_of(el, "energy:inclination"),
        "area":             text_of(el, "energy:area"),
        "construction":     _construction_ref_or_inline(el),
        "thermalOpenings":  [],
        "surfaceGeometry":  None,
    }
    for to_el in el.findall("energy:contains/energy:ThermalOpening", NS):
        tb["thermalOpenings"].append(parse_thermal_opening(to_el))
    sg = el.find("energy:surfaceGeometry", NS)
    if sg is not None:
        tb["surfaceGeometry"] = {"href": sg.get("{http://www.w3.org/1999/xlink}href")}
    return tb


# ── Schedules ─────────────────────────────────────────────────────────────────

def parse_schedule(el: ET.Element | None) -> dict | None:
    if el is None:
        return None
    sched_el = next(iter(el), None)
    if sched_el is None:
        return None
    tag      = f"{sched_el.tag.split('}')[1]}" if "}" in sched_el.tag else sched_el.tag
    name_el  = sched_el.find("gml:name", NS)
    result: dict = {
        "scheduleType": tag,
        "name": name_el.text.strip() if name_el is not None and name_el.text else None,
    }
    for pop_el in sched_el.findall("energy:periodOfYear/energy:PeriodOfYear", NS):
        for dp in pop_el.findall("energy:dailySchedule/energy:DailySchedule", NS):
            day_type    = text_of(dp, "energy:dayType") or "typicalDay"
            sched_inner = dp.find("energy:schedule", NS)
            if sched_inner is not None:
                ts = sched_inner.find("energy:RegularTimeSeries", NS)
                if ts is not None:
                    vals_el = ts.find("energy:values", NS)
                    desc_el = ts.find(
                        "energy:variableProperties/energy:TimeValuesProperties"
                        "/energy:thematicDescription",
                        NS,
                    )
                    result[f"schedule_{day_type}"] = {
                        "timeInterval": text_of(ts, "energy:timeInterval"),
                        "values":       vals_el.text.strip() if vals_el is not None and vals_el.text else None,
                        "uom":          vals_el.get("uom") if vals_el is not None else None,
                        "description":  desc_el.text.strip() if desc_el is not None and desc_el.text else None,
                    }
    return result


# ── Zones ─────────────────────────────────────────────────────────────────────

def parse_usage_zone(el: ET.Element) -> dict:
    uz: dict = {
        "id":                       _gml_id(el),
        "type":                     text_of(el, "energy:usageZoneType"),
        "isHeated":                 text_of(el, "energy:isHeated"),
        "isCooled":                 text_of(el, "energy:isCooled"),
        "isVentilated":             text_of(el, "energy:isVentilated"),
        "isMechanicallyVentilated": text_of(el, "energy:isMechanicallyVentilated"),
        "floorAreas":               [],
        "occupancySchedules":       [],
        "heatingSchedule":          parse_schedule(el.find("energy:heatingSchedule", NS)),
        "coolingSchedule":          parse_schedule(el.find("energy:coolingSchedule", NS)),
        "ventilationSchedule":      parse_schedule(el.find("energy:ventilationSchedule", NS)),
        "electricalAppliances":     [],
    }
    for fa_el in el.findall("energy:floorArea/energy:FloorArea", NS):
        uz["floorAreas"].append({
            "type":  text_of(fa_el, "energy:type"),
            "value": text_of(fa_el, "energy:value"),
        })
    for ea_el in el.findall("energy:equippedWith/energy:ElectricalAppliances", NS):
        hd_el = ea_el.find("energy:heatDissipation/energy:HeatExchangeType", NS)
        hd = None
        if hd_el is not None:
            hd = {
                "totalValue":        text_of(hd_el, "energy:totalValue"),
                "convectiveFraction": text_of(hd_el, "energy:convectiveFraction"),
                "radiantFraction":   text_of(hd_el, "energy:radiantFraction"),
            }
        uz["electricalAppliances"].append({
            "id":                _gml_id(ea_el),
            "heatDissipation":   hd,
            "operationSchedule": parse_schedule(ea_el.find("energy:operationSchedule", NS)),
        })
    return uz


def parse_thermal_zone(el: ET.Element) -> dict:
    tz: dict = {
        "id":                _gml_id(el),
        "isHeated":          text_of(el, "energy:isHeated"),
        "isCooled":          text_of(el, "energy:isCooled"),
        "volumes":           [],
        "floorAreas":        [],
        "thermalBoundaries": [],
        "usageZones":        [],
        "usageZoneRefs":     [],
    }
    for vol_el in el.findall("energy:volume/energy:VolumeType", NS):
        tz["volumes"].append({
            "type":  text_of(vol_el, "energy:type"),
            "value": text_of(vol_el, "energy:value"),
        })
    for fa_el in el.findall("energy:floorArea/energy:FloorArea", NS):
        tz["floorAreas"].append({
            "type":  text_of(fa_el, "energy:type"),
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


# ── Building enrichment ───────────────────────────────────────────────────────

def enrich_building(el: ET.Element, building: dict) -> None:
    """Add Energy ADE 2.0 thermal data in-place to a building dict."""
    for tz_el in el.findall("energy:thermalZone/energy:ThermalZone", NS):
        building["energy"]["thermalZones"].append(parse_thermal_zone(tz_el))
    for uz_el in el.findall("energy:usageZone/energy:UsageZone", NS):
        building["energy"]["usageZones"].append(parse_usage_zone(uz_el))
    for fa_el in el.findall("energy:floorArea/energy:FloorArea", NS):
        building["energy"]["floorAreas"].append({
            "type":  text_of(fa_el, "energy:type"),
            "value": text_of(fa_el, "energy:value"),
        })


# ── Global object collector ───────────────────────────────────────────────────

def collect_global_objects(root: ET.Element) -> dict:
    """Return a {gml_id: parsed_object} dict for top-level ADE 2.0 objects."""
    result: dict = {}
    for wrapper in ("gml:featureMember", "core:cityObjectMember"):
        for member in root.findall(wrapper, NS):
            for child in member:
                gml_id = _gml_id(child)
                if not gml_id:
                    continue
                local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if local == "Construction":
                    obj = parse_construction(child)
                    obj["_class"] = "Construction"
                    result[gml_id] = obj
                elif local == "SolidMaterial":
                    obj = parse_solid_material(child) or {}
                    obj["_class"] = "SolidMaterial"
                    result[gml_id] = obj
                elif local == "Gas":
                    obj = parse_gas(child)
                    obj["_class"] = "Gas"
                    result[gml_id] = obj
    return result
