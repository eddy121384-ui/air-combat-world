# Xinyi urban identity — engineering plan (street / facade + school / campus)

Status: **audit + design + invisible foundation**. Nothing in this pass changes a tile, material, ground
texture, level or render. The visual implementation (Taipei Urban Identity Pass v0) is a later,
separate pass. Everything below was verified in code or data at HEAD `08d8b67`; claims that could not be
verified are marked **UNVERIFIED**.

**Policy decision (accepted): inferred running tracks stay DISABLED.** A campus whose open yard merely
has room for a 400 m oval is not evidence that a track exists. The future visual pass may use real /
tagged school and campus data, tagged pitches / courts / playgrounds and derived campus ↔ building
membership. A running track may be added only after that specific track is externally verified or comes
from a curated source with a citation. `track_candidate` in `campuses.json` is an audit hint, never a
render input, and there is no debug / art-review toggle that draws it.

Foundation added (all new files, none consumed by Unreal yet):

| file | purpose |
|---|---|
| `tools/lookdev/fetch_education_context.py` | snapshots the OSM education / sports features the ground fetch discards (campus relations, school buildings, pools, halls) into `data/lookdev_cache/osm_education_context.json.gz` (+ `.meta.json`, ODbL notice). `data/lookdev_cache/` is a versioned snapshot directory (locked inputs so machines without Overpass egress can rebuild), so the snapshot is committed like its siblings |
| `tools/lookdev/build_urban_identity.py` | deterministic **frontage** and **campus** metadata → `unreal/Saved/XinyiLook/urban_identity/` (`frontage.json.gz`, `campuses.json`, report, debug PNG) |

Run: `python tools/lookdev/fetch_education_context.py` (once, needs network) then
`python tools/lookdev/build_urban_identity.py` (≈ 35 s; needs the look tiles' `look_buildings.jsonl.gz`,
shapely / scipy / pillow like the other lookdev builders). Output is byte-identical across runs (sha256
in the report).

---

## 1. Existing facade pipeline (audit)

Flow: WFS footprints → accepted 25 runtime tiles → `tools/lookdev/build_look_tiles.py` re-emits the same
triangles with attributes → `M_XinyiCity` (one Custom node, `xinyi_city.hlsl`).

| item | what exists (verified) |
|---|---|
| per-vertex data | POSITION, NORMAL (planar face normal), TEXCOORD_0, TEXCOORD_1, TEXCOORD_2. No COLOR_0, no UV3. Material inputs: `WP, N, UV0, UV1, UV2, Night, LitFrac` |
| UV0 | walls: `(u = perimeter metres along the footprint ring, h = metres above surveyed ground)`; roofs / soffits: tile-local (east, north) m. `u` starts at a **mesh-index-dependent ring vertex** (`ring_params`, sorted vertex ids), so it is continuous around a building but is **not** a stable per-wall id |
| UV1 | `(record height_m, visual floor height m)` — constant per building record |
| UV2 | packed RGBA8 → `R = archetype*16 + variant`, `G = appearance seed` (per building *group*), `B = weathering 0..255`, `A = flags` |
| flags (A) | bit0 planned core, bit1 group anchor, bit2 podium part, bit3 rooftop structure. **Bits 4–6 are free**; bit7 / values ≥ 248 are reserved: the hero (Taipei 101) is tagged `A = 250` and tested with `step(0.97, A)` |
| archetypes | 0 low, 1 walkup, 2 huaxia, 3 res_tower, 4 office_glass, 5 commercial_podium, 6 civic. Code space allows 16 (`arch*16`): **7 is free** and is the natural slot for a school archetype. Landmarks already override archetype / variant from a registry (`lm_variant`) |
| facade orientation | **no per-wall side id.** The fragment has the world normal `N`, so the facade bearing is available per pixel in the shader; which wall faces which street is not known to the shader |
| floor info | `floorsTotal = round(H / fh)`, `fi = floor(h / fh)` computed per pixel from UV0.y / UV1 |
| seeds | per group seed (G), per bay hash from `(bay index, floor, seed)`, per-sign-cell hash from `u` |
| age / district | weathering B (core ×0.55), core flag |
| roof / wall | by normal (`isRoof = smoothstep(0.55, 0.75, N.z)`), soffit by `N.z < -0.7` |
| already in the shader | bay rhythm, balconies, enclosed balconies, **iron window cages (鐵窗)**, **AC condensers**, 騎樓 arcade + shop fronts + **sign band with pseudo-lettering**, rooftop sheet metal. All procedural, per bay, applied to **every** facade side of old stock alike (`isOld`, damped by `core`) |
| instancing infra | `place_hism` (xinyi_look_build_level.py): one holder + HISM per type, per-instance transform, **one custom-data float** = variant, `(v + 0.5)/variants` (256 variants used by rooftop sheets), per-type cull distances, shadows on/off. Props share `M_XinyiProps` (`xc_prop`, type ids 1–14 used, 10 = street lamp) |
| LOD / culling | tile meshes: single LOD, Nanite off, no cull distance (always drawn, 0.49 M triangles, 0.99 M welded vertices). HISM props: per-type cull (rooftop rooms 3.5–4.5 km, small clutter 0.6–0.9 km, trees 1.5–2.6 km); trees / lamps / props ≥ 24 tris get auto-LODs. Facade detail LOD is shader-side: `xc_detail(fwidth(...), period)` fades every pattern to its mean |

