// Fetch the same Taipei WFS building layer (tp_building_height, EPSG:3826)
// over the wider Taipei-basin bbox for FAR-LOD massing only. Streams a slim
// ndjson.gz (id, height, ground, outer ring rounded to 0.1 m). The raw file is
// an intermediate: only the generalized product is committed.
// Usage: node tools/lookdev/fetch_far_city.mjs [out.ndjson.gz]
import { createGzip } from "node:zlib";
import { createWriteStream } from "node:fs";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { deriveBuildingHeight } from "../taipei/vendor/buju/taipei_building_height_semantics.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..");
const OUT = process.argv[2] || path.join(REPO, "data", "generated", "taipei", "far_city_raw.ndjson.gz");
const ENDPOINTS = [
  "https://citydashboard.taipei/geo_server/taipei_vioc/ows",
  "https://citydashboard.taipei/geo_server/ows",
];
const TYPE_NAME = "taipei_vioc:tp_building_height";
const BBOX = "121.455,24.975,121.645,25.125";   // Taipei basin within Taipei City
const PAGE = 5000;

async function text(url) {
  for (let i = 0; i < 5; i++) {
    try {
      const r = await fetch(url, { headers: { "User-Agent": "air-combat-world/xinyi-lookdev-far-city" } });
      const t = await r.text();
      if (!r.ok) throw new Error(`HTTP ${r.status}: ${t.slice(0, 200)}`);
      return t;
    } catch (e) {
      if (i === 4) throw e;
      await new Promise((res) => setTimeout(res, 2000 * 2 ** i));
    }
  }
}
const url = (base, p) => { const u = new URL(base); for (const [k, v] of Object.entries(p)) u.searchParams.set(k, String(v)); return u; };

await mkdir(path.dirname(OUT), { recursive: true });
let last;
for (const ep of ENDPOINTS) {
  try {
    const hitsXml = await text(url(ep, { service: "WFS", version: "2.0.0", request: "GetFeature", typeNames: TYPE_NAME,
      resultType: "hits", srsName: "EPSG:3826", bbox: `${BBOX},EPSG:4326` }));
    const expected = Number((/(?:numberMatched|numberOfFeatures)=["'](\d+)["']/.exec(hitsXml) || [])[1]);
    const gz = createGzip({ level: 6 });
    const done = new Promise((res) => gz.pipe(createWriteStream(OUT)).on("finish", res));
    const seen = new Set();
    let start = 0, pages = 0;
    while (true) {
      const gj = JSON.parse(await text(url(ep, { service: "WFS", version: "2.0.0", request: "GetFeature", typeNames: TYPE_NAME,
        outputFormat: "application/json", srsName: "EPSG:3826", bbox: `${BBOX},EPSG:4326`, startIndex: start, count: PAGE,
        sortBy: "gid" })));
      const feats = gj.features || [];
      pages += 1;
      for (const f of feats) {
        const id = String(f.id);
        if (seen.has(id) || !f.geometry) continue;
        seen.add(id);
        const d = deriveBuildingHeight(f.properties || {});
        const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
        const rings = polys.map((p) => p[0].map(([x, y]) => [Math.round(x * 10) / 10, Math.round(y * 10) / 10]));
        gz.write(JSON.stringify({ id, h: d.height_m, g: d.ground_elev_m, r: rings }) + "\n");
      }
      start += feats.length;
      if (!feats.length || feats.length < PAGE || (expected && seen.size >= expected)) break;
      if (pages > 400) throw new Error("page guard");
      if (pages % 10 === 0) console.log(`pages ${pages} features ${seen.size}/${expected}`);
    }
    gz.end();
    await done;
    console.log(JSON.stringify({ out: OUT, expected, features: seen.size, pages }));
    process.exit(0);
  } catch (e) { last = e; console.error(`FAILED ${ep}: ${e.message}`); }
}
console.error(`all endpoints failed: ${last?.message}`);
process.exit(2);
