# Xinyi Unreal V2 — Offline Contract Result

Date: 2026-09-22 Asia/Taipei  
Branch: `feat/xinyi-unreal-v2`  
Issue: #8  
Passing workflow: `35676287874` (run #2)  
Passing workflow head: `570d13f00264089d49b286536d737cca8a2ab432`

## Result

**PASS — engine-facing offline input contract is reproducible and ready for the first real UE5.8 import stage.**

This is not yet an Unreal runtime PASS. It proves that the already-validated
building and terrain pipelines can be regenerated together into one deterministic
engine input contract without changing either upstream geometry policy.

## Revalidated upstream inputs

The workflow regenerated the full Xinyi building set from the locked projected WFS
source and reproduced the accepted production baseline:

- source SHA-256:
  `c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d`
- 25 building tiles
- 485,936 triangles
- full building tile manifest SHA-256:
  `bfaf5ab05d3a792330fb96597766c41bdf979f68193bdc1447bdfca0fbb06a15`
- geometry failures: 0

The same run refetched the MOI 2025 DTM derivative mirror and reproduced the
accepted terrain + surveyed building-ground contract before generating Unreal data.

## Unreal Landscape contract

The Xinyi coverage is exactly a 5 x 5 grid of 500 m city tiles.

The engine contract therefore uses:

- Landscape heightmap: **631 x 631**
- Landscape components: **5 x 5**
- sections/component: **2 x 2**
- quads/section: **63**
- quads/component: **126**
- physical component size: **500 m**
- Landscape XY scale: **396.825396825 cm**
- Landscape Z scale: **200**

This makes one Unreal Landscape component exactly one existing 500 m Xinyi tile.

The 20 m MOI DTM is bilinearly oversampled to the 631 x 631 representation only
to satisfy Unreal Landscape topology. This does not increase terrain source
accuracy.

## Height result

Generated accepted-DTM height range across the Unreal contract:

- minimum: **0.477499762 m**
- maximum: **177.532293728 m**

Unreal uint16 encoding round-trip maximum absolute error:

- **0.007812492 m**

The generator fails instead of clipping if terrain cannot fit the locked
Landscape Z representation.

## Coordinate contract

The existing measured UE mapping remains:

```text
UE X = ENU east  * 100 cm
UE Y = ENU north * -100 cm
UE Z = ENU up    * 100 cm
```

Heightmap orientation is west-to-east by columns and north-to-south by rows, so
image row direction follows increasing UE +Y.

## Building Z contract

Surveyed WFS `ground_elev_m` remains authoritative for building base placement.

The engine-facing manifest contains:

- surveyed building Z records: **11,132**
- missing records: **0**

No per-building visual Z adjustment is introduced. Unreal must measure imported
mesh bases and apply the same uniform measured-base-to-surveyed-ground policy that
passed the Blender gate.

## CI validation

Contract unit tests:

- **4 passed**

Generated heightmap / manifest evidence:

- PNG SHA-256:
  `b1abea8620adf8329409e5546e5c75fe534c3060bfd119bfaed9863197bf1376`
- RAW16 SHA-256:
  `088c1b18c15a0b807348676e3568c99eb83b63444b0e7266078d673938f0594c`

Workflow artifact:

- name: `xinyi-unreal-v2-inputs`
- artifact ID: `10673126769`
- artifact SHA-256:
  `6c3b43aeff070b19ab9f8599f0071fa35c44d62832a5eb6f60a0e2b06a185ca0`

The artifact contains the 25 validated building GLBs, Full-Xinyi report,
terrain/building-Z evidence, Unreal heightmap files, and the engine contract JSON.

## UE5.8 stage prepared

The branch now includes:

- `adapters/unreal/xinyi_v2_api_probe.py`
- `adapters/unreal/import_xinyi_v2_buildings.py`
- `adapters/unreal/verify_xinyi_v2_building_import.py`
- `tools/unreal_xinyi_v2/run_local_gate.ps1`

The building importer uses the already-proven UE5.8 Interchange route, checks every
GLB SHA before import, keeps all content isolated under `/Game/XinyiV2`, disables
importer-default Nanite for the SM5/mobile baseline, saves the assets, and records
actual asset granularity.

A separate fresh UnrealEditor-Cmd process verifies that the imported assets and
Nanite-off state persisted.

The Landscape API is deliberately not guessed from older experimental Python APIs.
The probe records the actual Python surface exposed by the installed promoted UE
5.8 build. The subsequent Landscape creation/import script should be written from
that evidence.

## Next gate

Run the prepared UE5.8 local stage:

1. actual API probe;
2. verified-SHA import of all 25 building GLBs;
3. fresh-process building asset persistence check;
4. inspect actual Interchange asset granularity/names;
5. implement Landscape creation/import from the 631 x 631 accepted heightmap using
   the API surface proven by the probe;
6. create isolated `XinyiV2` level;
7. place terrain/buildings against measured bounds;
8. save, exit, fresh-reopen and remeasure.

Do not call XinyiV2 an Unreal PASS until those engine-side gates succeed.
