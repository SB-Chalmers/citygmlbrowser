# A Modular CityGML Life Cycle Assessment ADE (LCA ADE 1.0)

**Specification and design rationale**
Namespace: `http://sb.chalmers.se/ade/lca/1.0` (prefix `lca`)
Depends on: CityGML 2.0 (Core, Building) and the Energy ADE 3.0 (beta 7)
Version: 1.0 beta — 2026-07

---

## Overview

This document specifies the Life Cycle Assessment Application Domain Extension
(LCA ADE) for CityGML and records the motivation, the concrete action taken, the
compliance with the accompanying UML model, and the interoperability
implications of every change. The extension deliberately adds a minimal set of
parameters to *existing* classes of the Energy ADE 3.0 rather than introducing a
new component module. This keeps the schema lightweight, reuses the substantial
building, device and material information already carried by the Energy ADE, and
lowers the barrier to adoption for tools that already understand CityGML and the
Energy ADE.

The additions are organised around the three data needs of building LCA
described in EN 15978: a **general** parameter that fixes the assessment horizon,
the **embodied** parameters that link physical components to environmental
datasets, and the **operational** parameters that link resource flows to the same
datasets. Each of the following sections follows the same structure —
*motivation*, *action*, *UML compliance*, and *interoperability* — so that a
reader can trace a single design decision from its LCA rationale down to its XML
encoding.

## Design principles

Three principles guided every decision and are worth stating up front, because
they explain why several seemingly obvious additions were deliberately *not*
made.

The first principle is **reuse over reinvention**. Where the Energy ADE already
carries a value that LCA needs, the LCA ADE references it rather than duplicating
it. The clearest example is embodied carbon: the Energy ADE 3.0 `SolidMaterial`
class already defines `embodiedCarbon` and `embodiedEnergy` attributes, so the
LCA ADE does not add a competing greenhouse-warming-potential field.

The second principle is **link, don't store**. Environmental impact factors are
volatile. Environmental Product Declarations (EPDs) are valid for three to five
years, and national databases such as the Swedish Boverket climate database are
updated several times per year. Furthermore, an impact factor is not a single
number but a matrix spanning multiple indicators and life-cycle modules. Storing
such factors inline in a spatial model would guarantee that the model is out of
date the moment it is written. The LCA ADE therefore stores only a stable
*identifier* that resolves to the current record in an external database.

The third principle is **respect the host schema**. Every addition is expressed
through the mechanisms that CityGML and the Energy ADE already provide — the
Application Domain Extension hook for city objects, and the top-level city-object
pattern for document-scope data — so that the resulting files remain valid
CityGML and can be round-tripped by existing tooling such as the 3D City
Database Importer/Exporter.

---

## GENERAL — the assessment period

### Reference study period on a top-level LCA scenario

**Motivation.** Any life-cycle assessment beyond the pure production stage
(modules A1–A3) requires a reference study period (RSP): the number of years over
which the building is assessed. The RSP governs how many times a component is
replaced (module B4) and over how long operational impacts (B6, B7) accumulate.
For any given scenario it is a document-wide value; it is not a property of an
individual wall, device or building.

**Action.** The LCA ADE introduces one new top-level class, `LCAScenario`, which
carries a single property, `referenceStudyPeriod`, expressed as a measure in
years (`uom="a"`). One or more `LCAScenario` objects may be written per CityGML
document as `core:cityObjectMember` entries. For interoperable exchange profiles,
exactly one scenario should be designated as the active/default baseline (tooling
may overwrite or switch this selection):

```xml
<core:cityObjectMember>
  <lca:LCAScenario gml:id="lca_scenario_1">
    <lca:referenceStudyPeriod uom="a">50</lca:referenceStudyPeriod>
  </lca:LCAScenario>
</core:cityObjectMember>
```

The number of replacement cycles for any component then follows directly from the
RSP and that component's reference service life (RSL):

```
replacements = ceil( referenceStudyPeriod / referenceServiceLife ) − 1
```

**UML compliance.** In the UML model, `LCAScenario` is a `«featureType»` tagged
`topLevel = true` and generalises `Core::_CityObject`. This mirrors exactly how
the Energy ADE models every one of its document-scope objects.

