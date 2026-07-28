# Embodied LCA Report

## Executive Summary

This report presents embodied carbon results for the building model below, covering product and construction stages A1-A5 (A1-A3, A4, A5.1).

| Item | Value |
|---|---|
| Model file | models/FZKHouseLoD3-LCA.gml |
| Reference study period (RSP) | 50 a |
| Scope | A1-A3, A4, A5.1 |
| Layers computed | 42 |
| Layers skipped | 2 |
| Boundary area analyzed | 447.2 m2 |

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
| A1-A3 | 18,847.0 | 80.9% |
| A4 | 2,962.4 | 12.7% |
| A5.1 | 1,493.6 | 6.4% |
| TOTAL (A1-A5) | 23,303.1 | 100.0% |

### Intensity Results

| Module | Intensity (kgCO2eq/m2) |
|---|---:|
| A1-A3 | 42.15 |
| A4 | 6.62 |
| A5.1 | 3.34 |
| TOTAL (A1-A5) | 52.11 |

### Split By Component Group

| Group | A1-A5 (kgCO2eq) | Share of total |
|---|---:|---:|
| Wall | 11,376.8 | 48.8% |
| Roof | 5,648.9 | 24.2% |
| Slab | 6,220.0 | 26.7% |
| Window | 57.4 | 0.2% |
| Other | 0.0 | 0.0% |

## Data Quality And Completeness

| Check | Result |
|---|---|
| Computable coverage | 42/44 layers (95.5%) |
| Skipped layers reason breakdown | See table below |

| Skipped item (material + reason) | Count |
|---|---:|
| KIT-FZK-Haus-Luftschicht (density missing (Gas/air gap)) | 2 |


## Interpretation

- A1-A3 is the dominant contributor in this run.
- Transport (A4) and construction process (A5.1) are secondary but non-negligible.
- Reported intensities are normalized by analyzed boundary area, not floor area.

## Limitations

- Results depend on mapped Boverket IDs and available module factors.
- Layers without required physical or LCA metadata are excluded from computed totals.
- This report does not include uncertainty analysis.

