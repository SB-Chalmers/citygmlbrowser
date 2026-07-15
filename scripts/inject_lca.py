"""inject_lca.py — Inject LCA ADE 1.0 attributes into a CityGML + Energy ADE file.

Usage:
    python scripts/inject_lca.py <input.gml> <output.gml>

Adds, to every energy:SolidMaterial / energy:Gas element with a mapped gml:id:
    <lca:environmentalId>            Boverket Klimatdatabas ResourceId
    <lca:referenceServiceLife uom="a">   Reference Service Life (years)

Adds, to every bldg:Building element:
    <lca:referenceStudyPeriod uom="a">   study-period system boundary (years)

The LCA ADE namespace is http://www.citygml.org/ade/lca/1.0 (prefix "lca").
Only elements listed in MATERIAL_MAP are touched; unknown materials are skipped.
Uses only the Python standard library (xml.etree.ElementTree).
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

# ── LCA ADE namespace ─────────────────────────────────────────────────────────
LCA_NS  = "http://www.citygml.org/ade/lca/1.0"
LCA_PRE = "lca"

# gml:id -> (boverket_resource_id, reference_service_life_years)
# ResourceIds are real matches from the Boverket Klimatdatabas v2 (closest
# equivalents). RSL values are derived from each resource's RefServiceLifeNormal.
# The air gap (Luftschicht, a Gas) has no embodied carbon and is intentionally
# left unmapped.
MATERIAL_MAP: dict[str, tuple[str, str]] = {
    # ── FZK Haus (CityGML 2.0 + Energy ADE 2.0) ──────────────────────────
    "KIT-FZK-Haus-Beton-Bodenplatte":         ("6000000029", "50"),  # Ready-mix concrete C25/30
    "KIT-FZK-Haus-Bitumendachbahn":           ("6000000141", "40"),  # Bitumen membrane, single layer
    "KIT-FZK-Haus-Gipskarton":                ("6000000020", "50"),  # Gypsum standard plasterboard
    "KIT-FZK-Haus-Holz-Dach":                 ("6000000007", "50"),  # Sawn timber, coniferous
    "KIT-FZK-Haus-Holz-Tuer":                 ("6000000118", "50"),  # Door, external, wood
    "KIT-FZK-Haus-Polyethylenfolie":          ("6000000198", "50"),  # Plastic film, vapor barrier
    "KIT-FZK-Haus-Polystyrol-Extruderschaum": ("6000000132", "50"),  # XPS
    "KIT-FZK-Haus-Polystyrol-Partikelschaum": ("6000000131", "50"),  # EPS
    "KIT-FZK-Haus-Porenbeton":                ("6000000096", "50"),  # Autoclaved Aerated Concrete
    "KIT-FZK-Haus-Putz-Aussen":               ("6000000091", "50"),  # Masonry/plastering mortar B (CS III)
    "KIT-FZK-Haus-Putz-Innen":                ("6000000092", "50"),  # Plastering/masonry mortar C (CS II)
    "KIT-FZK-Haus-ZementEstrich":             ("6000000098", "50"),  # Floor screed < 17% cement
    "KIT-FZK-Haus-Ziegel":                    ("6000000082", "50"),  # Bricks

    # ── Alderaan (CityGML 2.0 + Energy ADE 3.0) ──────────────────────────
    # Matched to Boverket closest equivalents by conductivity & density.
    # Gases (id_gas_1, id_gas_2) are intentionally left unmapped.
    "id_solid_material_1":  ("6000000029", "50"),  # λ=3.5  ρ=2500 → concrete C25/30
    "id_solid_material_2":  ("6000000098", "50"),  # λ=1.4  ρ=2000 → floor screed <17% cement
    "id_solid_material_3":  ("6000000131", "50"),  # λ=0.04 ρ=20   → EPS
    "id_solid_material_4":  ("6000000092", "50"),  # λ=0.23 ρ=1100 → plastering mortar C
    "id_solid_material_5":  ("6000000029", "50"),  # λ=2.3  ρ=2300 → concrete C25/30
    "id_solid_material_6":  ("6000000092", "50"),  # λ=0.7  ρ=1400 → plastering mortar C
    "id_solid_material_7":  ("6000000091", "50"),  # λ=0.8  ρ=1800 → masonry mortar B
    "id_solid_material_9":  ("6000000001", "50"),  # λ=0.035 ρ=20  → glasswool, batts & rolls
    "id_solid_material_10": ("6000000091", "50"),  # λ=0.87 ρ=1800 → masonry mortar B
    "id_solid_material_11": ("6000000092", "50"),  # λ=0.7  ρ=1400 → plastering mortar C
    "id_solid_material_12": ("6000000029", "50"),  # λ=2.3  ρ=2400 → concrete C25/30
    "id_solid_material_14": ("6000000125", "50"),  # λ=0.04 ρ=110  → stone wool, facade board
    "id_solid_material_15": ("6000000092", "50"),  # λ=0.23 ρ=1100 → plastering mortar C
    "id_solid_material_16": ("6000000092", "50"),  # λ=0.7  ρ=1400 → plastering mortar C
    "id_solid_material_17": ("6000000091", "50"),  # λ=0.8  ρ=1800 → masonry mortar B
    "id_solid_material_18": ("6000000092", "50"),  # λ=0.7  ρ=1400 → plastering mortar C
}

REFERENCE_STUDY_PERIOD = "50"  # years, applied to every building

_GML_ID_ATTRS = (
    "{http://www.opengis.net/gml}id",
    "{http://www.opengis.net/gml/3.2}id",
)
_MATERIAL_LOCALS = {"SolidMaterial", "Gas"}
_BUILDING_LOCAL = "Building"

# Device type (XML local name) → (env_id, rsl_years, source)
# source is "boverket" | "oekobaudat" | "placeholder"
# RSL values follow EN 15978 typical service-life assumptions.
# Ökobaudat UUIDs verified to have A1-A3 Climate Change data (2026-07).
DEVICE_TYPE_MAP: dict[str, tuple[str, str, str]] = {
    # ── Confirmed Ökobaudat EPDs (A1-A3 verified) ─────────────────────────────
    "Boiler":                 ("fe91b985-60da-45dc-b3fd-29b9e632d49f", "20", "oekobaudat"),
    #                          Gas-Brennwertgerät 120-400 kW (Standgerät)
    "HeatPump":               ("1cd6b257-a4f8-4509-a83b-492cd34c7d98", "20", "oekobaudat"),
    #                          Strom-Wärmepumpe (Luft-Wasser) 14 kW
    "CombinedHeatPower":      ("98471e41-8d40-4f09-8b08-af2a8489f6cf", "20", "oekobaudat"),
    #                          Gas Blockheizkraftwerk 500 kW
    "ChillerUnit":            ("cc071698-9d73-4315-b470-e13dfcdba10a", "15", "oekobaudat"),
    #                          Kältemaschine 500 kW
    "LightingDevice":         ("6293ec16-2f99-4620-a032-fd6e57912a6c", "15", "oekobaudat"),
    #                          Rasterleuchte 2×T8-36W (LFL)
    "ThermalStorageDevice":   ("1aa165a1-32ca-461a-a006-3736d3c9c8e2", "20", "oekobaudat"),
    #                          Pufferspeicher (Edelstahl)
    "ElectricalStorageDevice": ("5b430e64-fcd6-42b6-9b2a-18661249a335", "15", "oekobaudat"),
    #                          Lithium Eisenphosphat (LFP) Batterie (1 kWh)
    "AirDistributionSystem":  ("40edb030-3b81-47f6-a24f-acd8b2be0d20", "25", "oekobaudat"),
    #                          Lüftungskanal (verzinktes Stahlblech)

    # ── Boverket EPD ──────────────────────────────────────────────────────────
    "PhotovoltaicCollector":  ("6000000203", "30", "boverket"),
    #                          Photovoltaic cells, mono-Si

    # ── Placeholder (no suitable EPD found in Boverket or Ökobaudat) ─────────
    "HeatExchanger":          ("DEV-HEX-01",        "20", "placeholder"),
    # No generic residential heat exchanger EPD in Ökobaudat; closest is
    # Übergabestation Fernwärme (61aad695) but that is district-heating-specific.
    "SolarThermalCollector":  ("413ba0ce-2a78-44e2-89d2-d9adfd4e492c", "25", "oekobaudat"),
    #                          Flat solar collector  (A1-A3=95.6 kgCO₂eq)
    "GenericSolarCollector":  ("413ba0ce-2a78-44e2-89d2-d9adfd4e492c", "25", "oekobaudat"),
    #                          Flat solar collector  (same generic proxy)
    "LightingFacilities":     ("cbd2e78d-8930-4214-9715-553cee8e376e", "15", "oekobaudat"),
    #                          RS PRO R-Series (Steinel GmbH) presence sensor light
    "ElectricalAppliances":   ("DEV-ELAPP-01",      "10", "placeholder"),
    "GenericElectricalDevice": ("DEV-ELGN-01",      "15", "placeholder"),
    "GenericDevice":          ("DEV-GN-01",         "15", "placeholder"),
    "MovableShadingDevice":   ("650a4800-0bc1-4d1e-b673-85e05cfc2310", "15", "oekobaudat"),
    #                          Außenliegender Raffstore (exterior roller blind)
    "MechanicalVentilation":  ("8159a95f-3224-4b8a-8eab-1590eeaefe6a", "20", "oekobaudat"),
    #                          SIEGENIA AEROMAT VT decentralised HRV ventilation unit
}

# Register the common CityGML / Energy ADE prefixes so ElementTree preserves
# readable prefixes on output instead of emitting ns0:, ns1:, …
_NAMESPACE_PREFIXES = {
    "core":   "http://www.opengis.net/citygml/2.0",
    "core3":  "http://www.opengis.net/citygml/3.0",
    "bldg":   "http://www.opengis.net/citygml/building/2.0",
    "bldg3":  "http://www.opengis.net/citygml/building/3.0",
    "con":    "http://www.opengis.net/citygml/construction/3.0",
    "gen":    "http://www.opengis.net/citygml/generics/2.0",
    "gml":    "http://www.opengis.net/gml",
    "gml32":  "http://www.opengis.net/gml/3.2",
    "energy": "http://www.sig3d.org/citygml/2.0/energy/2.0",
    "nrg3":   "http://www.citygml.org/ade/energy/3.0",
    "app":    "http://www.opengis.net/citygml/appearance/2.0",
    "xAL":    "urn:oasis:names:tc:ciq:xsdschema:xAL:2.0",
    "xlink":  "http://www.w3.org/1999/xlink",
    # Extra CityGML 2.0 modules present in Alderaan
    "frn":    "http://www.opengis.net/citygml/cityfurniture/2.0",
    "grp":    "http://www.opengis.net/citygml/cityobjectgroup/2.0",
    "veg":    "http://www.opengis.net/citygml/vegetation/2.0",
    "brid":   "http://www.opengis.net/citygml/bridge/2.0",
    "dem":    "http://www.opengis.net/citygml/relief/2.0",
    "tran":   "http://www.opengis.net/citygml/transportation/2.0",
    "tun":    "http://www.opengis.net/citygml/tunnel/2.0",
    "wtr":    "http://www.opengis.net/citygml/waterbody/2.0",
    "luse":   "http://www.opengis.net/citygml/landuse/2.0",
    LCA_PRE:  LCA_NS,
}


def _gml_id(el: ET.Element) -> str | None:
    for attr in _GML_ID_ATTRS:
        v = el.get(attr)
        if v:
            return v
    return None


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _lca(name: str) -> str:
    return f"{{{LCA_NS}}}{name}"


def inject(root: ET.Element) -> tuple[int, int, int]:
    mats_done = 0
    devs_done = 0
    bldgs_done = 0

    for el in root.iter():
        local = _local(el.tag)

        if local in _MATERIAL_LOCALS:
            mapping = MATERIAL_MAP.get(_gml_id(el) or "")
            if mapping is None:
                continue
            resource_id, rsl = mapping
            env = ET.SubElement(el, _lca("environmentalId"))
            env.set("source", "boverket")
            env.text = resource_id
            life = ET.SubElement(el, _lca("referenceServiceLife"))
            life.set("uom", "a")
            life.text = rsl
            mats_done += 1

        elif local in DEVICE_TYPE_MAP:
            resource_id, rsl, src = DEVICE_TYPE_MAP[local]
            env = ET.SubElement(el, _lca("environmentalId"))
            env.set("source", src)
            env.text = resource_id
            life = ET.SubElement(el, _lca("referenceServiceLife"))
            life.set("uom", "a")
            life.text = rsl
            devs_done += 1

        elif local == "CityModel":
            rsp = ET.Element(_lca("referenceStudyPeriod"))
            rsp.set("uom", "a")
            rsp.text = REFERENCE_STUDY_PERIOD
            el.insert(0, rsp)   # first child of CityModel
            bldgs_done += 1     # counter reused for RSP injections

    return mats_done, devs_done, bldgs_done


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2

    in_path, out_path = argv[1], argv[2]

    # Preserve readable prefixes on output (avoids ns0:, ns1:, …)
    for prefix, uri in _NAMESPACE_PREFIXES.items():
        ET.register_namespace(prefix, uri)

    tree = ET.parse(in_path)
    root = tree.getroot()

    mats, devs, rsps = inject(root)

    tree.write(out_path, xml_declaration=True, encoding="UTF-8")
    print(f"Wrote {out_path}: injected {mats} material(s), {devs} device(s), {rsps} RSP(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
