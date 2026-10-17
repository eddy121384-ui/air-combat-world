# North Taiwan forest coverage data

See [usage, sources, limits and Unreal interface](../../../docs/north-taiwan-forest-coverage-v1.md).

`inputs_v1/` is the compact, checksum-verified offline source clip. `coverage_v1/`
contains actual full-world derived outputs; regenerate with
`python tools/ntw/forest_coverage.py build`. No tree models or reference photos.

Land cover: Esri / Impact Observatory / Microsoft, 2021, via mutolisp's pinned
EPSG:3826 derivative; CC BY 4.0. Modified here by categorical 20 m resampling,
reclassification, review masks and area aggregation; not a forestry survey.
Coast: MOI county boundaries 1140318 via a pinned, simplified third-party
derivative; Taiwan Open Government Data License 1.0. Projection, generic topology
repair and clipping disclosed in `inputs_v1/provenance.json`.

Retain attribution and provenance when distributing these derived masks.
