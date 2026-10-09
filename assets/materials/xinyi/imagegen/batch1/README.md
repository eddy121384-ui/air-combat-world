# Taipei material ImageGen batch 1

Six independent original AI sources for artistic review. **Three accepted as offline source candidates;
three need revision. This is not a production-ready six-material pack.** No Unreal integration or runtime atlas.

![Original source contact sheet](review/contact_sheet.png)

![Raw and processed 3x3 repetition review](review/tiling_review.png)

## Git baseline and scope

Fetched `origin/feat/opus55-xinyi-visual-quality` on 2026-10-09. Full remote starting SHA:
`ede7960d8ec05b2aa521b1e4c65b5bbd667c456d`. Required `ede7960` ancestry verified.
Created `spike/xinyi-material-imagegen-batch1` directly from that remote tracking commit in a
clean isolated clone. The pre-existing local checkout had untracked Unreal content and was left intact.
PR target: `feat/opus55-xinyi-visual-quality`; no merge is authorized by this package.

Read the library spec, facade-material pilot and facade-grammar v0A before generation.
The handoff explicitly asks for three color bases in addition to masks; this supersedes the older
mask-only generation queue for this isolated art study. It does not change the procedural palette strategy.

## Generation and provenance

Actual capability: **built-in `image_gen.imagegen`** through the imagegen skill. No stock textures,
web photos, Fab assets, copied repo images, or procedural noise substituted for source art.
Seven independent generation attempts: six selected original outputs, one rejected A2 aggregate attempt
for excessive speckle. The rejected image is not committed; its prompt, original filename, hash,
dimensions and reason remain in the manifest/log. Each selected image came from its own generation call,
without image references. The tool did not expose an underlying model ID, seed or reproducible request ID.
Generation date: 2026-10-09. Prompts are recorded in full in `manifest.json` and `generation_log.json`.

`sources/` contains byte-identical **1254 x 1254** native tool outputs, including embedded PNG metadata.
The requested 1024 size was not returned natively. `normalized_1024/` contains six clearly derived
1024 x 1024 review copies; these are not additional independent AI sources and are not all accepted.
A-series copies are RGB. The native B-series images are visually grayscale RGB with measured channel
drift of 5-7 levels; B-series normalized and processed copies are strict single-channel L PNGs.
No original file was overwritten or silently desaturated.

No third-party source licensing dependency is known. AI generation is the documented provenance;
uniqueness, legal clearance and provider training provenance were not independently certified.

## Artistic and tiling decisions

| ID / exact source filename | Status | Repetition result |
|---|---|---|
| A1 `a1_taipei_aged_ceramic_tiles.png` | Needs revision | Restrained off-white occupied-apartment tile identity, but partial border tiles and grout phase cause repeat joins on both axes. No accepted processed material. |
| A2 `a2_taipei_washed_aggregate_plaster.png` | Accepted for offline review | Revised fine mineral plaster is quiet enough; raw tonal edge steps corrected in candidate. Broad mottling still recurs. This represents the plaster option rather than strongly exposed aggregate. |
| A3 `a3_taipei_modern_stone_cladding.png` | Needs revision | Credible neutral matte stone; running-bond joints fail to close across tile boundaries. Fine grain also needs distance filtering. No accepted processed material. |
| B1 `b1_taipei_weathering_field.png` | Accepted for offline review | Broad damp shapes retained after low-pass, level remap and border blend. Edge jump removed; recognizable stain groups still recur at the 32m period. |
| B2 `b2_taipei_repair_zones.png` | Needs revision | Distinct human repaint structure, but coverage is excessive, patches are oversized, and repetition becomes camouflage-like. Border-clipped patches remain. No accepted processed material. |
| B3 `b3_taipei_rain_run.png` | Accepted for offline review | Uneven vertical runs retain gravity direction after low-pass and border blend. Edge jump removed; group repetition remains visible. |

All six were directly inspected individually and in the final sheets. No windows, building elevations,
text, people, brands or strong directional sunlight were seen. A1/A3 fine construction detail is a
close-view source study, not evidence of aerial benefit. B1/B3 sources were too finely textured to use
unchanged; derivative filtering is mandatory for the accepted candidates.

The compact tiling sheet shows unaltered-source 3x3 repeats on the left, accepted derivative 3x3 repeats
on the right, and explicit revision placeholders where no derivative was accepted. The contact sheet
shows all six original samples with filenames, labels, generation method and review status.

### Documented deterministic processing

Implemented in `build_review.py` (offline Pillow/NumPy helper only; no runtime dependency or dependency
manifest change): Lanczos resize to 1024; explicit L conversion for masks. For B1/B3 only, Gaussian blur
sigma 8px (~0.25m at the proposed 32m wall span), then linear min/max remap to numeric 112..144.
For A2/B1/B3, opposing border samples blend toward their shared average over 64px, with
`weight = 0.5 * (1-i/63)^2`, horizontal then vertical. No mirrored extension, generated noise or
invented replacement shapes. This changes the edge band and can soften features there.

Candidate opposing-edge MAE is **0 on both axes** (8-bit values), independently asserted by validation.
Matching pixel boundaries is a technical check, not proof of invisible repetition or gradient continuity.
Every source and output has a SHA-256; raw edge metrics are included in the manifest.
No gamma conversion is hidden: masks are numerical grayscale authoring data, not imported textures.
Any later engine import must explicitly choose linear/non-sRGB sampling and the agreed mask semantics.

### Distance limits

No Unreal, flight, performance, lighting or A/B test was performed. At the documented 1080p / 60-degree
vertical FOV assumption, a 2m feature projects to approximately 12/6/3/2px at 150/300/600/800m.
The 32m mask mapping is a proposal inherited from the spec. These sheets do not establish in-engine scale
or lack of shimmer; subpixel tile joints and stone grain should not drive the eventual aircraft material.
Final artistic review must judge broad material identity, maintained ageing intensity and repeated groups.

## Counts and validation

| Category | Count |
|---|---:|
| Generation attempts | 7 |
| Rejected generation attempts | 1 |
| Selected independent AI originals | 6 |
| Accepted independent sources for offline review | 3 |
| Selected sources needing revision | 3 |
| Normalized 1024 review copies | 6 |
| Accepted processed game material candidates | 3 |
| Total derived asset images (normalization + processing) | 9 |
| Review sheets | 2 |
| Total tracked PNG files | 17 |
| Production atlases | 0 |
| Images imported into Unreal | 0 |

Validation: all 17 PNGs decode; native originals are 1254 square; nine asset derivatives are 1024 square;
all six B-series derivatives are L; manifest hashes match; both review sheets contain six labeled entries;
candidate borders match exactly; original copies match the tool output bytes. The manifest distinguishes
source acceptance from eventual artistic approval. No missing planned source, but only half of the pilot
currently qualifies for further material-candidate review.

Portable audit from this directory: `python build_review.py --validate` (Pillow and NumPy needed).
Rebuilding initially copies the native tool files referenced in `generation_log.json`, so it uses the
author's local generation paths; validation only uses the committed package.

No Unreal runtime, shaders, geometry, generated UE content, main branch or existing Draft PR changed.
Stop at Draft PR review. No Unreal integration or merge has occurred.