**Interoperability.** The Energy ADE specification states that its library
classes (`MaterialLibrary`, `LayeredConstructionLibrary`, `ScheduleLibrary`) and
the `WeatherStation` and `UrbanFunctionArea` classes are all top-level elements
derived from `_CityObject`, a decision the specification describes as *pragmatic*
because it lets tools such as the 3D City Database Importer/Exporter select which
top-level objects to import or export. By deriving `LCAScenario` from
`_CityObject` in the same way, the RSP becomes a first-class, selectable,
exchangeable object. Two alternatives were rejected: attaching
`referenceStudyPeriod` directly to `core:CityModel` is invalid, because the
content model of `CityModel` is fixed and cannot host a foreign-namespace child;
and attaching it to every building through an ADE hook would misrepresent a
document-wide value as a per-building one and force arbitrary duplication.

---

## EMBODIED — production, end-of-life and replacement

The embodied additions attach two parameters to the physical components of the
model: an **Environmental ID** that links the component to its EPD (covering
modules A1–A5 and C1–C4, and the optional benefit module D), and a **reference
service life** that drives the replacement calculation (module B4). Both are added
to three kinds of component — energy devices, whole-unit construction assemblies,
and the solid materials of layered constructions.

### The Environmental ID and its supporting types

**Motivation.** Following the *link, don't store* principle, the LCA ADE needs a
compact, database-agnostic way to reference an external impact record. Different
databases identify their records differently: Boverket uses ten-digit integers,
while Ökobaudat uses UUIDs. The reference therefore needs to carry both the
record identifier and an indication of which database it belongs to.

**Action.** A single data type, `LCAEnvironmentalReference`, holds the database
record identifier as its content and an optional `source` attribute that names
the database. The `source` attribute draws its values from a closed code list,
`EPDSourceValue`, which currently admits two values, `boverket` and
`oekobaudat`. The list is deliberately closed: restricting the supported
databases keeps resolution unambiguous and prevents silently unverifiable
references from entering a model.

```xml
<lca:environmentalId source="boverket">6000000104</lca:environmentalId>
```

**UML compliance.** In the UML model `LCAEnvironmentalReference` is a
`«dataType»` and `EPDSourceValue` is a `«codeList»`, following the official
Energy ADE convention of rendering data types in peach and code lists as plain
white boxes. The data type depends on the code list through its `source`
property.

**Interoperability.** Modelling the reference as a data type rather than a bare
string means that a consuming tool can validate the `source` against the code
list and dispatch to the correct database connector. Because the code list is
published as an external GML dictionary, new databases can be added in future
minor versions without breaking existing documents.

### Embodied impact of energy devices

**Motivation.** Heating, ventilation, air-conditioning and photovoltaic
equipment carry significant embodied impact and are replaced on cycles shorter
than the building itself, so they require both an Environmental ID and an RSL.

**Action.** The Environmental ID and the reference service life are recognised on
every concrete subclass of `nrg3::AbstractDevice`. The extension covers the
twelve device types defined in the Energy ADE 3.0 XSD: `Boiler`, `HeatPump`, the
four solar collectors (`PhotovoltaicCollector`, `PhotovoltaicThermalCollector`,
`SolarThermalCollector`, `GenericSolarCollector`), the two storage devices
(`ElectricalStorageDevice`, `ThermalStorageDevice`), `LightingDevice`,
`MovableShadingDevice`, and the two generic catch-alls (`GenericDevice`,
`GenericElectricalDevice`).

**UML compliance.** In the UML model the two LCA rows appear beneath a `+ LCA
ADE` separator inside `AbstractDevice`, signalling that they are the new
parameters proposed by this schema rather than pre-existing Energy ADE
attributes.

**Interoperability.** Because `AbstractDevice` extends `core:_CityObject`, the two
LCA properties attach to it through the **formal** CityGML ADE hook: they
substitute `core:_GenericApplicationPropertyOfCityObject` and are therefore
schema-validated on every device. This is the strongest form of interoperability
the host schema offers — a validating parser will accept the properties without
any knowledge of the LCA ADE beyond its schema location.

### Embodied impact of window and door units

**Motivation.** A window or an external door is generally purchased and declared
as a single product, and its EPD covers the complete unit (frame and glazing
together). Such an assembly does not decompose into the material layers used for
opaque walls, so its impact cannot be attributed to individual materials.

