"""LCA ADE 1.0 parser.

Namespace: http://sb.chalmers.se/ade/lca/1.0  (prefix: lca)

Recognises LCA reference data injected as sibling elements onto Energy ADE
objects, CityGML construction assemblies, installations, and operational
resources.

LCA ADE elements
────────────────
Two properties attach to any supported target element as direct children:

  lca:environmentalId  source="<db>"  — EPD database record ID (string).
      source attribute values: "boverket" | "oekobaudat"

  lca:referenceServiceLife  uom="a"   — reference service life in years (int).
      Basis for replacement-cycle calculation in the LCA model (EN 15978 B4).

One scenario-level property lives in the top-level lca:LCAScenario city object
(wrapped in a core:cityObjectMember):

  lca:referenceStudyPeriod  uom="a"  — system boundary horizon in years (int).

Coverage — XSD-derived target elements
──────────────────────────────────────
MATERIALS (nrg3:AbstractMaterial subclasses — Energy ADE 3.0 XSD confirmed)
  SolidMaterial, Gas
  Use for individual material layers in opaque constructions.
  NOTE: nrg3:SolidMaterial already carries embodiedCarbon / embodiedEnergy
  as first-class nrg3 properties; lca:environmentalId links to the full EPD.

CONSTRUCTION ASSEMBLIES (nrg3:AbstractLayeredConstruction subclasses)
  LayeredConstruction, ReverseLayeredConstruction
  Use for whole-unit product EPDs: window glazing systems, prefabricated door
  units, curtain-wall panels, or other assemblies where the EPD covers the
  product as a single unit. Do NOT combine with material-level EPDs on the
  same construction’s layers (double-counting).

DEVICES (nrg3:AbstractDevice subclasses — Energy ADE 3.0 XSD confirmed)
  Boiler, HeatPump,
  PhotovoltaicCollector, PhotovoltaicThermalCollector,
  SolarThermalCollector, GenericSolarCollector,
  ElectricalStorageDevice, ThermalStorageDevice,
  LightingDevice, MovableShadingDevice,
  GenericDevice, GenericElectricalDevice

INSTALLATIONS (CityGML 2.0 bldg: / 3.0 bldg3: — not in nrg3 XSD)
  BuildingInstallation, IntBuildingInstallation
  Use for non-energy-ADE built-in components: sanitary fittings, elevators,
  staircases, balconies, and other fixed building equipment.

RESOURCES (nrg3:AbstractResource subclasses — Energy ADE 3.0 XSD confirmed)
  Energy, Water, Food, Waste,
  ConstructionMaterial, OtherResource, UrbanSpace
  Use for operational flows whose embodied impact (e.g. carrier-specific CO₂
  factors) should be traceable to an EPD or environmental dataset record.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .base import NS, _gml_id, text_of

LCA_ADE_URI = "http://sb.chalmers.se/ade/lca/1.0"

_MATERIAL_LOCALS = frozenset({"SolidMaterial", "Gas"})
_CONSTRUCTION_LOCALS = frozenset({
    # Energy ADE 2.0 construction object
    "Construction",
    # nrg3 construction assembly objects — for whole-unit product EPDs.
    # Typical targets: window glazing systems, prefabricated door units.
    # Every CityObject in Energy ADE 3.0 can reference an AbstractLayeredConstruction,
    # so this covers any construction-level EPD not expressed at material level.
    "LayeredConstruction", "ReverseLayeredConstruction",
})
_INSTALLATION_LOCALS = frozenset({
    # CityGML 2.0 bldg: / CityGML 3.0 bldg3: building installations.
    # Covers non-energy-ADE built-in components: sanitary fittings, elevators,
    # staircases, balconies, and other building equipment not in the Devices module.
    "BuildingInstallation", "IntBuildingInstallation",
})
_RESOURCE_LOCALS = frozenset({
    # nrg3 AbstractResource subclasses (Resources module)
    "Energy", "Water", "Food", "Waste",
    "ConstructionMaterial", "OtherResource", "UrbanSpace",
})
_DEVICE_LOCALS = frozenset({
    # ── Energy ADE 3.0 XSD-confirmed concrete device types ────────────────────
    # Heating / cooling
    "Boiler", "HeatPump",
    # Solar (AbstractSolarCollector subclasses)
    "PhotovoltaicCollector", "PhotovoltaicThermalCollector",
    "SolarThermalCollector", "GenericSolarCollector",
    # Storage
    "ElectricalStorageDevice", "ThermalStorageDevice",
    # Lighting & shading
    "LightingDevice", "MovableShadingDevice",
    # Generic catch-alls
    "GenericDevice", "GenericElectricalDevice",
})


def _lca_props(el: ET.Element) -> dict:
    """Return any lca: properties found as direct children of *el*.

    Uses el.find() (path-based lookup) rather than positional indexing, so
    this function is robust to element ordering. In Energy ADE 3.0 beta8,
    materials/constructions/resources/devices all use formal CityObject-hook
    ordering (LCA properties before Energy ADE-specific children). Legacy
    beta7 exports may still place some properties by convention at the end;
    el.find() locates either representation.

    Unit-of-measure attributes (uom) are folded into the value string
    (e.g. "50 a") rather than emitted as separate rows.
    """
    props: dict = {}

    env_el = el.find("lca:environmentalId", NS)
    if env_el is not None and env_el.text and env_el.text.strip():
        props["lca:environmentalId"] = env_el.text.strip()
        source = env_el.get("source")
        if source:
            props["lca:environmentalIdSource"] = source

    rsl_el = el.find("lca:referenceServiceLife", NS)
    if rsl_el is not None and rsl_el.text and rsl_el.text.strip():
        uom = rsl_el.get("uom")
        val = rsl_el.text.strip()
        props["lca:referenceServiceLife"] = f"{val} {uom}".strip() if uom else val

    return props


# ── Building enrichment ───────────────────────────────────────────────────────

def enrich_building(el: ET.Element, building: dict) -> None:
    """Add material-level LCA data in-place to a building dict (no RSP here)."""
    pass  # RSP is at CityModel level; material props come via collect_global_objects


def enrich_model(root: ET.Element, model: dict) -> None:
    """Add CityModel-level LCA data (referenceStudyPeriod) to the model dict.

    Reads from the first lca:LCAScenario found anywhere in the document
    (expected as a core:cityObjectMember top-level element).
    """
    for scenario_el in root.iter(f"{{{LCA_ADE_URI}}}LCAScenario"):
        rsp_el = scenario_el.find("lca:referenceStudyPeriod", NS)
        if rsp_el is not None and rsp_el.text and rsp_el.text.strip():
            uom = rsp_el.get("uom")
            val = rsp_el.text.strip()
            model.setdefault("lca", {})["referenceStudyPeriod"] = (
                f"{val} {uom}".strip() if uom else val
            )
        break  # only the first LCAScenario is used


# ── Global object collector ───────────────────────────────────────────────────

def collect_global_objects(root: ET.Element) -> dict:
    """Return {gml_id: lca_props} for all elements with lca: children.

    Covers: materials, construction assemblies, devices, building
    installations, and operational resources (AbstractResource subclasses).
    """
    _non_material = _CONSTRUCTION_LOCALS | _DEVICE_LOCALS | _INSTALLATION_LOCALS | _RESOURCE_LOCALS
    _all_locals = _MATERIAL_LOCALS | _non_material

    result: dict = {}
    for el in root.iter():
        local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if local not in _all_locals:
            continue
        props = _lca_props(el)
        if props:
            gml_id = _gml_id(el)
            if gml_id:
                # Tag non-material objects so the graph builder can type them
                if local in _non_material:
                    props["_class"] = local
                    props["name"] = (
                        text_of(el, "gml:name") or
                        text_of(el, "gml32:name") or
                        gml_id
                    )
                result[gml_id] = props
    return result

