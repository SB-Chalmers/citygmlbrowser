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
}

REFERENCE_STUDY_PERIOD = "50"  # years, applied to every building

_GML_ID_ATTRS = (
    "{http://www.opengis.net/gml}id",
    "{http://www.opengis.net/gml/3.2}id",
)
_MATERIAL_LOCALS = {"SolidMaterial", "Gas"}
_BUILDING_LOCAL = "Building"

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


def inject(root: ET.Element) -> tuple[int, int]:
    mats_done = 0
    bldgs_done = 0

    for el in root.iter():
        local = _local(el.tag)

        if local in _MATERIAL_LOCALS:
            mapping = MATERIAL_MAP.get(_gml_id(el) or "")
            if mapping is None:
                continue
            resource_id, rsl = mapping
            env = ET.SubElement(el, _lca("environmentalId"))
            env.text = resource_id
            life = ET.SubElement(el, _lca("referenceServiceLife"))
            life.set("uom", "a")
            life.text = rsl
            mats_done += 1

        elif local == _BUILDING_LOCAL:
            pass   # RSP is on CityModel, not Building

        elif local == "CityModel":
            rsp = ET.Element(_lca("referenceStudyPeriod"))
            rsp.set("uom", "a")
            rsp.text = REFERENCE_STUDY_PERIOD
            el.insert(0, rsp)   # first child of CityModel
            bldgs_done += 1     # counter reused for RSP injections

    return mats_done, bldgs_done


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

    mats, bldgs = inject(root)

    tree.write(out_path, xml_declaration=True, encoding="UTF-8")
    print(f"Wrote {out_path}: injected {mats} material(s), {bldgs} building(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
