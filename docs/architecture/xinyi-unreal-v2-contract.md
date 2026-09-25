# Xinyi Unreal V2 — Offline Input Contract

Status: first engine-gate stage.

This contract sits between the already-passing Xinyi building/terrain pipelines and
the first UnrealEditor-Cmd import run. It exists so Unreal cannot silently invent a
second coordinate system, second terrain source, or ad-hoc building Z policy.

## Frozen upstream inputs

Buildings remain the validated Full-Xinyi output:

- projected WFS source SHA-256:
  `c7ca8da13a4c5baaab0fbd1fcfe5b3799723d49d1998f804cf1593904f70200d`
- full tile manifest SHA-256:
  `bfaf5ab05d3a792330fb96597766c41bdf979f68193bdc1447bdfca0fbb06a15`
- 25 x 500 m tiles
- 11,130 mesh components
- building XY geometry immutable

Terrain remains the accepted MOI 2025 20 m bare-earth DTM derivative path from
`docs/xinyi-terrain-v0-dtm-result.md`. Copernicus GLO-30 DSM is not an accepted
urban-ground source.

## Coordinate mapping

The previous UE 5.8 spike empirically validated:

```text
ENU east  -> UE +X
ENU north -> UE -Y
ENU up    -> UE +Z
metres    -> centimetres
```

Therefore:

```text
UE_X_cm = east_m  * 100
UE_Y_cm = north_m * -100
UE_Z_cm = up_m    * 100
```

Unreal import scripts must measure imported bounds and verify this mapping rather
than trusting asset origins.

## Why the Landscape heightmap is 631 x 631

Xinyi terrain currently covers a deterministic 5 x 5 grid of 500 m tiles.

Unreal Landscape can use 2 x 2 sections per component with 63 quads per section:

```text
126 quads / component
5 components / axis
5 * 126 + 1 = 631 height samples
```

That gives a useful property:

**one Landscape component = exactly one existing 500 m Xinyi tile.**

The corresponding XY scale is:

```text
500 m / 126 quads = 3.968253968 m / quad
Landscape Scale X/Y = 396.8253968 cm
```

The source is still a 20 m DTM. The 631 x 631 grid is bilinear oversampling only
for Unreal Landscape topology and tile/component alignment. It does not claim
approximately 4 m source accuracy.

## Height encoding

The contract uses Unreal Landscape's uint16 height convention:

```text
height_cm = (uint16 - 32768) * ScaleZ / 128
```

For Xinyi v2 the initial locked `ScaleZ` is 200. This covers the validated Xinyi
height range while retaining centimetre-class quantization. Generation fails
instead of clipping if the accepted terrain falls outside the representable range.

Both outputs are emitted:

- 16-bit grayscale PNG
- little-endian RAW16 (`.r16`)

The generator reopens the PNG and requires sample-exact equality.

## Image orientation

The raster contract is:

- column 0 = west / minimum east
- columns advance east
- row 0 = north / maximum north
- rows advance south

Rows therefore advance in Unreal +Y under the validated `UE Y = -north` mapping.

## Building Z

The existing surveyed WFS `ground_elev_m` remains the building-base source.
The engine-facing manifest converts it to centimetres only:

```text
UE building ground Z = ground_elev_m * 100
```

As in Blender, the Unreal stage should measure each imported object's actual world
base and apply one uniform measured-base-to-surveyed-ground policy. Do not assume
the importer's pivot/base is exactly zero.

## Generated evidence

`tools/unreal_xinyi_v2/build_contract.py` produces:

- `xinyi_unreal_v2_contract.json`
- `xinyi_moi2025_landscape_631.png`
- `xinyi_moi2025_landscape_631.r16`
- `building_ground_ue_cm.json`

The contract records every building tile's validated GLB SHA-256, ENU origin,
expected UE translation, node count and triangle count.

The CI workflow regenerates the accepted upstream building and terrain inputs,
checks their locked hashes, builds this contract, runs unit tests and uploads one
input artifact for the subsequent Unreal stage.

## Next gate

The next code must run inside UnrealEditor-Cmd and:

1. import the 25 validated building GLBs under an isolated `/Game/XinyiV2` path;
2. import/create the 631 x 631 Landscape with 5 x 5 components;
3. measure actual imported bounds;
4. place Landscape/buildings against this contract;
5. save the map;
6. exit the editor;
7. launch a fresh process and re-measure everything.

Same-session success is not persistence evidence.
