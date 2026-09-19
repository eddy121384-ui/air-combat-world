// Xinyi v2 source fetch: preserve footprint precision by asking GeoServer
// for projected TWD97/TM2 coordinates (EPSG:3826), while keeping the same
// 4326 bbox and the same surveyed-height semantics as the pinned v0 sample.
//
// Generated source is intentionally separate from the v0 EPSG:4326 snapshot.
// Usage: node tools/citygen_v2/fetch_projected_sample.mjs
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { deriveBuildingHeight } from "../taipei/vendor/buju/taipei_building_height_semantics.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..");
const OUT_DIR = path.join(REPO, "data", "generated", "taipei");
const OUT_GEOJSON = path.join(OUT_DIR, "sample_buildings_epsg3826.geojson");
const OUT_MANIFEST = path.join(OUT_DIR, "sample_buildings_epsg3826.manifest.json");

const ENDPOINTS = [
  "https://citydashboard.taipei/geo_server/taipei_vioc/ows",
  "https://citydashboard.taipei/geo_server/ows",
];
const TYPE_NAME = "taipei_vioc:tp_building_height";
const INPUT_BBOX_CRS = "EPSG:4326";
const OUTPUT_CRS = "EPSG:3826";
const BBOX = "121.5546,25.0247,121.5744,25.0427";
const PAGE_SIZE = 5000;

function makeUrl(base, params) {
  const url = new URL(base);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
  }
  return url;
}

async function fetchText(url) {
  const res = await fetch(url, {
    headers: {
      Accept: "application/json, application/geo+json, application/xml, text/xml, */*",
      "User-Agent": "air-combat-world/xinyi-v2-projected-source",
    },
    redirect: "follow",
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} ${res.statusText}; ${text.slice(0, 300).replace(/\s+/g, " ")}`);
  }
  return text;
}

function parseHitCount(xml) {
  const m = xml.match(/(?:numberMatched|numberOfFeatures)=["'](\d+)["']/i);
  return m ? Number(m[1]) : null;
}

async function getHits(base) {
  const xml = await fetchText(makeUrl(base, {
    service: "WFS",
    version: "2.0.0",
    request: "GetFeature",
    typeNames: TYPE_NAME,
    resultType: "hits",
    srsName: OUTPUT_CRS,
    bbox: `${BBOX},${INPUT_BBOX_CRS}`,
  }));
  return parseHitCount(xml);
}

async function getPage(base, startIndex) {
  const text = await fetchText(makeUrl(base, {
    service: "WFS",
    version: "2.0.0",
    request: "GetFeature",
    typeNames: TYPE_NAME,
    outputFormat: "application/json",
    srsName: OUTPUT_CRS,
    bbox: `${BBOX},${INPUT_BBOX_CRS}`,
    startIndex,
    count: PAGE_SIZE,
  }));
  const gj = JSON.parse(text);
  if (gj?.type !== "FeatureCollection" || !Array.isArray(gj.features)) {
    throw new Error(`unexpected GeoJSON shape: ${gj?.type ?? "unknown"}`);
  }
  return gj.features;
}

function slimFeature(feature) {
  if (!["Polygon", "MultiPolygon"].includes(feature?.geometry?.type)) return null;
  const derived = deriveBuildingHeight(feature.properties ?? {});
  return {
    type: "Feature",
    ...(feature.id !== undefined ? { id: feature.id } : {}),
    geometry: feature.geometry,
    properties: {
      height_m: derived.height_m,
      height_source: derived.source,
      top_elev_m: derived.top_elev_m,
      ground_elev_m: derived.ground_elev_m,
      floors: feature.properties?.["1_floor"] ?? null,
    },
  };
}

await mkdir(OUT_DIR, { recursive: true });
const fetchedAt = new Date().toISOString();
let lastError = null;

for (const endpoint of ENDPOINTS) {
  try {
    const expected = await getHits(endpoint);
    const byId = new Map();
    let startIndex = 0;
    let page = 0;
    while (true) {
      page += 1;
      const feats = await getPage(endpoint, startIndex);
      if (!feats.length) break;
      for (const f of feats) byId.set(String(f.id ?? `${startIndex}:${byId.size}`), f);
      startIndex += feats.length;
      if (Number.isFinite(expected) && byId.size >= expected) break;
      if (feats.length < PAGE_SIZE) break;
      if (page > 50) throw new Error("page guard tripped");
    }

    const slim = [];
    let dropped = 0;
    const sourceCounts = {};
    for (const f of byId.values()) {
      const s = slimFeature(f);
      if (!s) {
        dropped += 1;
        continue;
      }
      slim.push(s);
      sourceCounts[s.properties.height_source] = (sourceCounts[s.properties.height_source] ?? 0) + 1;
    }

    const fc = { type: "FeatureCollection", name: "xinyi_epsg3826", features: slim };
    const body = JSON.stringify(fc);
    const sha256 = createHash("sha256").update(body).digest("hex");
    await writeFile(OUT_GEOJSON, body);
    const manifest = {
      tool: "tools/citygen_v2/fetch_projected_sample.mjs",
      type_name: TYPE_NAME,
      endpoint_used: endpoint,
      endpoints_tried: ENDPOINTS,
      bbox: BBOX,
      bbox_crs: INPUT_BBOX_CRS,
      response_crs: OUTPUT_CRS,
      fetched_at: fetchedAt,
      expected_hits: expected,
      feature_count: slim.length,
      dropped_non_polygon: dropped,
      height_source_counts: sourceCounts,
      sha256,
      reason: "avoid EPSG:4326 four-decimal footprint collapse observed in v0 snapshot",
    };
    await writeFile(OUT_MANIFEST, JSON.stringify(manifest, null, 2));
    console.log(JSON.stringify({
      output: OUT_GEOJSON,
      manifest: OUT_MANIFEST,
      feature_count: slim.length,
      response_crs: OUTPUT_CRS,
      sha256,
    }, null, 2));
    process.exit(0);
  } catch (e) {
    lastError = e;
    console.error(`FAILED ${endpoint}: ${e.message}`);
  }
}

console.error(`All endpoints failed. Last error: ${lastError?.message}`);
process.exit(2);