**Action.** The Environmental ID and reference service life are recognised on
`nrg3::LayeredConstruction` and `nrg3::ReverseLayeredConstruction`, but only for
**layerless** constructions — those that carry a `glazingRatio` and have no
`Layer` children. The injection tooling enforces this by skipping any
construction that already contains layers. In the Alderaan test model this rule
selects exactly one construction, the triple-glazed glazing unit, which is linked
to the Boverket record `6000000104` (*Window, wood, side hung, triple-glazed*).

**UML compliance.** The UML model shows the LCA rows on `LayeredConstruction` and
`ReverseLayeredConstruction`, annotated *"layerless window/door units only"*, and
an adjacent note states the decomposition rule explicitly: a construction with
layers carries its EPDs on the layer materials, while a construction without
layers carries the EPD itself, and never both.

**Interoperability.** This rule is the schema-level guarantee against
**double-counting**, the single most important correctness property of a
component LCA. Because opaque constructions expose their materials through the
`Layer → material` composition, attributing an EPD to both the construction and
its materials would count the same impact twice. Restricting construction-level
EPDs to layerless `LayeredConstruction` and `ReverseLayeredConstruction`
assemblies makes the two encodings mutually exclusive by construction.

### Embodied impact of construction materials

**Motivation.** For opaque constructions — walls, floors, roofs — the impact is
best attributed to the individual materials, whose quantities follow from the
layer thicknesses and the surface areas. Each material is replaced on its own
cycle and therefore needs its own RSL.

**Action.** The Environmental ID and reference service life are recognised on
`nrg3::SolidMaterial`. Gas layers, such as the air gap in a glazing cavity, are
recognised by the parser but intentionally left unmapped, because a still-air
gap has no embodied impact.

**UML compliance.** The UML model shows the LCA rows beneath the existing
`embodiedCarbon` and `embodiedEnergy` attributes of `SolidMaterial`,
underscoring that the Environmental ID *complements* rather than replaces the
native Energy ADE fields: the inline `embodiedCarbon` gives a quick,
self-contained A1–A3 figure, while the Environmental ID unlocks the full EPD
matrix across all modules and indicators.

**Interoperability.** `SolidMaterial` extends `gml:_Feature` rather than
`core:_CityObject`, so it does not participate in the
`_GenericApplicationPropertyOfCityObject` substitution group. The LCA properties
are therefore attached by **convention injection** — they are written as direct
sibling children of the material element. This is a valid CityGML ADE pattern but
is not enforced by the host substitution-group mechanism; consuming tools must be
aware of the LCA ADE to interpret it. The same consideration applies to layered
constructions and to resources, and is discussed further under *Encoding and
conformance* below.

---

## OPERATIONAL — energy and water in use

### Environmental ID on resources

**Motivation.** Operational impacts (modules B6 and B7) arise from the energy and
water a building consumes in use. The Energy ADE 3.0 introduced the Resources
module precisely to generalise the older concept of energy demand, so the annual
or hourly amounts are already available. What is missing is the link from a
resource flow to the emission factor of its carrier.

**Action.** The Environmental ID is recognised on every concrete subclass of
`nrg3::AbstractResource` — `Energy`, `Water`, `Food`, `Waste`,
`ConstructionMaterial`, `OtherResource` and `UrbanSpace`. Crucially, the
reference service life is **not** added here: an operational flow is consumed,
not replaced, so the B4 replacement concept does not apply.

**UML compliance.** The UML model shows only a single LCA row on
`AbstractResource` and an accompanying note states explicitly that
`referenceServiceLife` is omitted for resources. This asymmetry with the embodied
components is intentional and visible in the diagram.

**Interoperability.** Like materials and constructions, `AbstractResource`
extends `gml:_Feature`, so the Environmental ID is attached here by convention
injection. The operational carbon of a flow is then obtained by resolving the
carrier's factor from the referenced database and multiplying by the amount the
Energy ADE already stores; the volatile factor itself never enters the model, in
keeping with the *link, don't store* principle. It is worth noting that the
Energy ADE's own `co2Equivalent` attribute on `AbstractResource` could hold an
inline figure, but for the same volatility reasons the LCA ADE prefers the
database link.

---

## Deliberate non-additions

Several fields that a first draft might include were considered and rejected, and
recording them is as important as recording the additions.

