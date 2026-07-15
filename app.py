#!/usr/bin/env python3
"""
CityGML Interactive Graph Viewer

Builds a standalone HTML file with a vis.js force/hierarchical graph
that lets you explore the full CityGML model hierarchy interactively.

Usage:
    python3 app.py models/FZKHouseLoD3-ADE.gml
    python3 app.py models/FZKHouseLoD3-ADE.gml --out my-viewer.html
    python3 app.py models/FZKHouseLoD3-ADE.gml --serve --port 8080
"""

import sys
import json
import argparse
import webbrowser
import http.server
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parse import parse_file, NS, text_of, parse_construction, _parse_solid_material

# ── Node styling ──────────────────────────────────────────────────────────────

TYPE_STYLE = {
    "CityModel":            {"bg": "#2C3E50", "border": "#1a252f", "font": "#ffffff", "size": 38, "shape": "diamond"},
    "Building":             {"bg": "#E8720C", "border": "#b85a08", "font": "#ffffff", "size": 44, "shape": "dot"},
    "WallSurface":          {"bg": "#4C8EDA", "border": "#2c6bb5", "font": "#ffffff", "size": 32, "shape": "dot"},
    "RoofSurface":          {"bg": "#D0021B", "border": "#a80116", "font": "#ffffff", "size": 32, "shape": "dot"},
    "GroundSurface":        {"bg": "#5CB85C", "border": "#3d9b3d", "font": "#ffffff", "size": 32, "shape": "dot"},
    "ClosureSurface":       {"bg": "#7F8C8D", "border": "#5d6566", "font": "#ffffff", "size": 26, "shape": "dot"},
    "InteriorWallSurface":  {"bg": "#F39C12", "border": "#c47d0e", "font": "#ffffff", "size": 28, "shape": "dot"},
    "CeilingSurface":       {"bg": "#16A085", "border": "#0e6b5a", "font": "#ffffff", "size": 28, "shape": "dot"},
    "FloorSurface":         {"bg": "#27AE60", "border": "#1a7a43", "font": "#ffffff", "size": 28, "shape": "dot"},
    "Window":               {"bg": "#AED6F1", "border": "#5dade2", "font": "#ffffff", "size": 22, "shape": "dot"},
    "Door":                 {"bg": "#A9DFBF", "border": "#52be80", "font": "#ffffff", "size": 22, "shape": "dot"},
    "ThermalZone":          {"bg": "#9B59B6", "border": "#7d3c98", "font": "#ffffff", "size": 36, "shape": "dot"},
    "ThermalBoundary":      {"bg": "#C39BD3", "border": "#9b59b6", "font": "#ffffff", "size": 26, "shape": "dot"},
    "ThermalOpening":       {"bg": "#D7BDE2", "border": "#c39bd3", "font": "#ffffff", "size": 20, "shape": "dot"},
    "Construction":         {"bg": "#F1C40F", "border": "#c29d0b", "font": "#ffffff", "size": 28, "shape": "dot"},
    "SolidMaterial":        {"bg": "#95A5A6", "border": "#717d7e", "font": "#ffffff", "size": 20, "shape": "dot"},
    "Gas":                  {"bg": "#BDC3C7", "border": "#95a5a6", "font": "#ffffff", "size": 20, "shape": "dot"},
    "UsageZone":            {"bg": "#1ABC9C", "border": "#148f77", "font": "#ffffff", "size": 32, "shape": "dot"},
    "ElectricalAppliances": {"bg": "#E74C3C", "border": "#c0392b", "font": "#ffffff", "size": 24, "shape": "dot"},
}
DEFAULT_STYLE = {"bg": "#BDC3C7", "border": "#95a5a6", "font": "#ffffff", "size": 22, "shape": "dot"}


# ── Global energy feature collector ──────────────────────────────────────────

def _local(tag):
    return tag.split("}")[1] if "}" in tag else tag.split(":")[-1]


