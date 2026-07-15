"""LCA ADE 1.0 parser.

Namespace: http://www.citygml.org/ade/lca/1.0  (prefix: lca)

Injects LCA reference data as sibling elements onto Energy ADE objects
and at the building level.

Elements recognised
───────────────────
On energy:SolidMaterial / energy:Gas / nrg3:SolidMaterial / nrg3:Gas:
  lca:environmentalId          — Boverket (or other EPD DB) ResourceId
  lca:referenceServiceLife  uom="a"  — RSL in years
  lca:gwp                   uom="kgCO2eq"  — optional inline GWP

On bldg:Building:
  lca:referenceStudyPeriod  uom="a"  — system boundary in years
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .base import NS, _gml_id, text_of

LCA_ADE_URI = "http://www.citygml.org/ade/lca/1.0"

_MATERIAL_LOCALS = frozenset({"SolidMaterial", "Gas"})
_DEVICE_LOCALS = frozenset({
    "GenericDevice", "HeatPump", "CombinedHeatPower",
    "ElectricalAppliances", "LightingFacilities",
})


def _lca_props(el: ET.Element) -> dict:
    """Return any lca: properties found as direct children of *el*.

    Unit-of-measure attributes (uom) are folded into the value string
    (e.g. "50 a") rather than emitted as separate rows.
    """
    props: dict = {}

    env_id = text_of(el, "lca:environmentalId")
    if env_id:
        props["lca:environmentalId"] = env_id

    rsl_el = el.find("lca:referenceServiceLife", NS)
    if rsl_el is not None and rsl_el.text and rsl_el.text.strip():
        uom = rsl_el.get("uom")
        val = rsl_el.text.strip()
        props["lca:referenceServiceLife"] = f"{val} {uom}".strip() if uom else val

    gwp_el = el.find("lca:gwp", NS)
    if gwp_el is not None and gwp_el.text and gwp_el.text.strip():
        uom = gwp_el.get("uom")
        val = gwp_el.text.strip()
        props["lca:gwp"] = f"{val} {uom}".strip() if uom else val

    return props


# ── Building enrichment ───────────────────────────────────────────────────────

def enrich_building(el: ET.Element, building: dict) -> None:
    """Add material-level LCA data in-place to a building dict (no RSP here)."""
    pass  # RSP is at CityModel level; material props come via collect_global_objects


def enrich_model(root: ET.Element, model: dict) -> None:
    """Add CityModel-level LCA data (referenceStudyPeriod) to the model dict."""
    rsp_el = root.find("lca:referenceStudyPeriod", NS)
    if rsp_el is not None and rsp_el.text and rsp_el.text.strip():
        uom = rsp_el.get("uom")
        val = rsp_el.text.strip()
        model.setdefault("lca", {})["referenceStudyPeriod"] = (
            f"{val} {uom}".strip() if uom else val
        )


# ── Global object collector ───────────────────────────────────────────────────

def collect_global_objects(root: ET.Element) -> dict:
    """Return {gml_id: lca_props} for all materials/devices with lca: children."""
    result: dict = {}
    for el in root.iter():
        local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if local not in (_MATERIAL_LOCALS | _DEVICE_LOCALS):
            continue
        props = _lca_props(el)
        if props:
            gml_id = _gml_id(el)
            if gml_id:
                result[gml_id] = props
    return result

