# Taipei building era metadata v0

Status: **data / engineering foundation only.** No render, shader, geometry, rooftop or Unreal asset consumes it.
Code: `tools/building_era/` · Tests: `tests/test_building_era.py` · Caches: `data/lookdev_cache/`.

## 1. Schema (`acw.building_era/0`, `tools/building_era/era_schema.py`)

Per footprint (WFS `tp_building_height` feature id) — no parallel building database; the record is keyed by the
existing footprint id and aggregated to the existing look-dev building *group* on demand (`aggregate_group`).

| field | meaning |
|---|---|
| `construction_year` | observed completion year; **only** when `era_confidence == "exact"` |
| `year_min`, `year_max` | inclusive evidence bounds (equal when exact) |
| `era_bucket` | `pre_1980` · `1980_1999` · `2000_2009` · `2010_2019` · `2020_plus` · `unknown` |
| `era_source` | `open_use_permit` · `open_construction_permit` (reserved) · `profile_inference` · `unknown` |
| `era_confidence` | `exact` · `range` (coarse, one bucket) · `inferred` · `unknown` |
| `era_join` | how evidence reached the building (`parcel_overlap`) |
| `era_evidence` | sorted permit numbers (≤ 4) |
| `era_ambiguous` | several permits competed across buckets; bucket stays `unknown` |

`validate_record` enforces: inferred never poses as observed, observed never "inferred", year bounds lie inside the
bucket, and research-only sources are rejected.

**Buckets.** Boundaries are inclusive upper years: ≤1979, 1980–1999, 2000–2009, 2010–2019, ≥2020. 1999 (921
earthquake / code change) separates the tiled mid-rise stock from post-quake construction; the 2010s/2020s split
keeps the newest glass/premium stock separable. Five bands + unknown is deliberately the most a facade/roof/
construction grammar will plausibly art-direct, and none of it is Taipei-specific.

## 2. Sources actually used

| source | licence | role |
|---|---|---|
| 臺北市歷年使用執照摘要, data.gov.tw/dataset/128203 (Taipei Building Management and Engineering Office) | Government Open Data License v1.0 | permit year, height, parcel list (new builds only, 2001–2025) → **era evidence** |
| accepted EPSG:3826 footprints (`sample_buildings_epsg3826.geojson.gz`) | as already accepted | targets of the join |
| Dashboard WFS `building_cadastralmap` parcel polygons | **UNVERIFIED** (same WFS family as the accepted footprint source) | **join geometry only** — fetched to the gitignored `data/generated/taipei/era/`, never committed, never emitted |

Raw permit XML (68 MB, sha256 in the meta) is not committed. `taipei_use_permits.py` reduces it to a 271 KB compact
cache of 7,799 new-build permits; `build_era_metadata.py` reads only caches (no network) unless `--fetch-parcels`.
Retrieval date, URL, licence, raw hash and cache hash are in `taipei_use_permits_new_build.meta.json`.

## 3. Licence status

* Permits: open (OGDL v1, attribution to the Building Management and Engineering Office).
* **City Dashboard `building_age`: research-only, not used.** Licence unverified; nothing was fetched, cached,
  committed, or used to derive priors. Tests assert no file in the repo data dirs carries it, no era tool references
  its WFS type name, and the cache meta lists it under `research_only_not_used`. `RESEARCH_ONLY_SOURCES` makes
  `validate_record` reject it as a source.
* **Open item to resolve:** the parcel layer used for joining has the same unverified status as the footprint
  source the project already ships. Only permit-derived values attach to footprint ids in the committed output;
  parcel geometry is not distributed. Data.gov.tw's open 臺北市數值地籍地段圖 (157685) was checked and is
  *section* (地段) level, not parcels, so it cannot replace it. If the user wants the join dependency removed
  entirely, the committed cache can still be used as-is; a rebuild needs the parcel layer or a licensed substitute.

## 4. Join method