Consequence: the **facade identity already has a shader-painted baseline** (cages, ACs, shopfronts,
sign bands) that is blind to streets. The future pass is mostly (a) making that baseline street-aware and
(b) adding a thin layer of real geometry near the camera, not building from nothing.

## 2. Street / frontage information (audit)

| question | answer |
|---|---|
| road data available? | yes, `data/lookdev_cache/osm_xinyi_context.json.gz` (2.9 × 3.2 km): `highway` ways with class, lanes, width, oneway. `build_ground.py` turns them into a road SDF + class raster (B channel: 0 / .33 local / .66 collector / 1 arterial) at 1.22 m/px over 2.5 km, plus road paint and 4,913 lamps |
| used by buildings? | **no.** The building shader never sees roads. Ground uses road class only for kerb / asphalt treatment |
| building ↔ road relation | none stored. WFS buildings carry only `height_m, height_source, top_elev_m, ground_elev_m, floors` (no use, no name, no address) |
| facade facing a road | not available → derived by this pass (below) |
| corners, setbacks, frontage class, commercial frontage | not available → derived |
| road width / class | available in OSM (explicit `width` rare; widths come from lanes × 3.3 m in `way_geometry`) |

Derived (implemented, `build_urban_identity.py`): for every footprint **ring edge** ≥ 1.5 m — midpoint,
outward normal, candidate roads within 45 m; a road qualifies if its curb distance ≤ 16 m and the
direction to it is within 60° of the outward normal; nearest curb wins with a 2.5 m-per-class bias (a
main street 8 m away beats a parking-aisle `service` way 3 m away); the sight line to the road must not
cross another building of a different group (open view = real frontage, not an alley behind a block).
Per building: frontage length by class, best class (edges ≥ 3 m), **corner** (two substantial frontage
edges on different roads, normals ≥ 45° apart), **commercial candidate** (old shop-house archetypes +
podium, best class ≥ local, frontage ≥ 6 m).

Measured on the 8,085 street-relevant buildings (rooftop-structure records and hero excluded):

| | |
|---|---|
| buildings with any frontage | 5,852 (72 %), 17,688 frontage edges out of 80 k |
| frontage length by class | alley (service) 50.2 km · local 43.1 km · collector 7.9 km · arterial 9.2 km |
| corners | 1,767 |
| commercial candidates | 2,230 (walk-up 661, huaxia 1,136, low 408, podium 25); 1,148 of them are corners |
| facade area on frontage edges, old stock | 1.48 M m² (0.78 M m² on local-or-larger roads) |
| ground-floor commercial frontage | 58.2 km (45.2 km on local-or-larger) |
| size | `frontage.json.gz` 0.58 MB, `campuses.json` 0.12 MB |

