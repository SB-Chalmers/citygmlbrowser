"""calculate_lca.py — Embodied LCA: modules A1-A3, A4, A5.

Usage:
    PYTHONPATH=. python scripts/calculate_lca.py models/FZKHouseLoD3-LCA.gml

Iterates every thermal boundary → construction → layer → material and
computes A1-A3 + A4 + A5.1 embodied carbon using Boverket GWP factors.

Formula per layer
-----------------
base_mass    = boundary_area × layer_thickness × material_density          [kg]
procured     = base_mass × WasteFactor                                      [kg]
A1_A3        = procured × GWP_A1A3                               [kg CO2eq]
A4           = procured × GWP_A4                                 [kg CO2eq]
A5           = procured × GWP_A5_1                               [kg CO2eq]

The WasteFactor accounts for on-site cutting / installation losses;
A5.1 (where provided) covers construction-process emissions.
Both are sourced directly from the Boverket Klimatdatabas.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from api.parsers import parse_file
from api.graph import collect_global_energy
from scripts.databases import lookup_gwp

XLINK = "{http://www.w3.org/1999/xlink}href"


def _safe_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


# ── Result containers ─────────────────────────────────────────────────────────

@dataclass
class LayerResult:
    boundary_type: str
    construction: str
    material: str
    area_m2: float
    thickness_m: float
    density: float
    waste_factor: float
    base_mass_kg: float
    procured_kg: float
    a1_a3: float | None
    a4: float | None
    a5: float | None
    env_id: str | None
    bov_name: str | None
    skipped: bool = False
    skip_reason: str = ""


# ── Main calculation ──────────────────────────────────────────────────────────

def run(gml_file: str) -> None:
    print(f"\n{'='*70}")
    print(f" LCA Embodied Carbon — A1-A3 · A4 · A5")
    print(f" File : {Path(gml_file).name}")
    print(f"{'='*70}")

    # Parse GML
    model = parse_file(gml_file)
    ge = collect_global_energy(gml_file)

    rsp = model.get("lca", {}).get("referenceStudyPeriod", "—")
    print(f" RSP  : {rsp}  (A1–A5 scope; B4 replacement excluded)")

    results: list[LayerResult] = []
    skipped: list[LayerResult] = []

    for b in model["buildings"]:
        bname = b.get("name") or b.get("id") or "Building"
        print(f"\n Building: {bname}")

        for tz in b["energy"]["thermalZones"]:
            for tb in tz["thermalBoundaries"]:
                area = _safe_float(tb.get("area"))
                con_ref = (tb.get("construction") or "").lstrip("#")
                if not area or not con_ref:
                    continue

                con = ge.get(con_ref, {})
                con_name = con.get("name", con_ref)
                layers = con.get("layers", [])
                if not layers:
                    continue

                print(f"\n  Boundary: {tb.get('type','?')} | area: {area:.2f} m² "
                      f"| construction: {con_name}")

                for i, layer in enumerate(layers, 1):
                    thickness = _safe_float(layer.get("thickness"))
                    mat_ref = (layer.get("material") or "").lstrip("#")
                    mat = ge.get(mat_ref, {})
                    mat_name = mat.get("name", mat_ref or "?")
                    env_id = mat.get("lca:environmentalId")
                    env_src = mat.get("lca:environmentalIdSource", "boverket")
                    density = _safe_float(mat.get("density"))

                    def _skip(reason):
                        r = LayerResult(
                            boundary_type=tb.get("type","?"), construction=con_name,
                            material=mat_name, area_m2=area or 0,
                            thickness_m=thickness or 0, density=density or 0,
                            waste_factor=1.0, base_mass_kg=0, procured_kg=0,
                            a1_a3=None, a4=None, a5=None,
                            env_id=env_id, bov_name=None,
                            skipped=True, skip_reason=reason,
                        )
                        skipped.append(r)
                        print(f"    L{i}: {mat_name:<30s} ⚠ SKIP: {reason}")

                    if not thickness:
                        _skip("thickness missing"); continue
                    if not density:
                        _skip("density missing (Gas/air gap)"); continue
                    if not env_id:
                        _skip("no lca:environmentalId"); continue

                    gwp_data = lookup_gwp(env_id, env_src)
                    if gwp_data is None:
                        _skip(f"[{env_src}] id {env_id} not found"); continue

                    bov_name  = gwp_data.get("name", "?")
                    gwp_a1a3  = gwp_data.get("A1-A3")
                    gwp_a4    = gwp_data.get("A4")
                    gwp_a5    = gwp_data.get("A5.1")
                    waste     = _safe_float(gwp_data.get("WasteFactor")) or 1.0

                    if gwp_a1a3 is None:
                        _skip(f"no GWP A1-A3 in Boverket entry"); continue

                    base_mass  = area * thickness * density
                    procured   = base_mass * waste
                    a1_a3      = procured * gwp_a1a3
                    a4         = procured * gwp_a4   if gwp_a4  is not None else None
                    a5         = procured * gwp_a5   if gwp_a5  is not None else None

                    r = LayerResult(
                        boundary_type=tb.get("type","?"), construction=con_name,
                        material=mat_name, area_m2=area,
                        thickness_m=thickness, density=density,
                        waste_factor=waste, base_mass_kg=base_mass,
                        procured_kg=procured,
                        a1_a3=a1_a3, a4=a4, a5=a5,
                        env_id=env_id, bov_name=bov_name,
                    )
                    results.append(r)

                    a4_str = f"{a4:7.1f}" if a4 is not None else "    n/a"
                    a5_str = f"{a5:7.1f}" if a5 is not None else "    n/a"
                    print(
                        f"    L{i}: {mat_name:<30s} "
                        f"t={thickness:.4f}m  ρ={density:.0f}kg/m³  "
                        f"×{waste}  →  {procured:7.1f}kg"
                    )
                    print(
                        f"         [{bov_name[:40]:<40s}]"
                        f"  A1-A3={a1_a3:8.1f}  A4={a4_str}  A5={a5_str}  kgCO₂eq"
                    )

    # ── Summary ───────────────────────────────────────────────────────────────
    total_a1a3 = sum(r.a1_a3 for r in results if r.a1_a3 is not None)
    total_a4   = sum(r.a4   for r in results if r.a4   is not None)
    total_a5   = sum(r.a5   for r in results if r.a5   is not None)
    total      = total_a1a3 + total_a4 + total_a5

    print(f"\n{'─'*70}")
    print(f"  Layers computed : {len(results)}")
    print(f"  Layers skipped  : {len(skipped)}")
    if skipped:
        for s in skipped:
            print(f"    · {s.material:<30s} ({s.skip_reason})")
    print(f"{'─'*70}")
    print(f"  A1-A3  (product stage)        : {total_a1a3:>10.1f} kgCO₂eq")
    print(f"  A4     (transport to site)    : {total_a4:>10.1f} kgCO₂eq")
    print(f"  A5.1   (construction process) : {total_a5:>10.1f} kgCO₂eq")
    print(f"{'─'*70}")
    print(f"  TOTAL  A1-A5                  : {total:>10.1f} kgCO₂eq")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: PYTHONPATH=. python scripts/calculate_lca.py <file.gml>")
        raise SystemExit(1)
    run(sys.argv[1])
