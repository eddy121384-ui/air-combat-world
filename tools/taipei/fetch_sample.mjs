// Phase 1 — Taipei WFS sample ingest (2 km Xinyi / Taipei 101 tile).
// Reuses Buju-verified: endpoints, paging, bbox convention, height semantics,
// plausibility rules, fallback chain. Adds: height_source + provenance retention.
// Stdlib-only Node (no npm). Rerunnable: same bbox + same server state => same logical output.
//
// Usage: node tools/taipei/fetch_sample.mjs [--bbox minLon,minLat,maxLon,maxLat]
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { deriveBuildingHeight } from "./vendor/buju/taipei_building_height_semantics.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..");
const OUT_DIR = path.join(REPO, "data", "generated", "taipei");
const OUT_GEOJSON = path.join(OUT_DIR, "sample_buildings.geojson");
const OUT_MANIFEST = path.join(OUT_DIR, "sample_buildings.manifest.json");

const ENDPOINTS = [
  "https://citydashboard.taipei/geo_server/taipei_vioc/ows",
  "https://citydashboard.taipei/geo_server/ows",
];
const TYPE_NAME = "taipei_vioc:tp_building_height";
const PAGE_SIZE = 5000;

// Default: 2 km x 2 km tile centred on Taipei 101 (121.5645, 25.0337).
// 2 km E-W @lat25 ≈ 0.0198 deg lon; 2 km N-S ≈ 0.0180 deg lat.
const DEFAULT_BBOX = "121.5546,25.0247,121.5744,25.0427";

function parseArgs() {
  const out = { bbox: DEFAULT_BBOX };
  for (const a of process.argv.slice(2)) {
    if (a.startsWith("--bbox=")) out.bbox = a.slice("--bbox=".length);
  }
  return out;
}

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
      "User-Agent": "air-combat-world/0.1 greybox-core",
    },
    redirect: "follow",
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}; ${text.slice(0, 300).replace(/\s+/g, " ")}`);
  return text;
}

function parseHitCount(xml) {
  const m = xml.match(/(?:numberMatched|numberOfFeatures)=["'](\d+)["']/i);
  return m ? Number(m[1]) : null;
}

async function getHits(base, bbox) {
  const xml = await fetchText(makeUrl(base, {
    service: "WFS", version: "2.0.0", request: "GetFeature",
    typeNames: TYPE_NAME, resultType: "hits",
    srsName: "EPSG:4326", bbox: `${bbox},EPSG:4326`,
  }));
  return parseHitCount(xml);
}

async function getPage(base, bbox, startIndex) {
  const text = await fetchText(makeUrl(base, {
    service: "WFS", version: "2.0.0", request: "GetFeature",
    typeNames: TYPE_NAME, outputFormat: "application/json",
    srsName: "EPSG:4326", bbox: `${bbox},EPSG:4326`,
    startIndex, count: PAGE_SIZE,
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

const { bbox } = parseArgs();
await mkdir(OUT_DIR, { recursive: true });
const fetchedAt = new Date().toISOString();
let lastError = null;

for (const endpoint of ENDPOINTS) {
  try {
    console.log(`Endpoint: ${endpoint}`);
    const expected = await getHits(endpoint, bbox);
    console.log(`Expected features in sample bbox: ${expected?.toLocaleString() ?? "unknown"}`);

    const byId = new Map();
    let startIndex = 0, page = 0;
    while (true) {
      page += 1;
      const feats = await getPage(endpoint, bbox, startIndex);
      if (!feats.length) break;
      for (const f of feats) byId.set(String(f.id ?? `${startIndex}:${byId.size}`), f);
      startIndex += feats.length;
      console.log(`Page ${page}: +${feats.length} -> ${byId.size} unique`);
      if (Number.isFinite(expected) && byId.size >= expected) break;
      if (page > 50) throw new Error("page guard tripped (>50 pages for a 2 km tile)");
    }

    const slim = [];
    let dropped = 0;
    const sourceCounts = {};
    for (const f of byId.values()) {
      const s = slimFeature(f);
      if (!s) { dropped += 1; continue; }
      slim.push(s);
      sourceCounts[s.properties.height_source] = (sourceCounts[s.properties.height_source] ?? 0) + 1;
    }
    console.log(`Slim: ${slim.length} kept, ${dropped} non-polygon dropped`);
    console.log(`Height sources: ${JSON.stringify(sourceCounts)}`);

    const fc = { type: "FeatureCollection", features: slim };
    const body = JSON.stringify(fc);
    const sha256 = createHash("sha256").update(body).digest("hex");
    await writeFile(OUT_GEOJSON, body);
    const manifest = {
      tool: "tools/taipei/fetch_sample.mjs",
      type_name: TYPE_NAME,
      endpoint_used: endpoint,
      endpoints_tried: ENDPOINTS,
      srs: "EPSG:4326",
      bbox,
      fetched_at: fetchedAt,
      expected_hits: expected,
      feature_count: slim.length,
      dropped_non_polygon: dropped,
      height_source_counts: sourceCounts,
      sha256,
      semantics: "vendored tools/taipei/vendor/buju/taipei_building_height_semantics.mjs (Buju probe 2026-08-20)",
    };
    await writeFile(OUT_MANIFEST, JSON.stringify(manifest, null, 2));
    console.log(`WROTE ${OUT_GEOJSON} (${(body.length / 1024 / 1024).toFixed(2)} MB, sha256 ${sha256.slice(0, 16)}…)`);
    console.log(`WROTE ${OUT_MANIFEST}`);
    process.exit(0);
  } catch (e) {
    lastError = e;
    console.error(`FAILED ${endpoint}: ${e.message}`);
  }
}
console.error(`All endpoints failed. Last error: ${lastError?.message}`);
process.exit(1);
