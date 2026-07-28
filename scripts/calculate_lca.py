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

import argparse
import importlib
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
    boundary_id: str
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


def _fmt_kg(v: float) -> str:
    return f"{v:,.1f}"


def _fmt_intensity(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:,.2f}"


def _safe_db_factor(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    token = s.split()[0].replace(",", ".")
    try:
        return float(token)
    except ValueError:
        return None


def _category_from_boundary(boundary_type: str) -> str:
    b = (boundary_type or "").lower()
    if b == "outerwall":
        return "Wall"
    if b == "roof":
        return "Roof"
    if b == "groundslab":
        return "Slab"
    if b == "window":
        return "Window"
    return "Other"


def write_markdown_report(
    gml_file: str,
    rsp: str,
    results: list[LayerResult],
    skipped: list[LayerResult],
    total_boundary_area_m2: float,
    total_a1a3: float,
    total_a4: float,
    total_a5: float,
    total: float,
    a1a3_per_m2: float | None,
    a4_per_m2: float | None,
    a5_per_m2: float | None,
    total_per_m2: float | None,
    split_totals: dict[str, float],
    report_path: Path,
) -> None:
    a1a3_share = (100 * total_a1a3 / total) if total else 0.0
    a4_share = (100 * total_a4 / total) if total else 0.0
    a5_share = (100 * total_a5 / total) if total else 0.0

    skip_counts: dict[str, int] = {}
    for s in skipped:
        key = f"{s.material} ({s.skip_reason})"
        skip_counts[key] = skip_counts.get(key, 0) + 1

    skip_rows = ""
    if skip_counts:
        for k, cnt in sorted(skip_counts.items()):
            skip_rows += f"| {k} | {cnt} |\n"
    else:
        skip_rows = "| None | 0 |\n"

    report = f"""# Embodied LCA Report

## Executive Summary

This report presents embodied carbon results for the building model below, covering product and construction stages A1-A5 (A1-A3, A4, A5.1).

| Item | Value |
|---|---|
| Model file | {gml_file} |
| Reference study period (RSP) | {rsp} |
| Scope | A1-A3, A4, A5.1 |
| Layers computed | {len(results)} |
| Layers skipped | {len(skipped)} |
| Boundary area analyzed | {total_boundary_area_m2:,.1f} m2 |

## Goal And Scope

The goal is to estimate embodied global warming potential (GWP, kgCO2eq) for the modeled envelope constructions using CityGML Energy + LCA attributes and Boverket factors.

Included modules:
- A1-A3 product stage
- A4 transport to site
- A5.1 construction process

Excluded from this run:
- B4 replacement (outside current script scope)
- Operational impacts (B6/B7)
- End-of-life modules (C)

## Method And Inventory Basis

Per layer formula:

- base_mass = boundary_area * layer_thickness * material_density
- procured = base_mass * WasteFactor
- A1-A3 = procured * GWP_A1A3
- A4 = procured * GWP_A4
- A5.1 = procured * GWP_A5_1

Primary data source for factors: Boverket Klimatdatabas (via lca:environmentalId).

## Results

### Absolute Results

| Module | Result (kgCO2eq) | Share of total |
|---|---:|---:|
| A1-A3 | {_fmt_kg(total_a1a3)} | {a1a3_share:.1f}% |
| A4 | {_fmt_kg(total_a4)} | {a4_share:.1f}% |
| A5.1 | {_fmt_kg(total_a5)} | {a5_share:.1f}% |
| TOTAL (A1-A5) | {_fmt_kg(total)} | 100.0% |

### Intensity Results

| Module | Intensity (kgCO2eq/m2) |
|---|---:|
| A1-A3 | {_fmt_intensity(a1a3_per_m2)} |
| A4 | {_fmt_intensity(a4_per_m2)} |
| A5.1 | {_fmt_intensity(a5_per_m2)} |
| TOTAL (A1-A5) | {_fmt_intensity(total_per_m2)} |

### Split By Component Group

| Group | A1-A5 (kgCO2eq) | Share of total |
|---|---:|---:|
| Wall | {_fmt_kg(split_totals.get('Wall', 0.0))} | {(100 * split_totals.get('Wall', 0.0) / total if total else 0.0):.1f}% |
| Roof | {_fmt_kg(split_totals.get('Roof', 0.0))} | {(100 * split_totals.get('Roof', 0.0) / total if total else 0.0):.1f}% |
| Slab | {_fmt_kg(split_totals.get('Slab', 0.0))} | {(100 * split_totals.get('Slab', 0.0) / total if total else 0.0):.1f}% |
| Window | {_fmt_kg(split_totals.get('Window', 0.0))} | {(100 * split_totals.get('Window', 0.0) / total if total else 0.0):.1f}% |
| Other | {_fmt_kg(split_totals.get('Other', 0.0))} | {(100 * split_totals.get('Other', 0.0) / total if total else 0.0):.1f}% |

## Data Quality And Completeness

| Check | Result |
|---|---|
| Computable coverage | {len(results)}/{len(results)+len(skipped)} layers ({(100*len(results)/(len(results)+len(skipped)) if (len(results)+len(skipped)) else 0):.1f}%) |
| Skipped layers reason breakdown | See table below |

| Skipped item (material + reason) | Count |
|---|---:|
{skip_rows}

## Interpretation

- A1-A3 is the dominant contributor in this run.
- Transport (A4) and construction process (A5.1) are secondary but non-negligible.
- Reported intensities are normalized by analyzed boundary area, not floor area.

## Limitations

- Results depend on mapped Boverket IDs and available module factors.
- Layers without required physical or LCA metadata are excluded from computed totals.
- This report does not include uncertainty analysis.

"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")


def write_excel_report(
    gml_file: str,
    rsp: str,
    results: list[LayerResult],
    skipped: list[LayerResult],
    total_boundary_area_m2: float,
    report_path: Path,
) -> None:
    openpyxl = importlib.import_module("openpyxl")
    styles = importlib.import_module("openpyxl.styles")
    Workbook = getattr(openpyxl, "Workbook")
    Font = getattr(styles, "Font")

    # Rebuild workbook in a hierarchical structure: MaterialDB -> Surfaces -> Components -> Layers
    wb = Workbook()
    ws_summary = wb.active
    if ws_summary is None:
        ws_summary = wb.create_sheet("Summary")
    ws_summary.title = "Summary"
    ws_matdb = wb.create_sheet("MaterialDB")
    ws_surfaces = wb.create_sheet("Surfaces")
    ws_components = wb.create_sheet("Components")
    ws_layers = wb.create_sheet("Layers")
    ws_openings = wb.create_sheet("Openings")
    ws_skipped = wb.create_sheet("Skipped")

    layer_headers = [
        "BoundaryType",
        "BoundaryId",
        "Construction",
        "Material",
        "Area_m2",
        "Thickness_m",
        "Density_kg_m3",
        "WasteFactor",
        "GWP_A1A3",
        "GWP_A4",
        "GWP_A5_1",
        "BaseMass_kg",
        "Procured_kg",
        "A1A3_kgCO2eq",
        "A4_kgCO2eq",
        "A5_1_kgCO2eq",
        "Total_A1A5_kgCO2eq",
        "EnvId",
        "BoverketName",
    ]
    ws_layers.append(layer_headers)
    for c in range(1, len(layer_headers) + 1):
        ws_layers.cell(row=1, column=c).font = Font(bold=True)

    material_db_headers = [
        "Material",
        "EnvId",
        "BoverketName",
        "Density_kg_m3",
        "WasteFactor",
        "GWP_A1A3",
        "GWP_A4",
        "GWP_A5_1",
    ]
    ws_matdb.append(material_db_headers)
    for c in range(1, len(material_db_headers) + 1):
        ws_matdb.cell(row=1, column=c).font = Font(bold=True)

    surface_headers = [
        "BoundaryId",
        "BoundaryType",
        "Construction",
        "GrossArea_m2",
        "OpeningArea_m2",
        "NetArea_m2",
        "ThermalOpeningCount",
    ]
    ws_surfaces.append(surface_headers)
    for c in range(1, len(surface_headers) + 1):
        ws_surfaces.cell(row=1, column=c).font = Font(bold=True)

    component_headers = [
        "ComponentId",
        "ComponentType",
        "ParentBoundaryId",
        "Construction",
        "Area_m2",
        "OpeningArea_m2",
        "NetArea_m2",
        "A1A3_kgCO2eq",
        "A4_kgCO2eq",
        "A5_1_kgCO2eq",
        "Total_A1A5_kgCO2eq",
        "Intensity_kgCO2eq_m2",
    ]
    ws_components.append(component_headers)
    for c in range(1, len(component_headers) + 1):
        ws_components.cell(row=1, column=c).font = Font(bold=True)

    opening_headers = [
        "OpeningId",
        "OpeningName",
        "OpeningType",
        "ParentBoundaryId",
        "Construction",
        "Area_m2",
    ]
    ws_openings.append(opening_headers)
    for c in range(1, len(opening_headers) + 1):
        ws_openings.cell(row=1, column=c).font = Font(bold=True)

    material_rows: dict[str, int] = {}
    component_rows: dict[str, int] = {}

    # Build surfaces/components/openings from parsed model so windows are explicit.
    model = parse_file(gml_file)
    surface_row = 2
    component_row = 2
    opening_row = 2
    for b in model.get("buildings", []):
        for tz in b.get("energy", {}).get("thermalZones", []):
            for tb in tz.get("thermalBoundaries", []):
                tb_id = tb.get("id") or "?"
                tb_type = tb.get("type") or "?"
                construction = (tb.get("construction") or "").lstrip("#")
                gross_area = _safe_float(tb.get("area")) or 0.0
                openings = tb.get("thermalOpenings") or []
                opening_area = 0.0
                for op in openings:
                    op_area = _safe_float(op.get("area")) or 0.0
                    opening_area += op_area
                    op_con = (op.get("construction") or "").lstrip("#")
                    op_name_raw = op.get("name")
                    op_name = (op_name_raw or "").lower()
                    op_con_l = op_con.lower()
                    op_type = "window"
                    if "door" in op_name or "tur" in op_name or "door" in op_con_l or "tur" in op_con_l:
                        op_type = "door"
                    ws_openings.append([
                        op.get("id") or "?",
                        op_name_raw,
                        op_type,
                        tb_id,
                        op_con,
                        op_area,
                    ])
                    opening_row += 1

                net_area = max(gross_area - opening_area, 0.0)
                ws_surfaces.append([
                    tb_id,
                    tb_type,
                    construction,
                    gross_area,
                    opening_area,
                    net_area,
                    len(openings),
                ])
                surface_row += 1

                comp_id = f"C-{tb_id}"
                ws_components.append([
                    comp_id,
                    tb_type,
                    tb_id,
                    construction,
                    gross_area,
                    opening_area,
                    net_area,
                    f"=SUMIFS(Layers!N:N,Layers!B:B,C{component_row},Layers!C:C,D{component_row})",
                    f"=SUMIFS(Layers!O:O,Layers!B:B,C{component_row},Layers!C:C,D{component_row})",
                    f"=SUMIFS(Layers!P:P,Layers!B:B,C{component_row},Layers!C:C,D{component_row})",
                    f"=H{component_row}+I{component_row}+J{component_row}",
                    f"=IF(G{component_row}=0,0,K{component_row}/G{component_row})",
                ])
                component_rows[comp_id] = component_row
                component_row += 1

                # Window/door components for explicit opening accounting.
                for op in openings:
                    op_id = op.get("id") or "?"
                    op_con = (op.get("construction") or "").lstrip("#")
                    op_area = _safe_float(op.get("area")) or 0.0
                    op_name = (op.get("name") or "").lower()
                    op_con_l = op_con.lower()
                    op_type = "window"
                    if "door" in op_name or "tur" in op_name or "door" in op_con_l or "tur" in op_con_l:
                        op_type = "door"
                    op_comp_id = f"O-{op_id}"
                    ws_components.append([
                        op_comp_id,
                        op_type,
                        tb_id,
                        op_con,
                        op_area,
                        0.0,
                        op_area,
                        f"=SUMIFS(Layers!N:N,Layers!B:B,C{component_row},Layers!C:C,D{component_row})",
                        f"=SUMIFS(Layers!O:O,Layers!B:B,C{component_row},Layers!C:C,D{component_row})",
                        f"=SUMIFS(Layers!P:P,Layers!B:B,C{component_row},Layers!C:C,D{component_row})",
                        f"=H{component_row}+I{component_row}+J{component_row}",
                        f"=IF(G{component_row}=0,0,K{component_row}/G{component_row})",
                    ])
                    component_rows[op_comp_id] = component_row
                    component_row += 1

    for idx, r in enumerate(results, start=2):
        gwp_a1a3 = (r.a1_a3 / r.procured_kg) if (r.a1_a3 is not None and r.procured_kg) else None
        gwp_a4 = (r.a4 / r.procured_kg) if (r.a4 is not None and r.procured_kg) else None
        gwp_a5 = (r.a5 / r.procured_kg) if (r.a5 is not None and r.procured_kg) else None

        ws_layers.cell(row=idx, column=1, value=r.boundary_type)
        ws_layers.cell(row=idx, column=2, value=r.boundary_id)
        ws_layers.cell(row=idx, column=3, value=r.construction)
        ws_layers.cell(row=idx, column=4, value=r.material)
        ws_layers.cell(row=idx, column=5, value=r.area_m2)
        ws_layers.cell(row=idx, column=6, value=r.thickness_m)
        ws_layers.cell(row=idx, column=7, value=r.density)
        ws_layers.cell(row=idx, column=8, value=r.waste_factor)
        ws_layers.cell(row=idx, column=9, value=gwp_a1a3)
        ws_layers.cell(row=idx, column=10, value=gwp_a4)
        ws_layers.cell(row=idx, column=11, value=gwp_a5)

        ws_layers.cell(row=idx, column=12, value=f"=E{idx}*F{idx}*G{idx}")
        ws_layers.cell(row=idx, column=13, value=f"=L{idx}*H{idx}")
        ws_layers.cell(row=idx, column=14, value=f"=M{idx}*I{idx}")
        ws_layers.cell(row=idx, column=15, value=f"=M{idx}*J{idx}")
        ws_layers.cell(row=idx, column=16, value=f"=M{idx}*K{idx}")
        ws_layers.cell(row=idx, column=17, value=f"=N{idx}+O{idx}+P{idx}")
        ws_layers.cell(row=idx, column=18, value=r.env_id)
        ws_layers.cell(row=idx, column=19, value=r.bov_name)

        mat_key = f"{r.material}|{r.env_id or ''}"
        if mat_key not in material_rows:
            mat_row = ws_matdb.max_row + 1
            material_rows[mat_key] = mat_row
            ws_matdb.append([
                r.material,
                r.env_id,
                r.bov_name,
                r.density,
                r.waste_factor,
                gwp_a1a3,
                gwp_a4,
                gwp_a5,
            ])

    summary = ws_summary
    summary["A1"] = "Embodied LCA Report"
    summary["A1"].font = Font(bold=True)
    summary["A2"] = "Model file"
    summary["B2"] = gml_file
    summary["A3"] = "Reference study period"
    summary["B3"] = rsp
    summary["A4"] = "Layers computed"
    summary["B4"] = len(results)
    summary["A5"] = "Layers skipped"
    summary["B5"] = len(skipped)
    summary["A6"] = "Boundary area analyzed (m2)"
    summary["B6"] = total_boundary_area_m2

    summary["A7"] = "Surfaces"
    summary["B7"] = "=COUNTA(Surfaces!A:A)-1"
    summary["A8"] = "Openings (windows+doors)"
    summary["B8"] = "=COUNTA(Openings!A:A)-1"

    summary["A10"] = "Module"
    summary["B10"] = "kgCO2eq"
    summary["C10"] = "Share"
    summary["D10"] = "kgCO2eq/m2"
    for cell in ("A10", "B10", "C10", "D10"):
        summary[cell].font = Font(bold=True)

    summary["A11"] = "A1-A3"
    summary["A12"] = "A4"
    summary["A13"] = "A5.1"
    summary["A14"] = "TOTAL A1-A5"
    summary["B11"] = "=SUM(Layers!N:N)"
    summary["B12"] = "=SUM(Layers!O:O)"
    summary["B13"] = "=SUM(Layers!P:P)"
    summary["B14"] = "=SUM(Layers!Q:Q)"
    summary["C11"] = "=IF(B14=0,0,B11/B14)"
    summary["C12"] = "=IF(B14=0,0,B12/B14)"
    summary["C13"] = "=IF(B14=0,0,B13/B14)"
    summary["C14"] = "=IF(B14=0,0,B14/B14)"
    summary["D11"] = "=IF(B6=0,0,B11/B6)"
    summary["D12"] = "=IF(B6=0,0,B12/B6)"
    summary["D13"] = "=IF(B6=0,0,B13/B6)"
    summary["D14"] = "=IF(B6=0,0,B14/B6)"

    for row in (11, 12, 13, 14):
        summary[f"B{row}"].number_format = "#,##0.0"
        summary[f"C{row}"].number_format = "0.0%"
        summary[f"D{row}"].number_format = "#,##0.00"

    summary["A16"] = "Split"
    summary["B16"] = "A1-A5 kgCO2eq"
    summary["C16"] = "Share"
    for cell in ("A16", "B16", "C16"):
        summary[cell].font = Font(bold=True)
    summary["A17"] = "Wall"
    summary["A18"] = "Roof"
    summary["A19"] = "Slab"
    summary["A20"] = "Window"
    summary["A21"] = "Other"
    summary["B17"] = "=SUMIFS(Layers!Q:Q,Layers!A:A,\"outerWall\")"
    summary["B18"] = "=SUMIFS(Layers!Q:Q,Layers!A:A,\"roof\")"
    summary["B19"] = "=SUMIFS(Layers!Q:Q,Layers!A:A,\"groundSlab\")"
    summary["B20"] = "=SUMIFS(Layers!Q:Q,Layers!A:A,\"window\")"
    summary["B21"] = "=B14-SUM(B17:B20)"
    summary["C17"] = "=IF(B14=0,0,B17/B14)"
    summary["C18"] = "=IF(B14=0,0,B18/B14)"
    summary["C19"] = "=IF(B14=0,0,B19/B14)"
    summary["C20"] = "=IF(B14=0,0,B20/B14)"
    summary["C21"] = "=IF(B14=0,0,B21/B14)"
    for row in (17, 18, 19, 20, 21):
        summary[f"B{row}"].number_format = "#,##0.0"
        summary[f"C{row}"].number_format = "0.0%"

    skip_ws = ws_skipped
    skip_ws.append(["BoundaryType", "Construction", "Material", "Reason", "EnvId"])
    for c in range(1, 6):
        skip_ws.cell(row=1, column=c).font = Font(bold=True)
    for s in skipped:
        skip_ws.append([s.boundary_type, s.construction, s.material, s.skip_reason, s.env_id])

    report_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(report_path)


# ── Main calculation ──────────────────────────────────────────────────────────

def run(
    gml_file: str,
    report_path: Path | None = None,
    report_xlsx_path: Path | None = None,
) -> None:
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
    total_boundary_area_m2 = 0.0
    split_totals = {"Wall": 0.0, "Roof": 0.0, "Slab": 0.0, "Window": 0.0, "Other": 0.0}

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

                total_boundary_area_m2 += area

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
                            boundary_id=tb.get("id", ""),
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
                        boundary_id=tb.get("id", ""),
                        boundary_type=tb.get("type","?"), construction=con_name,
                        material=mat_name, area_m2=area,
                        thickness_m=thickness, density=density,
                        waste_factor=waste, base_mass_kg=base_mass,
                        procured_kg=procured,
                        a1_a3=a1_a3, a4=a4, a5=a5,
                        env_id=env_id, bov_name=bov_name,
                    )
                    results.append(r)
                    split_totals[_category_from_boundary(r.boundary_type)] += (
                        (a1_a3 or 0.0) + (a4 or 0.0) + (a5 or 0.0)
                    )

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

                for op in tb.get("thermalOpenings", []):
                    op_area = _safe_float(op.get("area"))
                    op_con_ref = (op.get("construction") or "").lstrip("#")
                    if not op_area or not op_con_ref:
                        continue

                    op_con = ge.get(op_con_ref, {})
                    op_con_name = op_con.get("name", op_con_ref)
                    op_layers = op_con.get("layers", [])
                    env_id = op_con.get("lca:environmentalId")
                    env_src = op_con.get("lca:environmentalIdSource", "boverket")
                    gwp_data = lookup_gwp(env_id, env_src) if env_id else None

                    # Handle simplified openings (e.g. windows) that carry direct db GWP factors.
                    if not op_layers:
                        db_a1 = _safe_db_factor(op_con.get("db:gwpA1A3"))
                        db_a4 = _safe_db_factor(op_con.get("db:gwpA4"))
                        db_a5 = _safe_db_factor(op_con.get("db:gwpA5_1"))
                        db_waste = _safe_db_factor(op_con.get("db:wasteFactor")) or 1.0
                        if db_a1 is None and gwp_data is not None:
                            db_a1 = _safe_float(gwp_data.get("A1-A3"))
                            db_a4 = _safe_float(gwp_data.get("A4"))
                            db_a5 = _safe_float(gwp_data.get("A5.1"))
                            db_waste = _safe_float(gwp_data.get("WasteFactor")) or 1.0
                        if db_a1 is None:
                            continue

                        bov_name = gwp_data.get("name", op_con_name) if gwp_data else op_con_name

                        procured = op_area * db_waste
                        a1_a3 = procured * db_a1
                        a4 = procured * db_a4 if db_a4 is not None else None
                        a5 = procured * db_a5 if db_a5 is not None else None

                        r = LayerResult(
                            boundary_id=tb.get("id", ""),
                            boundary_type="window",
                            construction=op_con_name,
                            material=op_con_name,
                            area_m2=op_area,
                            thickness_m=1.0,
                            density=1.0,
                            waste_factor=db_waste,
                            base_mass_kg=op_area,
                            procured_kg=procured,
                            a1_a3=a1_a3,
                            a4=a4,
                            a5=a5,
                            env_id=env_id,
                            bov_name=bov_name,
                        )
                        results.append(r)
                        split_totals["Window"] += (a1_a3 or 0.0) + (a4 or 0.0) + (a5 or 0.0)

    # ── Summary ───────────────────────────────────────────────────────────────
    total_a1a3 = sum(r.a1_a3 for r in results if r.a1_a3 is not None)
    total_a4   = sum(r.a4   for r in results if r.a4   is not None)
    total_a5   = sum(r.a5   for r in results if r.a5   is not None)
    total      = total_a1a3 + total_a4 + total_a5

    a1a3_per_m2 = (total_a1a3 / total_boundary_area_m2) if total_boundary_area_m2 else None
    a4_per_m2 = (total_a4 / total_boundary_area_m2) if total_boundary_area_m2 else None
    a5_per_m2 = (total_a5 / total_boundary_area_m2) if total_boundary_area_m2 else None
    total_per_m2 = (total / total_boundary_area_m2) if total_boundary_area_m2 else None

    print(f"\n{'─'*70}")
    print(f"  Layers computed : {len(results)}")
    print(f"  Layers skipped  : {len(skipped)}")
    if skipped:
        for s in skipped:
            print(f"    · {s.material:<30s} ({s.skip_reason})")
    print(f"{'─'*70}")
    print(f"  Boundary area analyzed        : {total_boundary_area_m2:>10.1f} m²")
    print(f"{'─'*70}")
    print(f"  A1-A3  (product stage)        : {total_a1a3:>10.1f} kgCO₂eq")
    print(f"  A4     (transport to site)    : {total_a4:>10.1f} kgCO₂eq")
    print(f"  A5.1   (construction process) : {total_a5:>10.1f} kgCO₂eq")
    print(f"{'─'*70}")
    print(f"  TOTAL  A1-A5                  : {total:>10.1f} kgCO₂eq")
    print(f"  Split A1-A5                   : Wall={split_totals['Wall']:>8.1f}  Roof={split_totals['Roof']:>8.1f}  Slab={split_totals['Slab']:>8.1f}  Window={split_totals['Window']:>8.1f}")
    if total_per_m2 is not None:
        print(f"  A1-A3 intensity               : {a1a3_per_m2:>10.2f} kgCO₂eq/m²")
        print(f"  A4 intensity                  : {a4_per_m2:>10.2f} kgCO₂eq/m²")
        print(f"  A5.1 intensity                : {a5_per_m2:>10.2f} kgCO₂eq/m²")
        print(f"  TOTAL intensity (A1-A5)       : {total_per_m2:>10.2f} kgCO₂eq/m²")
    print(f"{'='*70}\n")

    if report_path is None:
        report_path = Path("results") / f"{Path(gml_file).stem}_lca_report.md"
    if report_xlsx_path is None:
        report_xlsx_path = Path("results") / f"{Path(gml_file).stem}_lca_report.xlsx"

    write_markdown_report(
        gml_file=gml_file,
        rsp=str(rsp),
        results=results,
        skipped=skipped,
        total_boundary_area_m2=total_boundary_area_m2,
        total_a1a3=total_a1a3,
        total_a4=total_a4,
        total_a5=total_a5,
        total=total,
        a1a3_per_m2=a1a3_per_m2,
        a4_per_m2=a4_per_m2,
        a5_per_m2=a5_per_m2,
        total_per_m2=total_per_m2,
        split_totals=split_totals,
        report_path=report_path,
    )
    write_excel_report(
        gml_file=gml_file,
        rsp=str(rsp),
        results=results,
        skipped=skipped,
        total_boundary_area_m2=total_boundary_area_m2,
        report_path=report_xlsx_path,
    )
    print(f" Report written: {report_path}")
    print(f" Excel written : {report_xlsx_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compute embodied LCA (A1-A5) and generate a Markdown report."
    )
    parser.add_argument("gml_file", help="Input CityGML file path")
    parser.add_argument(
        "--report-md",
        dest="report_md",
        default=None,
        help="Output Markdown report path (default: results/<model>_lca_report.md)",
    )
    parser.add_argument(
        "--report-xlsx",
        dest="report_xlsx",
        default=None,
        help="Output Excel report path (default: results/<model>_lca_report.xlsx)",
    )
    args = parser.parse_args()

    run(
        args.gml_file,
        Path(args.report_md) if args.report_md else None,
        Path(args.report_xlsx) if args.report_xlsx else None,
    )
