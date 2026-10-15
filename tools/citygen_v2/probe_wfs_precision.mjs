// Probe whether Taipei WFS geometry precision improves when GeoServer
// reprojects the same bbox to projected TWD97/TM2 (EPSG:3826).
//
// This is diagnostic only. It never overwrites the pinned source snapshot.
// Usage: node tools/citygen_v2/probe_wfs_precision.mjs
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..");
const OUT = path.join(REPO, "data", "generated", "taipei", "xinyi_v2_wfs_precision_probe.report.json");

const ENDPOINTS = [
  "https://citydashboard.taipei/geo_server/taipei_vioc/ows",
  "https://citydashboard.taipei/geo_server/ows",
];
const TYPE_NAME = "taipei_vioc:tp_building_height";
const BBOX = "121.5546,25.0247,121.5744,25.0427";
const PAGE_SIZE = 5000;

function makeUrl(base, params) {
  const u = new URL(base);
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, String(v));
  return u;
}

async function fetchText(url) {
  const res = await fetch(url, {
    headers: {
      Accept: "application/json, application/geo+json, application/xml, text/xml, */*",
      "User-Agent": "air-combat-world/xinyi-v2-precision-probe",
    },
    redirect: "follow",
  });
  const body = await res.text();
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${body.slice(0, 240)}`);
  return body;
}

function parseHitCount(xml) {
  const m = xml.match(/(?:numberMatched|numberOfFeatures)=["'](\d+)["']/i);
  return m ? Number(m[1]) : null;
}

async function hitCount(base) {
  const xml = await fetchText(makeUrl(base, {
    service: "WFS", version: "2.0.0", request: "GetFeature",
    typeNames: TYPE_NAME, resultType: "hits",
    srsName: "EPSG:4326", bbox: `${BBOX},EPSG:4326`,
  }));
  return parseHitCount(xml);
}

async function fetchAll(base, outputSrs, expected) {
  const byId = new Map();
  let startIndex = 0;
  for (let page = 0; page < 20; page += 1) {
    const text = await fetchText(makeUrl(base, {
      service: "WFS", version: "2.0.0", request: "GetFeature",
      typeNames: TYPE_NAME, outputFormat: "application/json",
      srsName: outputSrs, bbox: `${BBOX},EPSG:4326`,
      startIndex, count: PAGE_SIZE,
    }));
    const gj = JSON.parse(text);
    if (gj?.type !== "FeatureCollection" || !Array.isArray(gj.features)) {
      throw new Error(`unexpected GeoJSON response for ${outputSrs}`);
    }
    if (!gj.features.length) break;
    for (const f of gj.features) byId.set(String(f.id), f);
    startIndex += gj.features.length;
    if (Number.isFinite(expected) && byId.size >= expected) break;
    if (gj.features.length < PAGE_SIZE) break;
  }
  return [...byId.values()];
}

function polygons(geometry) {
  if (geometry?.type === "Polygon") return [geometry.coordinates];
  if (geometry?.type === "MultiPolygon") return geometry.coordinates;
  return [];
}

function decimalDigits(v) {
  const s = String(v).toLowerCase();
  if (s.includes("e")) {
    const [m, eText] = s.split("e");
    const e = Number(eText);
    const frac = (m.split(".")[1] || "").length;
    return Math.max(0, frac - e);
  }
  const dot = s.indexOf(".");
  return dot < 0 ? 0 : s.length - dot - 1;
}

function summarize(features) {
  const decimals = new Map();
  const byId = new Map();
  let parts = 0;
  let collapsed = 0;
  let holes = 0;
  let multipart = 0;

  for (const f of features) {
    const ps = polygons(f.geometry);
    if (ps.length > 1) multipart += 1;
    let featureCollapsed = 0;
    for (const p of ps) {
      parts += 1;
      if (p.length > 1) holes += 1;
      const outer = p[0] || [];
      const unique = new Set(outer.map(xy => `${xy[0]}|${xy[1]}`)).size;
      if (unique < 3) {
        collapsed += 1;
        featureCollapsed += 1;
      }
      for (const ring of p) {
        for (const xy of ring) {
          for (const value of xy) {
            const d = decimalDigits(value);
            decimals.set(d, (decimals.get(d) || 0) + 1);
          }
        }
      }
    }
    byId.set(String(f.id), featureCollapsed);
  }

  return {
    feature_count: features.length,
    polygon_parts: parts,
    multipart_features: multipart,
    parts_with_holes: holes,
    collapsed_exterior_parts: collapsed,
    max_decimals: Math.max(...decimals.keys(), 0),
    decimal_histogram: Object.fromEntries([...decimals.entries()].sort((a, b) => a[0] - b[0])),
    collapsed_by_id: byId,
  };
}

let endpointUsed = null;
let expected = null;
let summaries = {};
let comparison = null;
let errors = [];

for (const endpoint of ENDPOINTS) {
  try {
    expected = await hitCount(endpoint);
    const f4326 = await fetchAll(endpoint, "EPSG:4326", expected);
    const f3826 = await fetchAll(endpoint, "EPSG:3826", expected);
    const s4326 = summarize(f4326);
    const s3826 = summarize(f3826);

    let collapsed4326Recovered3826 = 0;
    let commonIds = 0;
    for (const [id, n4326] of s4326.collapsed_by_id.entries()) {
      if (!s3826.collapsed_by_id.has(id)) continue;
      commonIds += 1;
      if (n4326 > 0 && s3826.collapsed_by_id.get(id) === 0) {
        collapsed4326Recovered3826 += 1;
      }
    }

    summaries = {
      "EPSG:4326": { ...s4326, collapsed_by_id: undefined },
      "EPSG:3826": { ...s3826, collapsed_by_id: undefined },
    };
    comparison = {
      common_ids: commonIds,
      collapsed_4326_features_recovered_in_3826: collapsed4326Recovered3826,
      interpretation: collapsed4326Recovered3826 > 0
        ? "Projected WFS output preserves footprint detail lost in EPSG:4326; investigate repinning Taipei geometry in EPSG:3826."
        : "Projected output did not recover collapsed footprints in this probe; seek another authoritative footprint source or format.",
    };
    endpointUsed = endpoint;
    break;
  } catch (e) {
    errors.push({ endpoint, error: String(e?.message || e) });
  }
}

const report = {
  probe: "Taipei WFS coordinate precision: EPSG:4326 vs EPSG:3826",
  bbox: BBOX,
  bbox_crs: "EPSG:4326",
  expected_hits: expected,
  endpoint_used: endpointUsed,
  summaries,
  comparison,
  errors,
};

await mkdir(path.dirname(OUT), { recursive: true });
await writeFile(OUT, JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
if (!endpointUsed) process.exit(2);