def collect_global_energy(gml_file):
    """Parse top-level energy:Construction / SolidMaterial / Gas from gml:featureMember."""
    root = ET.parse(gml_file).getroot()
    result = {}
    for member in root.findall("gml:featureMember", NS):
        for child in member:
            gml_id = child.get("{http://www.opengis.net/gml}id")
            if not gml_id:
                continue
            local = _local(child.tag)
            if local == "Construction":
                obj = parse_construction(child)
                obj["_class"] = "Construction"
                result[gml_id] = obj
            elif local == "SolidMaterial":
                obj = _parse_solid_material(child) or {}
                obj["_class"] = "SolidMaterial"
                result[gml_id] = obj
            elif local == "Gas":
                result[gml_id] = {
                    "_class": "Gas",
                    "id": gml_id,
                    "name": text_of(child, "gml:name"),
                    "description": text_of(child, "gml:description"),
                    "isVentilated": text_of(child, "energy:isVentilated"),
                    "rValue": text_of(child, "energy:rValue"),
                }
    return result


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

        # ── Boundary surfaces ──
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


# ── HTML template ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CityGML — __FILENAME__</title>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; overflow: hidden; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #1a1e2e;
    color: #e0e6f0;
    display: flex;
    flex-direction: column;
  }

  /* ── Header ── */
  header {
    display: flex; align-items: center; gap: 12px;
    padding: 0 16px;
    height: 48px; flex-shrink: 0;
    background: #0f1219;
    border-bottom: 1px solid #2d3348;
  }
  header h1 { font-size: 14px; font-weight: 700; color: #e8720c; letter-spacing: .04em; white-space: nowrap; }
  header .file { font-size: 11px; color: #556080; font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .controls { margin-left: auto; display: flex; gap: 6px; flex-shrink: 0; }
  button {
    padding: 4px 11px; border: 1px solid #3d4460; border-radius: 4px;
    background: #1e2335; color: #a0aec0; font-size: 11px; cursor: pointer;
    transition: all .12s;
  }
  button:hover  { background: #252d45; border-color: #5a6480; color: #e0e6f0; }
  button.active { background: #e8720c; border-color: #e8720c; color: #fff; }

  /* ── Main layout ── */
  .main { display: flex; flex: 1; min-height: 0; }

  /* ── Graph canvas ── */
  #graph-wrap { flex: 1; position: relative; background: #1a1e2e; }
  #graph { width: 100%; height: 100%; }

  /* ── Sidebar ── */
  #sidebar {
    width: 290px; flex-shrink: 0;
    background: #141824;
    border-left: 1px solid #2d3348;
    display: flex; flex-direction: column;
    overflow: hidden;
  }
  #sidebar-header {
    padding: 10px 13px 8px;
    border-bottom: 1px solid #2d3348;
    flex-shrink: 0;
  }
  #sidebar-header h2 { font-size: 11px; font-weight: 700; color: #e8720c; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 7px; }
  #search {
    width: 100%; padding: 5px 9px;
    background: #1a1e2e; border: 1px solid #2d3348; border-radius: 4px;
    color: #e0e6f0; font-size: 12px; outline: none;
    transition: border-color .12s;
  }
  #search:focus { border-color: #e8720c; }
  #search::placeholder { color: #3d4460; }
  #props { flex: 1; overflow-y: auto; padding: 10px 13px; }
  #props .empty { color: #7a8daa; font-size: 12px; font-style: italic; text-align: center; margin-top: 40px; }

  /* Node detail panel */
  .type-badge {
    display: inline-block; padding: 2px 9px; border-radius: 10px;
    font-size: 10px; font-weight: 700; letter-spacing: .04em;
    margin-bottom: 8px; text-transform: uppercase;
  }
  .node-name {
    font-size: 14px; font-weight: 600; color: #ffffff;
    margin-bottom: 10px; word-break: break-word;
    line-height: 1.35;
  }
  table.props { width: 100%; border-collapse: collapse; font-size: 11px; }
  table.props tr:nth-child(even) td { background: rgba(255,255,255,.05); }
  table.props td { padding: 4px 5px; vertical-align: top; border-bottom: 1px solid #252c42; }
  table.props td:first-child { color: #94a8cc; width: 42%; padding-right: 6px; font-weight: 500; }
  table.props td:last-child  { color: #ddeeff; word-break: break-all; font-family: monospace; font-size: 10.5px; }

  /* ── Legend ── */
  #legend {
    flex-shrink: 0; background: #0f1219;
    border-top: 1px solid #2d3348;
    padding: 6px 14px;
    display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center;
  }
  .legend-item { display: flex; align-items: center; gap: 5px; font-size: 10px; color: #7a8daa; }
  .legend-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 5px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #2d3348; border-radius: 3px; }
</style>
</head>
<body>

<header>
  <h1>CityGML Graph Viewer</h1>
  <span class="file">__FILENAME__</span>
  <div class="controls">
    <button id="btn-hier"  class="active" onclick="setLayout('hierarchical')">Hierarchical</button>
    <button id="btn-force"               onclick="setLayout('force')">Force</button>
    <button onclick="if(network) network.fit()">Fit</button>
    <button id="btn-freeze" style="display:none" onclick="toggleFreeze()">Freeze</button>
    <button id="btn-elabels" onclick="toggleEdgeLabels()">Edge Labels</button>
    <span style="width:1px;background:#3d4460;align-self:stretch;margin:4px 2px"></span>
    <button onclick="collapseAll()" title="Collapse everything">⊟ All</button>
    <button onclick="collapseOneLevel()" title="Collapse one more level from current frontier">⊟ −1</button>
    <button onclick="expandOneLevel()" title="Expand one level from each collapsed node">⊞ +1</button>
    <button onclick="expandAll()" title="Expand everything">⊞ All</button>
  </div>
</header>

<div class="main">
  <div id="graph-wrap">
    <div id="graph"></div>
  </div>
  <div id="sidebar">
    <div id="sidebar-header">
      <h2>Properties</h2>
      <p style="font-size:10px;color:#6a7d99;margin-bottom:6px">Click → inspect &nbsp;·&nbsp; Double-click → collapse/expand</p>
      <input id="search" type="text" placeholder="Search nodes by name or type…" oninput="filterNodes(this.value)">
    </div>
    <div id="props">
      <p class="empty">Click any node to inspect its properties.</p>
    </div>
  </div>
</div>

<div id="legend"></div>

<script>
// ── Data (injected by app.py) ────────────────────────────────────────────────
const RAW_NODES  = __NODES__;
const RAW_EDGES  = __EDGES__;
const TYPE_COLORS = __COLORS__;

// ── Legend ───────────────────────────────────────────────────────────────────
const legendEl = document.getElementById('legend');
Object.entries(TYPE_COLORS).forEach(([type, c]) => {
  const div = document.createElement('div');
  div.className = 'legend-item';
  div.innerHTML =
    `<div class="legend-dot" style="background:${c.background};border:1px solid ${c.border}"></div>`
    + `<span>${type}</span>`;
  legendEl.appendChild(div);
});

// ── vis.js DataSets ──────────────────────────────────────────────────────────
const nodesDS = new vis.DataSet(RAW_NODES.map(n => ({
  id:         n.id,
  label:      n.label,
  _baseLabel: n._baseLabel,
  group:      n.group,
  color:      n.color,
  size:       n.size,
  shape:      n.shape,
  font:       n.font,
  details:    n.details,
  children:   n.children || [],
  shadow:     { enabled: true, size: 10, x: 2, y: 3, color: 'rgba(0,0,0,.5)' },
})));

const edgesDS = new vis.DataSet(RAW_EDGES);

// ── Network factory ───────────────────────────────────────────────────────────
const COMMON_OPTS = {
  interaction: {
    hover: true,
    tooltipDelay: 80,
    navigationButtons: false,
    keyboard: { enabled: true, bindToWindow: false },
    zoomSpeed: 0.8,
  },
  nodes: { borderWidth: 2, borderWidthSelected: 3 },
  edges: { width: 1.5, selectionWidth: 3 },
};

function makeOpts(type) {
  if (type === 'hierarchical') {
    return Object.assign({}, COMMON_OPTS, {
      layout: {
        hierarchical: {
          enabled: true,
          direction: 'UD',
          sortMethod: 'directed',
          nodeSpacing: 150,
          levelSeparation: 110,
          treeSpacing: 220,
        },
      },
      physics: { enabled: false },
    });
  } else {
    return Object.assign({}, COMMON_OPTS, {
      layout: { hierarchical: { enabled: false }, randomSeed: 42 },
      physics: {
        enabled: true,
        solver: 'barnesHut',
        barnesHut: {
          gravitationalConstant: -8000,
          centralGravity: 0.25,
          springLength: 160,
          springConstant: 0.04,
          damping: 0.18,
          avoidOverlap: 0.5,
        },
        stabilization: { enabled: false },
      },
    });
  }
}

let network = null;
let currentLayout = 'hierarchical';

function createNetwork(type) {
  if (network) {
    network.destroy();
    network = null;
  }
  network = new vis.Network(
    document.getElementById('graph'),
    { nodes: nodesDS, edges: edgesDS },
    makeOpts(type)
  );
  attachEvents();
  if (type === 'hierarchical') {
    network.once('afterDrawing', () => {
      if (firstRender) { firstRender = false; autoCollapseAll(); }
      network.fit();
    });
    document.getElementById('btn-freeze').style.display = 'none';
  } else {
    // Let physics animate live; show Freeze button so user can stop it
    network.once('afterDrawing', () => {
      if (firstRender) { firstRender = false; autoCollapseAll(); }
      network.fit();
    });
    document.getElementById('btn-freeze').textContent = 'Freeze';
    document.getElementById('btn-freeze').style.display = '';
  }
}

// ── Node click → properties panel / double-click → collapse ────────────────
function attachEvents() {
  network.on('click', params => {
    if (!params.nodes.length) return;
    const node = nodesDS.get(params.nodes[0]);
    showProps(node);
    network.unselectAll();
  });
  network.on('doubleClick', params => {
    if (!params.nodes.length) return;
    toggleCollapse(params.nodes[0]);
    network.unselectAll();
  });
}

// ── Collapse / expand ─────────────────────────────────────────────────────────
// Map from nodeId → set of hidden descendant ids
const collapsedMap = new Map();

// Fixed: check visited BEFORE adding, not at start of call
function getDescendants(nodeId, visited = new Set()) {
  const node = nodesDS.get(nodeId);
  if (!node) return visited;
  for (const childId of (node.children || [])) {
    if (!visited.has(childId)) {
      visited.add(childId);
      getDescendants(childId, visited);
    }
  }
  return visited;
}

function toggleCollapse(nodeId) {
  const node = nodesDS.get(nodeId);
  if (!node || !(node.children && node.children.length)) return;

  if (collapsedMap.has(nodeId)) {
    // Expand: restore descendants not still hidden by another collapsed ancestor
    const hidden = collapsedMap.get(nodeId);
    collapsedMap.delete(nodeId);
    const nodeUpdates = [];
    const edgeUpdates = [];
    hidden.forEach(id => {
      const stillHidden = [...collapsedMap.values()].some(s => s.has(id));
      if (!stillHidden) {
        const child = nodesDS.get(id);
        // Restore badge label if this child is itself collapsed, else restore base
        const lbl = (collapsedMap.has(id) && child)
          ? child.label   // already has (+N) badge from when it was collapsed
          : (child && child._baseLabel) || (child && child.label) || '';
        nodeUpdates.push({ id, hidden: false, label: lbl });
      }
    });
    edgesDS.forEach(e => {
      if (hidden.has(e.from) || hidden.has(e.to)) {
        const stillHidden = [...collapsedMap.values()].some(s => s.has(e.from) || s.has(e.to));
        if (!stillHidden) edgeUpdates.push({ id: e.id, hidden: false });
      }
    });
    nodesDS.update(nodeUpdates);
    edgesDS.update(edgeUpdates);
    nodesDS.update([{ id: nodeId, label: node._baseLabel }]);
  } else {
    // Collapse: hide all descendants
    const descendants = getDescendants(nodeId);
    collapsedMap.set(nodeId, descendants);
    const nodeUpdates = [];
    const edgeUpdates = [];
    descendants.forEach(id => nodeUpdates.push({ id, hidden: true }));
    edgesDS.forEach(e => {
      if (descendants.has(e.from) || descendants.has(e.to)) {
        edgeUpdates.push({ id: e.id, hidden: true });
      }
    });
    nodesDS.update(nodeUpdates);
    edgesDS.update(edgeUpdates);
    const count = descendants.size;
    nodesDS.update([{ id: nodeId, label: (node._baseLabel || node.label) + `\n(+${count})` }]);
  }
  updateSharedLinkHighlights();
}

// ── Shared-link highlight (amber glow on collapsed nodes with visible connections) ──
const NORMAL_BORDER_WIDTH = 2;
const SHARED_BORDER_COLOR = '#f39c12';
const SHARED_BORDER_WIDTH = 5;

function updateSharedLinkHighlights() {
  // 1. Find all collapsed ancestor nodes that have >=1 edge touching a visible node
  const flagged = new Set();
  RAW_EDGES.forEach(e => {
    const fromNode = nodesDS.get(e.from);
    const toNode   = nodesDS.get(e.to);
    if (!fromNode || !toNode) return;
    const fromHidden = fromNode.hidden === true;
    const toHidden   = toNode.hidden   === true;
    // One side hidden, other visible → flag the collapsed ancestor
    if (fromHidden && !toHidden) {
      for (const [ancestorId, descendants] of collapsedMap) {
        if (descendants.has(e.from)) { flagged.add(ancestorId); break; }
      }
    }
    if (!fromHidden && toHidden) {
      for (const [ancestorId, descendants] of collapsedMap) {
        if (descendants.has(e.to)) { flagged.add(ancestorId); break; }
      }
    }
  });

  // 2. Update all collapsed nodes — glow if flagged, restore if not
  const updates = [];
  collapsedMap.forEach((_, id) => {
    const node = nodesDS.get(id);
    if (!node) return;
    if (flagged.has(id)) {
      updates.push({
        id,
        borderWidth: SHARED_BORDER_WIDTH,
        color: {
          background: node.color.background,
          border: SHARED_BORDER_COLOR,
          highlight: { background: node.color.background, border: '#fff' },
          hover:     { background: node.color.background, border: SHARED_BORDER_COLOR },
        },
        title: (node._baseLabel || node.label) + ' — has shared connections to visible nodes (double-click to expand)',
      });
    } else {
      // Restore original border
      updates.push({
        id,
        borderWidth: NORMAL_BORDER_WIDTH,
        color: node.color,
        title: undefined,
      });
    }
  });
  nodesDS.update(updates);

  // 3. Pulse animation: toggle borderWidth every 600ms for flagged nodes
  clearInterval(window._pulseTimer);
  if (flagged.size > 0) {
    let tick = false;
    window._pulseTimer = setInterval(() => {
      tick = !tick;
      const pulseUpdates = [];
      flagged.forEach(id => {
        if (collapsedMap.has(id)) {
          pulseUpdates.push({ id, borderWidth: tick ? SHARED_BORDER_WIDTH : SHARED_BORDER_WIDTH + 3 });
        }
      });
      nodesDS.update(pulseUpdates);
    }, 600);
  }
}

// ── Auto-collapse on first load ─────────────────────────────────────────
let firstRender = true;
function autoCollapseAll() {
  // Collapse every node that has children, deepest first, so badges are accurate
  // Build a topological order (BFS from roots) then reverse for deepest-first collapse
  const order = [];
  const roots = [];
  nodesDS.forEach(n => {
    // Find nodes with no incoming edges (roots)
    const hasParent = RAW_EDGES.some(e => e.to === n.id);
    if (!hasParent) roots.push(n.id);
  });
  const seen = new Set(roots);
  const queue = [...roots];
  while (queue.length) {
    const id = queue.shift();
    order.push(id);
    const node = nodesDS.get(id);
    if (!node) continue;
    for (const childId of (node.children || [])) {
      if (!seen.has(childId)) { seen.add(childId); queue.push(childId); }
    }
  }
  // Collapse deepest first so parent badges count correctly
  for (let i = order.length - 1; i >= 0; i--) {
    const node = nodesDS.get(order[i]);
    if (node && node.children && node.children.length) toggleCollapse(order[i]);
  }
}

createNetwork('hierarchical');

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function showProps(node) {
  const propsEl = document.getElementById('props');
  const c = TYPE_COLORS[node.group] || { background: '#aaa', border: '#888', font: '#000' };
  const details = node.details || {};
  const rows = Object.entries(details)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => {
      const val = typeof v === 'object' ? JSON.stringify(v) : String(v);
      return `<tr><td>${esc(k)}</td><td>${esc(val)}</td></tr>`;
    }).join('');

  propsEl.innerHTML = `
    <div class="type-badge" style="background:${c.background};color:#fff;border:1px solid ${c.border};text-shadow:0 1px 2px rgba(0,0,0,0.7)">
      ${esc(node.group)}
    </div>
    <div class="node-name">${esc(node.label.split('\\n').join(' '))}</div>
    ${rows
      ? `<table class="props">${rows}</table>`
      : '<p class="empty">No properties.</p>'
    }
  `;
}

// ── Layout switching ─────────────────────────────────────────────────────────
function setLayout(type) {
  if (type === currentLayout) return;
  currentLayout = type;
  document.getElementById('btn-hier').classList.toggle('active', type === 'hierarchical');
  document.getElementById('btn-force').classList.toggle('active', type === 'force');
  createNetwork(type);
}

// ── Edge label toggle ────────────────────────────────────────────────────────
let edgeLabelsOn = false;
function toggleEdgeLabels() {
  edgeLabelsOn = !edgeLabelsOn;
  document.getElementById('btn-elabels').classList.toggle('active', edgeLabelsOn);
  const updates = edgesDS.map(e => ({ id: e.id, label: edgeLabelsOn ? (e._label || '') : '' }));
  edgesDS.update(updates);
}

// ── Bulk collapse / expand helpers ────────────────────────────────────────────

// Returns BFS-ordered list of all node ids from roots downward
function bfsOrder() {
  const order = [];
  const roots = [];
  nodesDS.forEach(n => { if (!RAW_EDGES.some(e => e.to === n.id)) roots.push(n.id); });
  const seen = new Set(roots);
  const queue = [...roots];
  while (queue.length) {
    const id = queue.shift();
    order.push(id);
    const node = nodesDS.get(id);
    if (!node) continue;
    for (const c of (node.children || [])) {
      if (!seen.has(c)) { seen.add(c); queue.push(c); }
    }
  }
  return order;
}

function collapseAll() {
  // Collapse deepest-first so badges are accurate
  const order = bfsOrder();
  for (let i = order.length - 1; i >= 0; i--) {
    const n = nodesDS.get(order[i]);
    if (n && n.children && n.children.length && !collapsedMap.has(order[i])) {
      toggleCollapse(order[i]);
    }
  }
}

function expandAll() {
  // Expand shallowest-first
  const order = bfsOrder();
  for (const id of order) {
    if (collapsedMap.has(id)) toggleCollapse(id);
  }
}

function expandOneLevel() {
  // Expand only the collapsed nodes currently visible (not themselves hidden)
  const toExpand = [];
  collapsedMap.forEach((_, id) => {
    const n = nodesDS.get(id);
    if (n && !n.hidden) toExpand.push(id);
  });
  for (const id of toExpand) toggleCollapse(id);
}

function collapseOneLevel() {
  // Find the deepest visible nodes that have children and collapse them
  // "deepest" = no child is currently visible
  const order = bfsOrder();
  const toCollapse = [];
  for (const id of order) {
    const n = nodesDS.get(id);
    if (!n || n.hidden || collapsedMap.has(id)) continue;
    if (!n.children || !n.children.length) continue;
    // Collapse if none of its children are currently visible
    const anyChildVisible = (n.children || []).some(cid => {
      const c = nodesDS.get(cid);
      return c && !c.hidden;
    });
    if (!anyChildVisible) continue; // already collapsed or no children
    // Only collapse leaves of the visible frontier:
    // a node is a frontier leaf if ALL its visible children have no visible children
    const isLeaf = (n.children || []).every(cid => {
      const c = nodesDS.get(cid);
      if (!c || c.hidden) return true;
      return !c.children || !c.children.length || collapsedMap.has(cid) ||
        (c.children || []).every(gc => { const g = nodesDS.get(gc); return !g || g.hidden; });
    });
    if (isLeaf) toCollapse.push(id);
  }
  for (const id of toCollapse) toggleCollapse(id);
}

// ── Freeze / resume physics ─────────────────────────────────────────────────
let frozen = false;
function toggleFreeze() {
  if (!network) return;
  frozen = !frozen;
  network.setOptions({ physics: { enabled: !frozen } });
  document.getElementById('btn-freeze').textContent = frozen ? 'Resume' : 'Freeze';
  document.getElementById('btn-freeze').classList.toggle('active', frozen);
}

// ── Search / filter ───────────────────────────────────────────────────────────
function filterNodes(query) {
  const q = query.trim().toLowerCase();
  nodesDS.forEach(n => {
    const match = !q
      || n.label.toLowerCase().includes(q)
      || (n.group || '').toLowerCase().includes(q);
    nodesDS.update({ id: n.id, hidden: !match });
  });
}


</script>
</body>
</html>
"""


# ── Generator ─────────────────────────────────────────────────────────────────

def generate_html(model, gml_file, filename):
    graph = build_graph(model, gml_file)
    colors = {
        k: {"background": v["bg"], "border": v["border"], "font": v["font"]}
        for k, v in TYPE_STYLE.items()
    }
    html = HTML_TEMPLATE
    html = html.replace("__FILENAME__", filename)
    html = html.replace("__NODES__",  json.dumps(graph["nodes"], ensure_ascii=False))
    html = html.replace("__EDGES__",  json.dumps(graph["edges"], ensure_ascii=False))
    html = html.replace("__COLORS__", json.dumps(colors,         ensure_ascii=False))
    return html


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="CityGML interactive graph viewer")
    ap.add_argument("file",          help="Path to .gml file")
    ap.add_argument("--out",         default="viewer.html", help="Output HTML path (default: viewer.html)")
    ap.add_argument("--serve",       action="store_true",   help="Serve via HTTP and open in browser")
    ap.add_argument("--port",        type=int, default=8080, help="HTTP port for --serve (default: 8080)")
    ap.add_argument("--no-open",     action="store_true",   help="Don't auto-open the browser")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing {path.name}…")
    model = parse_file(str(path))
    html  = generate_html(model, str(path), path.name)

    out = Path(args.out)
    out.write_text(html, encoding="utf-8")
    print(f"Viewer written → {out.resolve()}")

    if args.serve:
        import os
        os.chdir(out.parent)

        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, fmt, *a):
                pass

        server = http.server.HTTPServer(("localhost", args.port), Handler)
        url = f"http://localhost:{args.port}/{out.name}"
        print(f"Serving at {url}  (Ctrl-C to stop)")
        if not args.no_open:
            threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        if not args.no_open:
            abs_url = out.resolve().as_uri()
            print(f"Opening {abs_url}")
            webbrowser.open(abs_url)


if __name__ == "__main__":
    main()
