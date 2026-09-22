# Xinyi Unreal V2 — Stage 1 Offline Contract Result

Date: 2026-09-22 Asia/Taipei  
Issue: #8  
Branch: `feat/xinyi-unreal-v2`

## Result

**PASS_CONTRACT.**

The first Unreal gate stage now regenerates the already-validated Full-Xinyi
building set and accepted MOI 2025 DTM, then emits deterministic engine-facing
inputs without changing building geometry or inventing a second elevation model.

Passing GitHub Actions runs:

- run #2: `35676287874`
- run #3: `35676518722`

Run #2 evidence artifact:

- name: `xinyi-unreal-v2-inputs`
- artifact ID: `10673126769`
- artifact ZIP SHA-256:
  `6c3b43aeff070b19ab9f8599f0071fa35c44d62832a5eb6f60a0e2b06a185ca0`

## Landscape contract

The current Xinyi grid is 5 x 5 existing 500 m tiles.

The engine-facing Landscape contract is:

| Property | Value |
|---|---:|
| Height samples | 631 x 631 |
| Landscape components | 5 x 5 |
| Sections / component | 2 x 2 |
| Quads / section | 63 |
| Quads / component | 126 |
| Component width | exactly 500 m |
| Total width | 2.5 km |
| XY scale | 396.8253968 cm |
| Z scale | 200 |
| Generated elevation min | 0.477500 m |
| Generated elevation max | 177.532294 m |
| Max uint16 encode/decode error | 0.007813 m |

This is a deliberate one-to-one alignment:

```text
1 existing city tile == 1 Unreal Landscape component
```

The 631 x 631 topology is not arbitrary. Epic's UE 5.8 Landscape Technical Guide
uses 631 x 631 as a valid example and documents the general
`(A * quads + 1, B * quads + 1)` rule. With 2 x 2 sections of 63 quads,
a component contains 126 quads. Five such components therefore require
`5 * 126 + 1 = 631` samples.

Official references:

- https://dev.epicgames.com/documentation/en-us/unreal-engine/landscape-technical-guide-in-unreal-engine
- https://dev.epicgames.com/documentation/en-us/unreal-engine/importing-and-exporting-landscape-heightmaps-in-unreal-engine

UE 5.8 officially supports 16-bit grayscale PNG and 16-bit R16 heightmaps. Both
are generated and hash-locked by this stage.

The underlying terrain is still the MOI 2025 **20 m** bare-earth DTM. Sampling it
onto 631 x 631 only provides a valid Landscape topology and exact 500 m component
alignment. It does not claim approximately 3.97 m terrain source accuracy.

## Building contract

The stage regenerates and locks:

- 25 validated Full-Xinyi building GLBs;
- frozen WFS source SHA-256
  `c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d`;
- frozen tile-manifest SHA-256
  `bfaf5ab05d3a792330fb96597766c41bdf979f68193bdc1447bdfca0fbb06a15`;
- 11,132 surveyed WFS building-ground anchors;
- 0 missing building-ground anchors.

The validated engine axis contract remains:

```text
UE X = ENU east  * 100 cm
UE Y = ENU north * -100 cm
UE Z = ENU up    * 100 cm
```

No per-building visual terrain fitting is allowed.

## Generated files

The CI artifact contains:

- `unreal/Saved/XinyiUnrealV2Contract/xinyi_unreal_v2_contract.json`
- `unreal/Saved/XinyiUnrealV2Contract/xinyi_moi2025_landscape_631.png`
- `unreal/Saved/XinyiUnrealV2Contract/xinyi_moi2025_landscape_631.r16`
- `unreal/Saved/XinyiUnrealV2Contract/building_ground_ue_cm.json`
- all 25 validated building GLBs;
- Full-Xinyi numerical report;
- terrain DTM report;
- MOI derivative-mirror provenance receipt.

Run #2 generated:

- PNG SHA-256:
  `b1abea8620adf8329409e5546e5c75fe534c3060bfd119bfaed9863197bf1376`
- R16 SHA-256:
  `088c1b18c15a0b807348676e3568c99eb83b63444b0e7266078d673938f0594c`

The PNG is reopened after generation and must reproduce the uint16 array exactly.

## UE5.8 local engine gate prepared

The repository now contains:

- `adapters/unreal/xinyi_v2_api_probe.py`
- `adapters/unreal/import_xinyi_v2_buildings.py`
- `adapters/unreal/verify_xinyi_v2_building_import.py`
- `adapters/unreal/probe_xinyi_v2_building_bounds.py`
- `tools/unreal_xinyi_v2/run_local_gate.ps1`

The local gate deliberately stops before actor placement. It first runs the actual
installed UE 5.8 promoted build to determine:

1. the exposed Landscape/Python API surface;
2. whether all 25 GLBs import and save;
3. whether the saved StaticMeshes persist after a fresh process;
4. whether Nanite remains disabled for the SM5/mobile baseline;
5. whether Interchange bakes glTF node translations, retains the 500 m tile-local
   coordinate frame, or recenters StaticMesh assets.

That last measurement is required before any placement script is allowed to encode
an engine-transform policy.

## Next gate

Once the UE bounds receipt establishes actual importer behavior:

1. choose and implement the deterministic building actor/scene placement strategy;
2. create/import the 631 x 631 Landscape from the same MOI DTM contract;
3. save;
4. exit;
5. fresh-reopen;
6. remeasure terrain/building placement;
7. only then evaluate World Partition / streaming / HLOD and runtime performance.

No facades, roads, vegetation, material polish, gameplay, or wider-Taipei expansion
belongs in this stage.
