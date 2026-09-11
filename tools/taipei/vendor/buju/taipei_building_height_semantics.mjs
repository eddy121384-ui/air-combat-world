// Vendored from eddy121384-ui/Taipei-Maps (same owner):
//   tools/data/taipei_building_height_semantics.mjs
// Verbatim copy — height semantics are probe-verified, do NOT re-guess.
// Probe: 2026-08-20, Taipei 101 + Daan + Yangmingshan.
//   roof elev `1_top_high`, entrance elev `1_ent_heig`,
//   surveyed height `1_bud_high`, floors `1_floor`.
//   Identity: 1_bud_high == 1_top_high - 1_ent_heig row-by-row.
export const DEFAULT_BUILDING_HEIGHT_M = 9.6;
export const MAX_PLAUSIBLE_BUILDING_HEIGHT_M = 600;
export const MIN_PLAUSIBLE_BUILDING_HEIGHT_M = 1.2;

function finiteNumber(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === "string" && value.trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function firstFinite(properties, keys) {
  for (const key of keys) {
    const value = finiteNumber(properties[key]);
    if (value !== null) return value;
  }
  return null;
}

function plausibleHeight(value) {
  return (
    Number.isFinite(value) &&
    value >= MIN_PLAUSIBLE_BUILDING_HEIGHT_M &&
    value <= MAX_PLAUSIBLE_BUILDING_HEIGHT_M
  );
}

function rounded(value) {
  return value == null ? null : Number(value.toFixed(3));
}

/**
 * Derivation order:
 * 1. plausible surveyed `1_bud_high`
 * 2. plausible roof elevation - entrance elevation
 * 3. floors × 3.2 m
 * 4. generic 9.6 m
 */
export function deriveBuildingHeight(properties = {}) {
  const topElevation = firstFinite(properties, ["1_top_high", "屋頂高程"]);
  const entranceElevation = firstFinite(properties, ["1_ent_heig", "出入口高程", "1_entr_heig"]);
  const surveyedBuildingHeight = firstFinite(properties, ["1_bud_high", "1_bd_high"]);
  const floors = firstFinite(properties, ["1_floor"]);

  const elevationDelta =
    topElevation != null && entranceElevation != null
      ? topElevation - entranceElevation
      : null;
  const consistencyDiff =
    plausibleHeight(surveyedBuildingHeight) && plausibleHeight(elevationDelta)
      ? Math.abs(surveyedBuildingHeight - elevationDelta)
      : null;

  if (plausibleHeight(surveyedBuildingHeight)) {
    return {
      height_m: rounded(surveyedBuildingHeight),
      source: "1_bud_high",
      top_elev_m: rounded(topElevation),
      ground_elev_m: rounded(entranceElevation),
      elevation_delta_m: rounded(elevationDelta),
      surveyed_vs_delta_diff_m: rounded(consistencyDiff),
    };
  }

  if (plausibleHeight(elevationDelta)) {
    return {
      height_m: rounded(elevationDelta),
      source: "top_minus_entrance",
      top_elev_m: rounded(topElevation),
      ground_elev_m: rounded(entranceElevation),
      elevation_delta_m: rounded(elevationDelta),
      surveyed_vs_delta_diff_m: null,
    };
  }

  if (floors != null && floors >= 1 && floors <= 150) {
    const floorHeight = floors * 3.2;
    if (plausibleHeight(floorHeight)) {
      return {
        height_m: rounded(floorHeight),
        source: "floors_x3.2",
        top_elev_m: rounded(topElevation),
        ground_elev_m: rounded(entranceElevation),
        elevation_delta_m: rounded(elevationDelta),
        surveyed_vs_delta_diff_m: rounded(consistencyDiff),
      };
    }
  }

  return {
    height_m: DEFAULT_BUILDING_HEIGHT_M,
    source: "fallback_9.6m",
    top_elev_m: rounded(topElevation),
    ground_elev_m: rounded(entranceElevation),
    elevation_delta_m: rounded(elevationDelta),
    surveyed_vs_delta_diff_m: rounded(consistencyDiff),
  };
}
