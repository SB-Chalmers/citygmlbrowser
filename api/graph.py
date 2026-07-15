"""Graph builder for the CityGML Browser API.

Transforms the parsed CityGML model dict into vis-network compatible
{nodes, edges} data.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from api.parsers.base import NS, _gml_id, text_of
from api.parsers import energy_ade_20, energy_ade_30
from api.dialect import detect_dialect

# ── Node styling ──────────────────────────────────────────────────────────────

TYPE_STYLE = {
    "CityModel":                    {"bg": "#2C3E50", "border": "#1a252f", "font": "#ffffff", "size": 38, "shape": "diamond"},
    "Building":                     {"bg": "#E8720C", "border": "#b85a08", "font": "#ffffff", "size": 44, "shape": "dot"},
    # CityGML 2.0 boundary surfaces
    "WallSurface":                  {"bg": "#4C8EDA", "border": "#2c6bb5", "font": "#ffffff", "size": 32, "shape": "dot"},
    "RoofSurface":                  {"bg": "#D0021B", "border": "#a80116", "font": "#ffffff", "size": 32, "shape": "dot"},
    "GroundSurface":                {"bg": "#5CB85C", "border": "#3d9b3d", "font": "#ffffff", "size": 32, "shape": "dot"},
    "ClosureSurface":               {"bg": "#7F8C8D", "border": "#5d6566", "font": "#ffffff", "size": 26, "shape": "dot"},
    "InteriorWallSurface":          {"bg": "#F39C12", "border": "#c47d0e", "font": "#ffffff", "size": 28, "shape": "dot"},
    "CeilingSurface":               {"bg": "#16A085", "border": "#0e6b5a", "font": "#ffffff", "size": 28, "shape": "dot"},
    "FloorSurface":                 {"bg": "#27AE60", "border": "#1a7a43", "font": "#ffffff", "size": 28, "shape": "dot"},
    "Window":                       {"bg": "#AED6F1", "border": "#5dade2", "font": "#ffffff", "size": 22, "shape": "dot"},
    "Door":                         {"bg": "#A9DFBF", "border": "#52be80", "font": "#ffffff", "size": 22, "shape": "dot"},
    # CityGML 3.0 constructive elements
    "Storey":                       {"bg": "#5D6D7E", "border": "#2E4053", "font": "#ffffff", "size": 34, "shape": "dot"},
    "BuildingConstructiveElement":  {"bg": "#4C8EDA", "border": "#2c6bb5", "font": "#ffffff", "size": 28, "shape": "dot"},
    # Energy ADE
    "ThermalZone":                  {"bg": "#9B59B6", "border": "#7d3c98", "font": "#ffffff", "size": 36, "shape": "dot"},
    "ThermalBoundary":              {"bg": "#C39BD3", "border": "#9b59b6", "font": "#ffffff", "size": 26, "shape": "dot"},
    "ThermalOpening":               {"bg": "#D7BDE2", "border": "#c39bd3", "font": "#ffffff", "size": 20, "shape": "dot"},
    "Construction":                 {"bg": "#F1C40F", "border": "#c29d0b", "font": "#ffffff", "size": 28, "shape": "dot"},
    "SolidMaterial":                {"bg": "#95A5A6", "border": "#717d7e", "font": "#ffffff", "size": 20, "shape": "dot"},
    "Gas":                          {"bg": "#BDC3C7", "border": "#95a5a6", "font": "#ffffff", "size": 20, "shape": "dot"},
    "UsageZone":                    {"bg": "#1ABC9C", "border": "#148f77", "font": "#ffffff", "size": 32, "shape": "dot"},
    "ElectricalAppliances":         {"bg": "#E74C3C", "border": "#c0392b", "font": "#ffffff", "size": 24, "shape": "dot"},
}
DEFAULT_STYLE = {"bg": "#BDC3C7", "border": "#95a5a6", "font": "#ffffff", "size": 22, "shape": "dot"}


# ── Global energy feature collector ──────────────────────────────────────────

def _local(tag):
    return tag.split("}")[1] if "}" in tag else tag.split(":")[-1]


def collect_global_energy(gml_file: str) -> dict:
    """Return global energy objects keyed by gml:id.

    Delegates to the version-specific ADE parser based on detected dialect.
    """
    root    = ET.parse(gml_file).getroot()
    dialect = detect_dialect(gml_file)
    if dialect.energy_ade == "3.0":
        return energy_ade_30.collect_global_objects(root)
    if dialect.energy_ade == "2.0":
        return energy_ade_20.collect_global_objects(root)
    return {}


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph(model, gml_file):
    global_energy = collect_global_energy(gml_file)
    created_refs = {}   # gml_id → vis node id (for shared xlink targets)

    nodes = []
    edges = []
    _ctr = [0]

    def nid():
        _ctr[0] += 1
        return _ctr[0]

    def add_node(node_type, label, details):
        i = nid()
        s = TYPE_STYLE.get(node_type, DEFAULT_STYLE)
        nodes.append({
            "id": i,
            "label": label,
            "_baseLabel": label,
            "group": node_type,
            "color": {
                "background": s["bg"],
                "border": s["border"],
                "highlight": {"background": s["bg"], "border": "#ffffff"},
                "hover":     {"background": s["bg"], "border": "#ffffff"},
            },
            "size": s["size"],
            "shape": s["shape"],
            "font": {"color": s["font"], "size": 11, "face": "ui-sans-serif, system-ui, sans-serif", "strokeWidth": 4, "strokeColor": "rgba(0,0,0,0.9)"},
            "details": {k: v for k, v in details.items() if v is not None},
            "children": [],   # direct child node ids
        })
        return i

    def add_edge(src, dst, label, dashes=False):
        # Track parent→child for collapse
        src_node = next((n for n in nodes if n["id"] == src), None)
        if src_node is not None and dst not in src_node["children"]:
            src_node["children"].append(dst)
        edges.append({
            "from": src, "to": dst,
            "label": "",        # hidden by default; toggled by JS
            "_label": label,    # stored for toggle
            "title": label,     # always visible as tooltip on hover
            "arrows": "to",
            "dashes": dashes,
            "color": {"color": "#3d4460" if not dashes else "#5d6880", "highlight": "#5a6490", "inherit": False},
            "font":  {"color": "#c8cfe0", "size": 9, "align": "middle", "strokeWidth": 2, "strokeColor": "rgba(0,0,0,0.85)"},
            "smooth": {"type": "cubicBezier", "forceDirection": "vertical", "roundness": 0.4},
        })

    def schedule_summary(sched):
        """Return a short human-readable string for a schedule (e.g. '16–20 C' or '0.5 1/h')."""
        if not sched:
            return None
        for key, val in sched.items():
            if key.startswith("schedule_") and isinstance(val, dict):
                raw = (val.get("values") or "").split()
                nums = []
                for p in raw:
                    try:
                        nums.append(float(p))
                    except ValueError:
                        pass
                if nums:
                    uom = val.get("uom") or ""
                    mn, mx = min(nums), max(nums)
                    if mn == mx:
                        return f"{mn} {uom}".strip()
                    return f"{mn}\u2013{mx} {uom}".strip()
        return sched.get("name") or sched.get("scheduleType")

    def build_material_node(href_or_dict, parent_id, edge_label):
        """Create/reuse a material node and link from parent."""
        if href_or_dict is None:
            return
        if isinstance(href_or_dict, dict):
            mat_type = "Gas" if href_or_dict.get("rValue") and not href_or_dict.get("conductivity") else "SolidMaterial"
            mat_name = href_or_dict.get("name") or "Material"
            mat_details = {k: v for k, v in href_or_dict.items() if k != "_class" and v is not None}
            m_id = add_node(mat_type, mat_name, mat_details)
            add_edge(parent_id, m_id, edge_label)
        elif isinstance(href_or_dict, str):
            ref_key = href_or_dict.lstrip("#")
            if ref_key in created_refs:
                add_edge(parent_id, created_refs[ref_key], edge_label, dashes=True)
            elif ref_key in global_energy:
                obj = global_energy[ref_key]
                mat_class = obj.get("_class", "SolidMaterial")
                mat_name = obj.get("name") or ref_key
                mat_details = {k: v for k, v in obj.items() if k != "_class" and v is not None}
                m_id = add_node(mat_class, mat_name, mat_details)
                created_refs[ref_key] = m_id
                add_edge(parent_id, m_id, edge_label)
            else:
                m_id = add_node("SolidMaterial", href_or_dict.lstrip("#"), {"xlink:href": href_or_dict})
                add_edge(parent_id, m_id, edge_label, dashes=True)

    def build_construction_node(c_or_href, parent_id, edge_label="construction"):
        """Create a Construction node (inline or resolved from xlink) and add layers."""
        if c_or_href is None:
            return
        if isinstance(c_or_href, str):
            ref_key = c_or_href.lstrip("#")
            if ref_key in created_refs:
                add_edge(parent_id, created_refs[ref_key], edge_label, dashes=True)
                return
            c = global_energy.get(ref_key)
            if c is None:
                c_id = add_node("Construction", ref_key, {"xlink:href": c_or_href})
                add_edge(parent_id, c_id, edge_label, dashes=True)
                return
        else:
            c = c_or_href

        c_name = c.get("name") or "Construction"
        c_details = {k: v for k, v in c.items() if k not in ("_class", "layers") and v is not None}
        c_id = add_node("Construction", c_name, c_details)

        # Cache if it came from xlink ref
        if isinstance(c_or_href, str):
            created_refs[c_or_href.lstrip("#")] = c_id

        add_edge(parent_id, c_id, edge_label, dashes=isinstance(c_or_href, str))

        for i, layer in enumerate(c.get("layers", []), 1):
            build_material_node(layer.get("material"), c_id, f"layer {i}")

    # ── CityModel ──
    bbox = model.get("bbox") or {}
    cm_id = add_node("CityModel", "CityModel", {
        "file":  Path(model["file"]).name,
        "lower": bbox.get("lower"),
        "upper": bbox.get("upper"),
        "srs":   bbox.get("srs"),
    })

    for b in model["buildings"]:
        b_bbox = b.get("bbox") or {}
        b_details = {"id": b["id"], **b["attributes"]}
        b_details["description"] = b.get("description")
        if b.get("address"):
            parts = [b["address"].get(k, "") for k in ["street", "number", "postcode", "city"]]
            b_details["address"] = " ".join(p for p in parts if p)
        for k, v in b.get("generic_attributes", {}).items():
            b_details[f"[generic] {k}"] = str(v) if isinstance(v, dict) else v
        b_details["bbox lower"] = b_bbox.get("lower")
        b_details["bbox upper"] = b_bbox.get("upper")
        for fa in b["energy"].get("floorAreas", []):
            b_details[f"floorArea [{fa['type']}]"] = fa["value"]

        b_id = add_node("Building", b["name"] or "Building", b_details)
        add_edge(cm_id, b_id, "contains")

        # ── CityGML 2.0: boundary surfaces ──
        for s in b["surfaces"]:
            surf_type = s["type"].split(":")[-1]
            s_bbox = s.get("bbox") or {}
            s_details = {
                "id": s.get("id"),
                "type": surf_type,
                "polygons": len(s["polygons"]),
                "openings": len(s["openings"]),
                "bbox lower": s_bbox.get("lower"),
                "bbox upper": s_bbox.get("upper"),
            }
            s_id = add_node(surf_type, s["name"] or surf_type, s_details)
            add_edge(b_id, s_id, "boundedBy")

            for o in s["openings"]:
                o_type = o["type"].split(":")[-1]
                o_id = add_node(o_type, o["name"] or o_type, {
                    "id":       o.get("id"),
                    "type":     o_type,
                    "polygons": len(o["polygons"]),
                })
                add_edge(s_id, o_id, "opening")

        # ── CityGML 3.0: storeys + constructive elements ──
        def _add_bce(bce: dict, parent_id: int) -> None:
            bce_label = bce.get("name") or bce.get("class") or "Element"
            bce_id = add_node("BuildingConstructiveElement", bce_label, {
                "id":                 bce.get("id"),
                "class":              bce.get("class"),
                "isStructuralElement": bce.get("isStructuralElement"),
                "polygons":           len(bce.get("polygons", [])),
                "openings":           len(bce.get("openings", [])),
            })
            add_edge(parent_id, bce_id, "buildingConstructiveElement")
            for o in bce.get("openings", []):
                o_type = o["type"].split(":")[-1]
                o_id = add_node(o_type, o.get("name") or o_type, {
                    "id":       o.get("id"),
                    "type":     o_type,
                    "polygons": len(o.get("polygons", [])),
                })
                add_edge(bce_id, o_id, "filling")

        for storey in b.get("storeys", []):
            st_id = add_node("Storey", storey.get("name") or storey.get("class") or "Storey", {
                "id":    storey.get("id"),
                "class": storey.get("class"),
                "elements": len(storey.get("constructiveElements", [])),
            })
            add_edge(b_id, st_id, "buildingSubdivision")
            for bce in storey.get("constructiveElements", []):
                _add_bce(bce, st_id)

        for bce in b.get("constructiveElements", []):
            _add_bce(bce, b_id)

        # ── Energy ADE ──
        # Build a map of GML-id → vis-node-id for building-level UsageZones
        # so ThermalZone can add xlink edges to them.
        uz_node_map = {}  # gml_id → vis node id

        for uz in b["energy"].get("usageZones", []):
            uz_details = {
                "id":           uz["id"],
                "type":         uz["type"],
                "isHeated":     uz["isHeated"],
                "isCooled":     uz["isCooled"],
                "isVentilated": uz["isVentilated"],
                "isMechanicallyVentilated": uz["isMechanicallyVentilated"],
            }
            for fa in uz.get("floorAreas", []):
                uz_details[f"floorArea [{fa['type']}]"] = fa["value"]
            hs = schedule_summary(uz.get("heatingSchedule"))
            cs = schedule_summary(uz.get("coolingSchedule"))
            vs = schedule_summary(uz.get("ventilationSchedule"))
            if hs:
                uz_details["heatingSetpoint"] = hs
            if cs:
                uz_details["coolingSetpoint"] = cs
            if vs:
                uz_details["ventilationRate"] = vs
            uz_id = add_node("UsageZone", uz.get("type") or "UsageZone", uz_details)
            add_edge(b_id, uz_id, "usageZone")
            if uz["id"]:
                uz_node_map[uz["id"]] = uz_id

            for ea in uz.get("electricalAppliances", []):
                hd = ea.get("heatDissipation") or {}
                ea_details = {"id": ea.get("id")}
                if hd.get("totalValue"):
                    ea_details["totalHeat"] = f"{hd['totalValue']} W/m²"
                if hd.get("convectiveFraction"):
                    ea_details["convective"] = hd["convectiveFraction"]
                if hd.get("radiantFraction"):
                    ea_details["radiant"] = hd["radiantFraction"]
                ops = schedule_summary(ea.get("operationSchedule"))
                if ops:
                    ea_details["operationSchedule"] = ops
                ea_id = add_node("ElectricalAppliances", "Electrical\nAppliances", ea_details)
                add_edge(uz_id, ea_id, "equippedWith")

        for tz in b["energy"]["thermalZones"]:
            tz_details = {"id": tz["id"], "isHeated": tz["isHeated"], "isCooled": tz["isCooled"]}
            for v in tz.get("volumes", []):
                tz_details[f"volume [{v['type']}]"] = v["value"]
            for fa in tz.get("floorAreas", []):
                tz_details[f"floorArea [{fa['type']}]"] = fa["value"]
            tz_id = add_node("ThermalZone", "ThermalZone", tz_details)
            add_edge(b_id, tz_id, "thermalZone")

            # Link ThermalZone to building-level UsageZones via xlink refs
            for ref_id in tz.get("usageZoneRefs", []):
                if ref_id in uz_node_map:
                    add_edge(tz_id, uz_node_map[ref_id], "contains", dashes=True)

            for tb in tz.get("thermalBoundaries", []):
                tb_type = tb.get("type") or "boundary"
                tb_label = f"{tb_type}\n{tb.get('azimuth', '?')}°"
                tb_id = add_node("ThermalBoundary", tb_label, {
                    "id":          tb["id"],
                    "type":        tb["type"],
                    "azimuth":     tb["azimuth"],
                    "inclination": tb["inclination"],
                    "area":        tb["area"],
                })
                add_edge(tz_id, tb_id, "boundedBy")
                build_construction_node(tb.get("construction"), tb_id)

                for idx, to in enumerate(tb.get("thermalOpenings", []), 1):
                    to_details = {
                        "id":           to.get("id"),
                        "area":         to.get("area"),
                        "uValue":       to.get("uValue"),
                        "glazingRatio": to.get("glazingRatio"),
                    }
                    if to.get("opticalProperties"):
                        to_details.update(to["opticalProperties"])
                    to_id = add_node("ThermalOpening", f"Opening {idx}", to_details)
                    add_edge(tb_id, to_id, "contains")
                    build_construction_node(to.get("construction"), to_id)

            for uz in tz.get("usageZones", []):
                uz_details = {
                    "id":                        uz["id"],
                    "type":                      uz["type"],
                    "isHeated":                  uz["isHeated"],
                    "isCooled":                  uz["isCooled"],
                    "isVentilated":              uz["isVentilated"],
                    "isMechanicallyVentilated":  uz["isMechanicallyVentilated"],
                }
                for fa in uz.get("floorAreas", []):
                    uz_details[f"floorArea [{fa['type']}]"] = fa["value"]
                hs = schedule_summary(uz.get("heatingSchedule"))
                cs = schedule_summary(uz.get("coolingSchedule"))
                vs = schedule_summary(uz.get("ventilationSchedule"))
                if hs:
                    uz_details["heatingSetpoint"] = hs
                if cs:
                    uz_details["coolingSetpoint"] = cs
                if vs:
                    uz_details["ventilationRate"] = vs
                uz_id = add_node("UsageZone", uz.get("type") or "UsageZone", uz_details)
                add_edge(tz_id, uz_id, "contains")
                if uz["id"]:
                    uz_node_map[uz["id"]] = uz_id

                for ea in uz.get("electricalAppliances", []):
                    hd = ea.get("heatDissipation") or {}
                    ea_details = {"id": ea.get("id")}
                    if hd.get("totalValue"):
                        ea_details["totalHeat"] = f"{hd['totalValue']} W/m²"
                    if hd.get("convectiveFraction"):
                        ea_details["convective"] = hd["convectiveFraction"]
                    if hd.get("radiantFraction"):
                        ea_details["radiant"] = hd["radiantFraction"]
                    ops = schedule_summary(ea.get("operationSchedule"))
                    if ops:
                        ea_details["operationSchedule"] = ops
                    ea_id = add_node("ElectricalAppliances", "Electrical\nAppliances", ea_details)
                    add_edge(uz_id, ea_id, "equippedWith")

    return {"nodes": nodes, "edges": edges}
