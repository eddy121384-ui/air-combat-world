// Audit the official 2025 MOI 20 m DTM catalog against the locked Xinyi bbox.
// This stage discovers the real downloadable terrain resources before any terrain
// geometry is generated. It is intentionally read-only and fail-closed.
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..");
const OUT_DIR = path.join(REPO, "data", "generated", "taipei", "terrain");
const REPORT = path.join(OUT_DIR, "nlsc_dtm_2025_source_audit.json");
const CATALOG_COPY = path.join(OUT_DIR, "nlsc_dtm_2025_catalog.csv");

const DATASET_PAGE = "https://data.gov.tw/dataset/176927";
const CATALOG_URL =
  "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/" +
  "A964612F-0D64-4C81-BFE5-6C1F2BA61DED/resource/" +
  "A0B94F67-8ADF-48A1-8DF0-C60719AD2B28/download";

const PROJECTED_BUILDINGS =
  path.join(REPO, "data", "generated", "taipei", "sample_buildings_epsg3826.geojson");

function parseCsv(text) {
  const rows = [];
  let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        field += '"'; i++;
      } else if (ch === '"') {
        quoted = false;
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      row.push(field); field = "";
    } else if (ch === "\n") {
      row.push(field); field = "";
      if (row.some(v => v.trim() !== "")) rows.push(row);
      row = [];
    } else if (ch !== "\r") {
      field += ch;
    }
  }
  if (field.length || row.length) {
    row.push(field);
    if (row.some(v => v.trim() !== "")) rows.push(row);
  }
  return rows;
}

function coordWalk(coords, bbox) {
  if (!Array.isArray(coords)) return;
  if (coords.length >= 2 && typeof coords[0] === "number" && typeof coords[1] === "number") {
    const [x, y] = coords;
    if (Number.isFinite(x) && Number.isFinite(y)) {
      bbox.min_x = Math.min(bbox.min_x, x);
      bbox.min_y = Math.min(bbox.min_y, y);
      bbox.max_x = Math.max(bbox.max_x, x);
      bbox.max_y = Math.max(bbox.max_y, y);
    }
    return;
  }
  for (const part of coords) coordWalk(part, bbox);
}

function buildingBbox(fc) {
  const bbox = { min_x: Infinity, min_y: Infinity, max_x: -Infinity, max_y: -Infinity };
  for (const f of fc.features ?? []) coordWalk(f?.geometry?.coordinates, bbox);
  if (!Object.values(bbox).every(Number.isFinite)) throw new Error("projected building bbox is empty");
  return bbox;
}

function normalizeHeader(s) {
  return String(s ?? "").replace(/^\uFEFF/, "").trim();
}

function rowObject(headers, cells) {
  const o = {};
  headers.forEach((h, i) => { o[h || `col_${i}`] = cells[i] ?? ""; });
  return o;
}

function looksTerrainRelevant(obj) {
  const text = Object.values(obj).join(" ");
  return /臺北|台北|Taipei|3826|TWD97|DTM|DEM|20公尺/i.test(text);
}

function urlsIn(obj) {
  const urls = [];
  for (const value of Object.values(obj)) {
    const matches = String(value).match(/https?:\/\/[^\s,;"']+/g) ?? [];
    urls.push(...matches);
  }
  return [...new Set(urls)];
}

async function fetchText(url) {
  const res = await fetch(url, {
    redirect: "follow",
    headers: {
      "User-Agent": "air-combat-world/xinyi-terrain-source-audit",
      "Accept": "text/csv,text/plain,*/*",
    },
  });
  const body = await res.text();
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${body.slice(0, 300)}`);
  return { body, finalUrl: res.url, contentType: res.headers.get("content-type") };
}

await mkdir(OUT_DIR, { recursive: true });

const projectedText = await (await import("node:fs/promises")).readFile(PROJECTED_BUILDINGS, "utf8");
const projected = JSON.parse(projectedText);
const xinyiBbox = buildingBbox(projected);

const fetchedAt = new Date().toISOString();
const { body: csv, finalUrl, contentType } = await fetchText(CATALOG_URL);
const catalogSha256 = createHash("sha256").update(csv).digest("hex");
await writeFile(CATALOG_COPY, csv, "utf8");

const parsed = parseCsv(csv);
if (parsed.length < 2) throw new Error(`DTM catalog unexpectedly has only ${parsed.length} rows`);
const headers = parsed[0].map(normalizeHeader);
const objects = parsed.slice(1).map(r => rowObject(headers, r));
const relevant = objects.filter(looksTerrainRelevant);

const uniqueUrls = [...new Set(objects.flatMap(urlsIn))];
const relevantUrls = [...new Set(relevant.flatMap(urlsIn))];

const report = {
  gate: "Xinyi terrain source discovery / audit",
  status: "CATALOG_DISCOVERED_NOT_YET_TERRAIN_LOCKED",
  fetched_at: fetchedAt,
  xinyi_building_source: {
    path: path.relative(REPO, PROJECTED_BUILDINGS),
    crs: "EPSG:3826",
    feature_count: projected.features?.length ?? null,
    bbox_epsg3826: xinyiBbox,
  },
  official_dataset: {
    title: "2025年版全臺灣20公尺網格數值地形模型DTM資料",
    provider: "內政部地政司 / 政府資料開放平臺",
    dataset_page: DATASET_PAGE,
    dataset_id: "176927",
    semantics: "20 m grid DTM; catalog says each grid point records planar coordinates and elevation",
    license: "政府資料開放授權條款-第1版",
    catalog_url: CATALOG_URL,
    catalog_final_url: finalUrl,
    catalog_content_type: contentType,
    catalog_sha256: catalogSha256,
    catalog_row_count: objects.length,
    catalog_headers: headers,
  },
  discovery: {
    relevant_row_count: relevant.length,
    relevant_rows_preview: relevant.slice(0, 30),
    all_discovered_urls: uniqueUrls,
    relevant_discovered_urls: relevantUrls,
  },
  next_gate: (
    "Identify the actual downloadable DTM resource(s) covering the Xinyi EPSG:3826 bbox, " +
    "lock CRS/vertical datum/file hash, then generate terrain tiles."
  ),
};

await writeFile(REPORT, JSON.stringify(report, null, 2) + "\n", "utf8");
console.log(JSON.stringify({
  report: path.relative(REPO, REPORT),
  catalog: path.relative(REPO, CATALOG_COPY),
  catalog_sha256: catalogSha256,
  headers,
  row_count: objects.length,
  relevant_row_count: relevant.length,
  xinyi_bbox_epsg3826: xinyiBbox,
  relevant_rows_preview: relevant.slice(0, 10),
  relevant_urls: relevantUrls.slice(0, 30),
}, null, 2));