An explicit greenhouse-warming-potential field (a hypothetical `lca:gwp`) was
**not** added, because `SolidMaterial` already carries `embodiedCarbon`, which is
the A1–A3 global warming potential per unit mass. Adding a second field would
create two competing sources of truth for the same quantity.

A dedicated service-life *class* was **not** re-introduced. The Energy ADE 1.0
had a `ServiceLife` class that was deliberately dropped in the transition to
version 3.0 as part of a broader effort to keep the schema focused on simulation
and to delegate lifecycle and environmental data to external databases and to
CityGML 3.0's native temporal features. Rather than resurrect that class, the LCA
ADE expresses service life as a lightweight measure property alongside the
Environmental ID, consistent with the modern *link to external data* philosophy.

Inline impact factors of any kind were **not** stored, for the volatility reasons
given under the design principles.

---

## Encoding and conformance

The LCA ADE relies on two distinct attachment mechanisms, and understanding the
difference matters for anyone building a validating parser.

For city objects — the energy devices, and the CityGML building installations —
the LCA properties substitute `core:_GenericApplicationPropertyOfCityObject`.
This is the **formal** CityGML 2.0 ADE hook, and such properties are validated by
the schema on any `_CityObject` subclass.

For the Energy ADE features that extend `gml:_Feature` rather than
`core:_CityObject` — namely `SolidMaterial`, `LayeredConstruction`,
`ReverseLayeredConstruction` and the resource classes — no such hook exists in the
host schema. Here the LCA properties are attached by **convention injection** as
direct sibling children of the target element. This is a common and legitimate
ADE technique, but it is not schema-validated through the substitution-group
machinery; a consumer must know the LCA ADE to interpret these elements.

This split reflects a limitation of the host schema, not of the LCA design: the
Energy ADE itself notes that several of its feature classes would arguably be
better derived from `_CityObject`, and were kept on `_Feature` for historical and
pragmatic reasons. Should a future Energy ADE revision move these classes under
`_CityObject`, the convention-injected properties would become formally hookable
without any change to their meaning.

The extension targets CityGML 2.0 because the Energy ADE 3.0 beta 7 itself imports
CityGML 2.0; the `_GenericApplicationPropertyOfCityObject` hook is a CityGML 2.0
concept. CityGML 3.0 replaces this hook mechanism with the approach defined in OGC
20-010, and no Energy ADE has yet been released against CityGML 3.0. When one is,
the LCA ADE would need a parallel `core3`-based encoding of the same two
properties.

---

## Coverage summary

The following table summarises which parameters attach to which class, the
attachment mechanism, and the EN 15978 modules each supports.

| Category | Class | Module of origin | Added parameter(s) | Mechanism | LCA modules |
|---|---|---|---|---|---|
| General | `LCAScenario` (new, one or more) | LCA ADE | `referenceStudyPeriod` | top-level object | horizon for all B/C |
| Embodied | `AbstractDevice` | Devices | `environmentalId`, `referenceServiceLife` | formal hook | A1–A5, C1–C4, D, B4 |
| Embodied | `BuildingInstallation` / `IntBuildingInstallation` | CityGML Building | `environmentalId`, `referenceServiceLife` | formal hook | A1–A5, C1–C4, D, B4 |
| Embodied | `LayeredConstruction` / `ReverseLayeredConstruction` (layerless) | Layered construction | `environmentalId`, `referenceServiceLife` | convention injection | A1–A5, C1–C4, D, B4 |
| Embodied | `SolidMaterial` | Layered construction | `environmentalId`, `referenceServiceLife` | convention injection | A1–A5, C1–C4, D, B4 |
| Operational | `AbstractResource` | Resources | `environmentalId` | convention injection | B6, B7 |

## Known limitations

Two limitations are acknowledged and left for future work. First, a single
`Layer` in the Energy ADE `LayeredConstruction` can, in reality, consist of more
than one material — timber studs interleaved with insulation, or reinforced
concrete, for example — whereas the current model links a layer to a single
material. This could be resolved by introducing a material-fraction factor or a
recursive layered-construction structure. Second, most CityGML models are
available at best at LOD2, occasionally LOD3, so components crucial for a complete
LCA — interior walls, slabs and foundations — are frequently missing; increasing
the LOD, or supplementing the model with archetypes and semantic enrichment, is
required to close that gap. Both limitations concern the *quantities* feeding the
assessment rather than the LCA ADE parameters themselves, and neither affects the
validity of the additions specified here.