Caveats: OSM `highway=service` is mapped on alleys *and* parking aisles — class 1 frontage is the
noisiest class (weight it down for signage). Frontage exists only inside the OSM bbox, which covers the
2 × 2 km WFS area. The planned-core blocks have large setbacks and little frontage by this rule.

Edge identity: `(building_id, part, ring edge index in the WorldModel footprint ring)` plus both
endpoints in ENU m. Because wall `u` is index-dependent, a consumer matches walls **geometrically**
(wall bottom-edge midpoint on the edge), or the tile build bakes the result (see §4).

## 3. School / campus / sports data (audit)

Verified against the cached ground context and a live Overpass query (OSM base 2026-07-15):

| data | in the **current cache** (used by ground art) | in OSM (now captured by the new fetch) |
|---|---|---|
| campus polygons | 5 closed `amenity=school/kindergarten/university` ways | **19 school + 1 university multipolygon relations** (仁愛 國中/國小, 三興, 信義 國中/國小, 博愛, 吳興, 興雅 國中/國小, 松山高中, 松山工農, 永春高中, 喬治商職, 東方工商, 光復, 大安, 永吉, 雙永, 立人, 臺北醫學大學) + kindergarten / seminary ways = **25 campuses**, 12 fully inside the WFS bbox |
| school buildings | none (building tags not fetched) | **138** `building=school/university/...` ways (classrooms, 活動中心, 行政大樓, 司令台, named wings), most inside campuses; 268 WFS buildings fall inside campus polygons |
| sports | 48 `leisure=pitch` → all painted as one "court" surface class: **sport type, orientation and size are discarded** (court colour = hash of 36 m cell) | per pitch: sport (basketball 16, tennis 11, multi 6, volleyball 5, badminton 3, baseball, roller), surface (tartan / acrylic / concrete…), polygon (mostly 5-vertex rectangles → exact orientation + size) |
| playgrounds | 22 → painted as vegetation (G channel) | 22 polygons (1 inside a campus) |
| pools / halls | pools: none; stadium: via `leisure` regex → "court" | 5 swimming pools, 2 school `leisure=stadium` activity halls |
| **athletics tracks** | `leisure=track` → "track" class (0.8, red PU in the ground shader): **0 elements, the track surface is never drawn** | **0** `leisure=track`, **0** `sport=athletics/running` in the bbox |
| schoolyards | the 5 school polygons only | derivable: campus polygon − buildings − sports (implemented) |
| court orientation | lost | yes (pitch MRR) |

So: campuses, school buildings and sports surfaces **exist in the source and are mostly discarded**;
tracks **cannot be known from OSM** here. Conservative derived signal: 6 campuses have an open yard that
could hold a 400 m oval (largest inscribed open rectangle ≥ 90 × 45 m) — flagged `track_candidate`
(audit hint only: **unverified, never rendered, no toggle**). The WFS has no school attribute; WFS-in-campus is a
geometric assignment (representative point inside the campus polygon); 138 OSM-tagged building footprints
also match WFS records by IoU ≥ 0.4 (stored as `wfs_building_id` where they match).

Not knowable from available data: which yard has a track, track lane count / exact geometry, court
markings beyond sport + size, covered walkways, school-specific facade colours.

## 4. Missing metadata → contracts to add

Generated now (`urban_identity/`):

* `frontage.json.gz` (`acw.frontage/0`): per building `{building_id, group, archetype, core, edges_total,
  edges:[{part, edge, p0, p1, len, normal_deg, front 1..4, road_id, road_hw, road_width, curb_m}],
  frontage_len_m, frontage_len_by_class, best_front_class, corner, commercial_candidate}`; only frontage
  edges are listed (absent = interior / blocked).
* `campuses.json` (`acw.campuses/0`): per campus `{id, aliases, name, level (elementary / junior_high /
  senior_high / vocational / k12 / kindergarten / university), amenity, area, bbox_coverage,
  complete_in_building_source, polygon, wfs_buildings[], osm_buildings[] (name, levels, wfs match),
  pitches[] (sport, surface, orientation_deg, length_m, width_m, polygon), playgrounds[], pools[],
  halls[], open_yard_area_m2, largest_open_rect, yard_basis, track_candidate}`; plus
  `orphan_education_buildings` and `sports_outside_campuses`.