1. Permit parcels → key `段小段|8-digit 地號` (matches WFS `kcnt` + `aa49`).
2. Footprint is a **candidate** for a permit when ≥ 60 % of its area lies in the union of that permit's parcels.
3. Candidate rejected when its height exceeds the permit height by more than max(3 m, 25 %) (`height_conflict`) —
   e.g. a 3 m permit sharing a parcel with an 18 m building never dates that building.
4. Candidates fold through `resolve_candidates`, which depends only on the *set* of candidates:
   one year → `exact`; several years in one bucket → `range` (no year); several buckets → `unknown` +
   `era_ambiguous` with evidence kept. A permit is never picked at random.

Permit-number join is not available (footprints carry no permit ids); bare spatial containment is not used.
Permit year = completion year if within 2 years of the issue year, else issue (use-permit) year.

## 5. Coverage (Xinyi look-dev extent, 11,132 footprints, 4,137 building groups)

| | footprints | groups |
|---|---|---|
| exact year | 1,214 (10.9 %) | 520 (12.6 %) |
| range (single bucket) | 332 | 145 |
| era known (exact + range) | 1,546 (13.9 %) | 665 (16.1 %) |
| unknown | 9,586 (86.1 %) | 3,472 (83.9 %) |
| ambiguous (subset of unknown) | 241 | 0 |

Buckets (groups): 2000_2009 = 479, 2010_2019 = 167, 2020_plus = 19, unknown = 3,472; all known are `open_use_permit`.
Joins: 7,799 permits; 268 have a parcel in the extent, **225 matched footprints (84 %)**, 43 matched parcels but no
footprint (lot renumbering / demolished / outside footprints), 7,531 are elsewhere in Taipei. 842 candidate
pairings were rejected by the height guard.

Coverage is low by construction: permits start in 2001, so every pre-2001 building is unknown. Absence of a permit
is **not** treated as "old". These numbers were not tuned; the 60 % overlap and height guard were fixed before
looking at yield.

## 6. Ambiguous cases

241 footprints are ambiguous (permits on shared parcels, e.g. multi-phase developments, with years in different
buckets). They remain `unknown` with the competing permit numbers in `era_evidence`. At group level an ambiguous
member does not vote; all 4,137 groups resolved without conflict. A group whose observed members disagree across
buckets becomes ambiguous/unknown.

## 7. Unknown / fallback

`EraInferer` (`era_schema.py`) is the CityProfile hook: it may return only `profile_inference`/`inferred` records,
sees only licensed attributes (district, floors, height, class, morphology), and is consulted only for unknown,
non-ambiguous buildings. v0 ships `NullInferer`: there is not yet enough licensed evidence for trustworthy priors,
so older buildings stay **unknown** rather than getting fake precision. (The priors that the research doc derived
from `building_age` were not reused.)

## 8. Determinism

Outputs are gzip-`mtime=0`, sorted keys. Rebuilding three times gave sha256 `2332a914…159b` each time. Tests cover
repeated rebuild, shuffled permit/parcel/footprint order, ambiguous-match resolution, exact bucket boundaries
(1979/1980, 1999/2000, 2009/2010, 2019/2020), provenance labels, missing data, and the cache hash vs. its meta.

## 9. Future integration points

`load_records()` → per-footprint `EraRecord`; `aggregate_group()` → per look-dev group (`classify` records carry the
group id). A later pass may add `era_bucket` as a look-dev record field feeding facade/roof/construction grammar;
construction-site work can add `open_construction_permit` (source constant reserved) for permits without a use
permit. Nothing is wired now.

## 10. Explicit non-use of City Dashboard age data

See §3. No `building_age` response was requested, stored, or used for matching, validation, priors or tuning.

## Reproduce

```
python tools/building_era/taipei_use_permits.py --force      # network; or --xml PATH
python tools/building_era/build_era_metadata.py --groups     # offline except missing parcel cache
python -m unittest tests.test_building_era
```
