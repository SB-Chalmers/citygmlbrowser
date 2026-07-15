from __future__ import annotations

from dataclasses import dataclass
import xml.etree.ElementTree as ET

CITYGML_2_URI = "http://www.opengis.net/citygml/2.0"
CITYGML_3_URI = "http://www.opengis.net/citygml/3.0"
ENERGY_ADE_2_URI = "http://www.sig3d.org/citygml/2.0/energy/2.0"
ENERGY_ADE_3_URI = "http://www.citygml.org/ade/energy/3.0"
LCA_ADE_URI      = "http://sb.chalmers.se/ade/lca/1.0"


@dataclass(frozen=True)
class DialectInfo:
    citygml: str | None
    energy_ade: str | None
    lca_ade: str | None
    namespaces: list[str]


def _detect_energy_ade_version(uri: str) -> str | None:
    if uri == ENERGY_ADE_2_URI:
        return "2.0"
    if uri == ENERGY_ADE_3_URI:
        return "3.0"

    lowered = uri.lower()
    if "energy" not in lowered:
        return None

    if "citygml/3.0" in lowered or "/3.0/energy" in lowered or "energy/3.0" in lowered:
        return "3.0"
    if "citygml/2.0" in lowered or "/2.0/energy" in lowered or "energy/2.0" in lowered:
        return "2.0"

    return "unknown"


def detect_dialect(path: str) -> DialectInfo:
    namespaces: set[str] = set()

    parser = ET.iterparse(path, events=("start", "start-ns"))
    for event, element in parser:
        if event == "start-ns":
            _prefix, uri = element
            namespaces.add(uri)
            continue
        if event == "start":
            break

    citygml_version: str | None = None
    if CITYGML_3_URI in namespaces:
        citygml_version = "3.0"
    elif CITYGML_2_URI in namespaces:
        citygml_version = "2.0"

    energy_ade_version: str | None = None
    for uri in namespaces:
        v = _detect_energy_ade_version(uri)
        if v:
            energy_ade_version = v
            if v in {"2.0", "3.0"}:
                break

    lca_ade_version: str | None = "1.0" if LCA_ADE_URI in namespaces else None

    return DialectInfo(
        citygml=citygml_version,
        energy_ade=energy_ade_version,
        lca_ade=lca_ade_version,
        namespaces=sorted(namespaces),
    )