Still missing / to add in the art pass (designed here, not built):

1. **Frontage → vertex**: bake `front class` (0–4) into **flags bits 4–6** in `build_look_tiles.py`
   (match each wall triangle's bottom-edge midpoint to a frontage edge). Zero new channels, hero tag
   untouched (max value 127 < 248). A second per-wall bit (corner) needs either a UV3 channel (writer +
   material input change, +8 B/vertex ≈ +8 MB) or archetype-style per-building data; start with bits 4–6.
2. **School archetype 7** (`ARCH_SCHOOL`) assigned to the 268 campus WFS buildings through the existing
   landmark-style override in `build_look_tiles.py` (group-level, so podium + wing stay consistent).
3. **Pitch surface records** with sport id and orientation for ground markings (data now in
   `campuses.json`; the ground texture stores only one class).
4. A **curated overrides file** for what OSM cannot give (tracks): `urban_identity/campus_overrides.json`
   `{campus_id: {track: {center, axis_deg, evidence}}}` with a source note per entry.
5. Signage atlas + metadata (§7).

## 5. Facade identity architecture (decision per layer)

Principle: *shader first, geometry only where silhouette matters at the distances flown, always opaque.*
Score = aerial / low-flight value ÷ (GPU + CPU + memory).

| layer | implementation | why |
|---|---|---|
| A. AC units | **hybrid**: keep the painted bay ACs (far / mid); add real boxes only within ~120–150 m using the existing 14-tri `ac` mesh as a HISM placed from frontage edges; shader painting fades out inside the geometry range | ACs read as silhouettes only up close; painted ACs already give the mid-range color rhythm. ~26 k potential instances if 1 per 30 m² of road-facing old facade, est. ~5 % within 150 m |
| B. Iron windows / grilles | **shader only** (exists); add a normal-map-style relief via the existing `nrm` output and gate density by frontage / archetype | geometry would be thousands of repeated cages for no aerial value; they are sub-pixel beyond ~60 m |
| C. Rain awnings | **instanced geometry** (8-tri sloped quad strip scaled to module length, one HISM, single opaque material, sign-palette colours) on frontage edges of commercial candidates | awning silhouettes + color blocks survive to ~400 m and break up the facade line; opaque = no sorting / alpha overdraw. ≤ 15 k total (58 km / ~4 m) |
| D. Vertical signs | **instanced quads / thin boxes**, perpendicular to the facade, atlas-textured, **opaque with an emissive mask** (not translucent, not alpha-cut); one HISM per aspect class | the strongest Taipei street cue from low flight; ~3–4 k total (≈ 1 per 18 m of local-or-larger commercial frontage + corners), cull ~700 m |
| E. Storefront signs | **shader atlas painting** on the existing sign band (replace the pseudo-glyph with an atlas lookup keyed by sign cell) | flat on the facade: no silhouette; one guarded texture sample, near-only (already `xc_detail` gated) |
| F. Large banners | **instanced quads** (opaque) on upper facades of huaxia / res_tower / podium with collector+ frontage; real-estate / project-ad category | mid-altitude color blocks; a few hundred instances |
| G. Utility clutter | **last / optional**: poles as street-furniture HISM (reuse lamp infra); no wires (alpha) | low aerial value; wires are sub-pixel and alpha-heavy |

Decals are not recommended on buildings (deferred decals cost a full-screen-ish pass and are not
available in the weak-GPU budget); a shader mask driven by the baked frontage bits is cheaper.

## 6. Deterministic facade distribution rules (start values, tune in the art pass)

Inputs: archetype, core flag, weathering (age proxy), frontage class, corner flag, floor index, edge
length. All hashes seeded by `(building seed, edge id, bay/slot)`; no per-building exceptions.

| archetype | AC | cages | awnings | signs | notes |
|---|---|---|---|---|---|
| walk-up / mixed-use (1) | highest; every second bay on road-facing floors ≥ 2, less on interior walls | most (existing 0.62 base) | on every commercial frontage edge | vertical every ~12–18 m + corners; ground-floor storefront band | strongest Taipei read; `commercial_candidate` gates signs / awnings |
| low shop-house (0) | high | high | on commercial frontage | frontage-class weighted | smaller roofs, more lean-to clutter already |
| huaxia (2) | moderate | some | partial (ground floor) | moderate, ground + 2nd floor | older half of the stock only (`weathering`) |
| res_tower (3) | regular grid (one per unit bay, aligned) | none | podium frontage only | restrained, entrance + 1 banner | clean, regular infrastructure |
| office_glass (4) | none | none | none | controlled: one lobby / tenant sign | no random clutter |
| podium (5) | rooftop chillers (exists) | none | continuous ground awning on collector+ | large horizontal + banner | commercial anchor |
| civic / landmark (6) | none | none | none | none unless the registry allows | preserve landmark logic |

Frontage modulates everything: class 4 / 3 → signage density ×1.0 + banners, class 2 → ×0.7, alleys
(class 1) → ×0.25 (mostly parking-aisle ways), interior walls → no signs / awnings, AC and cages at a
reduced "back-of-house" density (visible but unorganised). Core flag → ×0.45 clutter (matches the
rooftop pass). The existing shader gates (`isOld`, `core`) stay the master switches.

## 7. Signage atlas contract (no art yet)

* **Atlas**: 2048 × 2048 RGBA8 → BC7 (5.3 MB with mips), sRGB colour in RGB; **A = emissive mask** (lit
  letters / box). Optional second 1024² BC4 atlas only if a separate dirt mask is needed.
* **Layout**: bins by aspect ratio so cells pack without waste — vertical 1:4 (128 × 512 px), horizontal
  4:1 (512 × 128), square 1:1 (256 × 256), banner 3:1 (384 × 128), wide shopfront 6:1 (768 × 128). Mip
  gutter 4 px; text authored ≥ 2 px stroke at the cell resolution.
* **Metadata** `signage_atlas.json`: `{atlas, size, cells:[{id, category, aspect_class, rect_px, uv_rect,
  size_m {w, h}, lit (bool), color_family, style (box / panel / banner), text (audit only), set}]}` and
  `rules` (category weights per archetype / frontage class).
* **Categories (generic, original)**: 診所, 藥局, 補習班, 房仲, 餐廳, 小吃, 便利 / 零售 (generic), 手機 / 電器,
  美容 / 理髮, 停車場, 金融 (bank-like, generic), 建案 / 房屋廣告. **No trademarks, no real logos,
  no political / election content.** Replaceable *sets* (`set` field) leave room for themed packs later.
* **Aged / faded variants**: not extra atlas cells — a per-instance float (`fade`, from the hash) drives
  desaturation, value loss and a grime gradient in the shader. Illuminated vs plain: `lit` + emissive
  mask, scaled by `night` (no dynamic lights, same trick as lamps).
* **Assignment**: `cell = hash(building seed, edge id, slot) → category by the §6 weights → cell within
  the category`. Fonts must be OFL / free-redistribution CJK (e.g. Noto Sans CJK TC); the baking script
  records the font + version and renders deterministically offline (PIL).
* **Instance data**: custom data float 0 = cell index (16-bit packed into two floats if > 256 cells),
  float 1 = fade / lit / flip bits.

## 8. School / campus identity layer

Contract = `campuses.json` (preserve real geometry). What each real feature becomes:

| feature | source | representation |
|---|---|---|
| campus boundary | OSM relation polygon | ground classification (school yard class) + masks for the layer; **do not** draw a fence unless tagged (`barrier`) |
| classroom wings | WFS building geometry (268) + OSM name / levels | **existing geometry + `ARCH_SCHOOL` facade grammar**: long uniform window rhythm, open-air corridor line, pale school colour banding, flat roofs with tanks; no new mesh |
| courtyards / yard | campus polygon − buildings − sports | shared schoolyard surface (ground shader class) |
| pitches / courts | OSM pitches (sport, orientation, size) | **flat ground decal quads** (2-tri quads, one small HISM per sport with its marking material: basketball, tennis, volleyball, badminton, multi) laid 4 cm above terrain, colour from surface tag |
| playground | OSM polygon | ground surface class (soft colour block), no props |
| athletics track | **not in source** | **disabled.** Later, per verified track only: parametric oval (400 m: 2 × 84.4 m straights, 36.5 m radius, 8 lanes) drawn by **one flat quad + SDF shader**, from a curated entry with an external source. Inferred candidates are never drawn |
| central field | track infield / large pitch | same decal, grass colour |
| pools / halls | OSM | pools: flat blue decal; halls: existing WFS building |
| rooftop / utility | campus WFS buildings | rooftop pass already applies; school archetype keeps rooms rare |
| campus props (hoops, poles) | none in source | only if later justified (< 100 m); skip |

Never invent a campus: layout is data-driven; where only a classification exists (kindergartens, the
university) nothing beyond the school archetype + ground class is added.

## 9. Aircraft-distance LOD plan

| distance / altitude | facade identity that must survive | school identity |
|---|---|---|
| very close (< 150 m) | AC geometry, awnings, individual vertical + storefront signs, cage relief | facade structure, court markings, hoops (if built) |
| low flight (150 m – 1 km) | awning silhouettes, vertical-sign color, storefront color blocks, major AC clusters (shader) | classroom wings, courtyard, **track oval**, court / playground color blocks |
| mid altitude (1 – 4 km) | facade rhythm + dominant sign / awning color through material variation; banners | campus footprint, **running-track oval**, field / court palette, wing masses |
| high altitude (> 4 km) | collapses into the existing range tone (`bTone`, `hood`) | **campus geometry, oval track, field / court palette** stay readable (a 176 × 92 m oval is ≈ 165 px wide at 1 km, ≈ 33 px at 5 km, ≈ 16 px at 10 km at 1080p with a 60° vertical FOV) |

Rules: one representation per feature with a cull, not stacked LOD meshes; props fade out by cull
distance (never alpha); shader detail fades by `xc_detail` as today; ground decals have no cull (cheap).
No tiny prop is drawn beyond the distance where it covers ≥ ~2 px.

## 10. Performance budget (Intel UHD 770, 1080p, 16 GB shared)

Reference: current look scene ≈ 31 k rooftop + 26 k tree / lamp instances, 0.49 M tile triangles; rooftop
pass cost ≈ +0.2 … +2.7 ms; clouds measured separately.

| layer | total instances | visible (typ.) | triangles (total) | HISM comps | cull | notes |
|---|---|---|---|---|---|---|
| AC boxes | ≤ 26 k | 0.5 – 1.3 k | 0.36 M | 1–2 | 150 m | existing 14-tri mesh; no shadows |
| awnings | ≤ 15 k | 0.8 – 1.5 k | 0.12 M | 1 | 400 m | opaque, no shadows |
| vertical signs | 3 – 4 k | 0.2 – 0.5 k | 0.04 M | 2–3 (aspect) | 700 m | opaque + emissive; no shadows |
| banners | ~400 | ≤ 100 | < 0.01 M | 1 | 1.2 km | |
| pitch decals | 48 | ≤ 48 | ~100 | 1 | none | flat, 4 cm offset |
| track decals | ≤ 6 | ≤ 6 | 12 | 1 | none | SDF shader |
| **total new** | **≈ 45 k** | **≈ 1.5 – 3.5 k** | **≈ 0.5 M (if all visible: < 0.1 M)** | **≈ 8–10** | | draw calls +8–10 (+ HISM clusters) |

* **Textures**: signage atlas 5.3 MB (BC7) + optional mask; nothing else (decals are procedural).
* **Vertices**: bits 4–6 add no memory; a UV3 channel would add ~8 MB (avoid unless needed).
* **Material cost**: new shader work is behind per-building / per-edge coherent branches (the rooftop
  pass showed ~+2–3.5 ms when palette / weathering ran on every pixel, ~0 behind branches). Sign-band
  atlas sampling: one sample, gated by `xc_detail`. Props: reuse `M_XinyiProps` or one new unlit-ish sign
  material (≈ the rooftop prop cost).
* **Alpha overdraw**: none planned — every sign / awning / banner is opaque; no cutouts, no translucent
  cages / wires. The cloud lesson applies: the weak-GPU cost is pixel shading and one-time pass setup,
  not draw count (hidden / culled actors were free; 12 k culled actors were free).
* **CPU generation**: frontage 33 s, signage / awning placement is the same order (single-threaded numpy /
  shapely); HISM spawn in the editor is slow for tens of thousands of instances (the cloud scale test
  took ~8 min for 12 k actors; `add_instances` batches are far cheaper but check).
* **Risk watch**: AC geometry (largest count), HISM `set_custom_data_value` loop (per-instance Python
  calls at 45 k instances — batch it), per-pixel hash growth in the building shader (keep branches).

## 11. Recommended Opus implementation sequence

Ranked by (aerial + low-flight value) ÷ cost:

1. **Campus layer first** (data exists; high aerial value; small counts):
   (a) regenerate ground with the 25 campus polygons (school-yard class) and per-sport pitch decals from
   `campuses.json` (48 flat quads); (b) `ARCH_SCHOOL` for the 268 campus WFS buildings; (c) **tracks stay
   off** — OSM has none and inferred tracks are rejected; add one only when it is externally verified or
   curated with a citation (see risks).
2. **Frontage bake + street-aware shader** (no new geometry): flags bits 4–6 in `build_look_tiles.py`,
   then gate / weight cages, ACs, arcade and sign band by frontage class and corner; interior walls get
   back-of-house density. Biggest plausibility gain per ms; regression = intended visual change only.
3. **Awnings + vertical signs** (HISM + atlas) on commercial candidates; build `build_sign_atlas.py` and
   the atlas metadata contract first with ~40 cells.
4. **Storefront atlas on the sign band** (shader) and banners.
5. **Near-only AC geometry** + cage relief.
6. Utility clutter last (or skip).

Each step should be a separate commit with a before / after sheet and the same-session timing method
used for the rooftop and cloud passes.

## 12. Risks / open questions

* **Tracks are not in OSM** (0 elements). Decision taken: render none until a specific track is
  externally verified or curated (with a source note in `campus_overrides.json`). The 6 `track_candidate`
  campuses are rectangle-fit guesses and stay unrendered.
* **Ground regeneration** changes accepted ground pixels: adding the 20 campus relations to the school
  class repaints large yards — intended, but it breaks the pixel-identical regression for the ground.
* **Alleys vs parking aisles** (`highway=service`): noisy class-1 frontage; may need `service=alley` /
  `service=parking_aisle` tags (not fetched yet) if signage on alleys looks wrong.
* **Coverage**: WFS ≈ 2 × 2 km; 13 of 25 campuses lie partly / fully outside it (no WFS buildings) — only
  their OSM footprints exist; the far city has no per-building data for signs / awnings.
* **Frontage edge ↔ wall matching**: geometric matching of tile walls to ring edges must be validated
  (T-junctions, split walls); the sidecar stores endpoints so a tolerance match is possible, but this is
  **UNVERIFIED** until the bake is written.
* **flags bits**: only 3 bits free (4–6); more per-wall data needs a UV3 channel (writer, Interchange
  import, material input, +8 MB).
* **Material variant limit**: one custom-data float per instance (256 distinct sheet variants worked);
  signage needs 2 floats (`set_num_custom_data_floats(2)`).
* **Fonts / licensing**: CJK text baked into the atlas needs an OFL font and no real brands.
* **OSM license**: `osm_education_context` is ODbL data; the meta file carries the notice, and a
  derived-data attribution line is needed in any shipped credit.
* **Determinism**: hashing must stay seed-based (no `random`); the metadata generator already verifies
  identical output across runs.
* **What did not change**: no tile / material / ground / level / cloud / rooftop output; accepted DAY /
  DUSK / NIGHT baseline, rooftop identity, Taipei 101 and the cloud renderers are untouched (the new
  tools write only under `unreal/Saved/XinyiLook/urban_identity/` and a new cache file).
