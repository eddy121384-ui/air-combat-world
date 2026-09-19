# Xinyi Robust Whitebox v2 — Source Geometry Audit

Date: 2026-09-20  
Baseline: `main@08afe383d1b89a745f78f17d1930a75f045cec7a`  
Scope: pinned Xinyi sample only; no production-route decision yet.

## Why this audit exists

PR #3 proved that the v0 custom cap winding was wrong, but it did not explain
why roughly half the source buildings never became useful solids. v2 therefore
separates two failure classes before touching Unreal:

1. source geometry that has already lost area; and
2. valid area-bearing geometry that a triangulation/extrusion stack must handle.

A mature geometry library can solve class (2). It cannot reconstruct coordinates
that are already missing from class (1).

## Pinned-snapshot findings

The committed `sample_buildings.geojson` contains:

- 11,132 features;
- 11,132 geometries encoded as GeoJSON `MultiPolygon`;
- 11,136 polygon parts;
- 715 features/parts with one or more interior rings (holes);
- 5,297 exterior polygon parts with fewer than three distinct XY coordinates;
- coordinates observed at no more than four decimal places in EPSG:4326.

At Xinyi latitude, a 0.0001-degree grid is approximately 10.1 m east-west and
11.1 m north-south. That is coarse enough to collapse small Taipei building
footprints to a line or point.

The current downloader does not round coordinates: it writes
`feature.geometry` from the WFS response directly. The precision loss is
therefore upstream of the custom triangulator.

## Relationship to the legacy 5,296 zero_area count

The source snapshot contains 5,297 collapsed polygon parts. One collapsed
feature belongs to the Taipei 101 hero stack and is suppressed before Layer A
meshing. The remaining 5,296 match the legacy Layer A `zero_area` count.

This changes the diagnosis materially:

> The huge `zero_area` population is primarily source-footprint collapse, not
> 5,296 independent triangulator failures.

The old custom geometry layer still has real correctness problems on
area-bearing polygons (PR #3 / folded low-rise evidence), but replacing ear
clipping alone cannot recover these 5,296 footprints.

## Hole handling bug in v0 WorldModel

The WFS snapshot contains 715 polygon parts with interior rings. v0
`worldmodel.py` stored only `poly[0]` and silently discarded every hole
before triangulation.

The v2 branch changes WorldModel additively:

- existing `footprint_lonlat` / `footprint_enu` remain the exterior ring,
  so the baseline compiler behavior is preserved;
- `holes_lonlat` / `holes_enu` preserve interior rings for GEOS;
- `source_geometry_type` and `source_polygon_index` preserve provenance.

No v0 triangulation behavior is changed by this addition.

## v2 geometry policy

For area-bearing inputs:

- Shapely/GEOS owns validity and `make_valid(structure)`;
- lower-dimensional collapse is rejected, never inflated into a fake building;
- mapbox-earcut, through trimesh, owns triangulation;
- trimesh owns extrusion;
- numerical acceptance requires finite vertices, no zero-area triangles,
  watertight + consistent winding + positive closed volume, roof +Y, base -Y,
  and source-height preservation.

No new custom triangulator, hole bridge, or polygon repair is permitted.

## Precision probe

Before declaring the Taipei WFS unsuitable as a footprint source, v2 probes the
same WFS bbox twice:

1. GeoJSON output in `EPSG:4326` (current route);
2. GeoJSON output reprojected by GeoServer to Taiwan TWD97/TM2
   `EPSG:3826`.

If the projected response preserves additional coordinate precision and turns
collapsed 4326 features back into area-bearing polygons, the preferred fix is
to repin Taipei geometry in the higher-precision projected route and transform
that to theater ENU. If it does not, the project must evaluate a different
authoritative footprint source/format rather than inventing geometry.

The probe is diagnostic and never overwrites the pinned source snapshot.

## Gate decision

The 50–100 building mature-library spike should continue on the area-bearing
source population because it still answers whether the custom geometry layer
can be replaced cleanly.

Full-Xinyi v2 generation is **not** automatically authorized by a successful
mesh test. Before scaling, review both:

- the representative mesh gate / Blender inspection; and
- the WFS precision probe / footprint-source decision.

This keeps the strategic question intact: the production method must scale to
the Taipei Basin without silently losing half the city or requiring district-
by-district manual reconstruction.
