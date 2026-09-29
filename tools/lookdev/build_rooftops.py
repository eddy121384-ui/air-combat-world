"""Generate Taipei rooftop clutter as instanced props on the real roof polygons.

The WFS gives every building a flat roof. From an aircraft the Taipei roofscape
is anything but: 頂樓加蓋 sheet-metal sheds, stainless water tanks on stands,
solar water heaters, TV antennas, AC condensers, and on towers machine rooms,
cooling towers, window-cleaning cranes and red aviation obstruction lights.

Placement is deterministic per building (seeded by building id), constrained to
the accepted footprint polygon (inset) at the building's surveyed top elevation,
oriented to the footprint's minimum rotated rectangle. Buildings are not edited.

Outputs (unreal/Saved/XinyiLook/rooftops/):
  props_<type>.glb          one small mesh per prop type (TEXCOORD_2 packed data:
                            R = prop type id, G = part id)
  rooftop_instances.json    {type: [{e,n,z,yaw,sx,sy,sz,v}]}
  rooftops.report.json
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from shapely import affinity
from shapely.geometry import Point, Polygon, box
from shapely.prepared import prep

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools/compiler"))
sys.path.insert(0, str(HERE))
from gltf_writer import pack_rgba8, ue_local_bounds_cm, write_glb  # noqa: E402
from worldmodel import build_worldmodel  # noqa: E402

SOURCE = REPO / "data/generated/taipei/sample_buildings_epsg3826.geojson"
CITY = REPO / "cities/taipei/city.yaml"
LOOK = REPO / "unreal/Saved/XinyiLook"
OUT = LOOK / "rooftops"

TYPES = ["shed", "tank", "solar", "antenna", "ac", "cooling", "machine", "bmu", "avlight"]
TYPE_ID = {t: i + 1 for i, t in enumerate(TYPES)}
ARCH_LOW, ARCH_WALKUP, ARCH_HUAXIA, ARCH_RESTOWER, ARCH_OFFICE, ARCH_PODIUM = range(6)
FLAG_ROOFTOP = 8


# ------------------------------------------------------------------ meshes ---
class MB:
    def __init__(self, tid):
        self.tid = tid
        self.v, self.f, self.c = [], [], []

    def box(self, cx, cy, z0, sx, sy, sz, part=0):
        x0, x1, y0, y1, z1 = cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2, z0 + sz
        faces = [
            [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],  # top
            [(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)],  # bottom
            [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
            [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],
            [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)],
            [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)],
        ]
        for q in faces:
            self.quad(q, part)

    def quad(self, q, part):
        b = len(self.v)
        self.v += q
        self.c += [(self.tid, part, 0, 255)] * 4
        self.f += [(b, b + 1, b + 2), (b, b + 2, b + 3)]

    def cyl(self, cx, cy, z0, r, h, n=10, part=0, cap=True):
        a = [2 * math.pi * i / n for i in range(n)]
        for i in range(n):
            j = (i + 1) % n
            p0 = (cx + r * math.cos(a[i]), cy + r * math.sin(a[i]))
            p1 = (cx + r * math.cos(a[j]), cy + r * math.sin(a[j]))
            self.quad([(p0[0], p0[1], z0), (p1[0], p1[1], z0), (p1[0], p1[1], z0 + h), (p0[0], p0[1], z0 + h)], part)
            if cap:
                b = len(self.v)
                self.v += [(cx, cy, z0 + h), (p0[0], p0[1], z0 + h), (p1[0], p1[1], z0 + h)]
                self.c += [(self.tid, part, 0, 255)] * 3
                self.f += [(b, b + 1, b + 2)]

    def write(self, path):
        v = np.asarray(self.v, dtype=np.float64)
        f = np.asarray(self.f, dtype=np.int64)
        game = np.column_stack([v[:, 0], v[:, 2], -v[:, 1]]).astype(np.float32)
        fn = np.cross(game[f[:, 1]] - game[f[:, 0]], game[f[:, 2]] - game[f[:, 0]])
        fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-9)
        nrm = np.zeros_like(game)
        for k in range(3):
            nrm[f[:, k]] = fn
        write_glb(path, [{"name": "XinyiRoofProp", "positions": game, "normals": nrm,
                          "uv2": pack_rgba8(np.asarray(self.c, np.uint8)), "indices": f.astype(np.uint32),
                          "base_color": [0.6, 0.6, 0.6, 1.0]}], mesh_name="SM_XinyiRoof_" + TYPES[self.tid - 1])
        return ue_local_bounds_cm(game), len(f)


def build_meshes():
    OUT.mkdir(parents=True, exist_ok=True)
    meshes = {}
    # unit shed: 1 x 1 footprint, 1 m tall walls + shallow gable ridge; scaled per instance
    m = MB(TYPE_ID["shed"])
    m.box(0, 0, 0, 1.0, 1.0, 1.0, part=0)
    m.quad([(-0.52, -0.52, 1.0), (0.52, -0.52, 1.0), (0.52, 0.0, 1.12), (-0.52, 0.0, 1.12)], 1)
    m.quad([(0.52, 0.52, 1.0), (-0.52, 0.52, 1.0), (-0.52, 0.0, 1.12), (0.52, 0.0, 1.12)], 1)
    meshes["shed"] = m
    # stainless water tank on a steel stand
    m = MB(TYPE_ID["tank"])
    for dx, dy in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)):
        m.box(dx, dy, 0, 0.08, 0.08, 1.2, part=1)
    m.box(0, 0, 1.15, 1.2, 1.2, 0.08, part=1)
    m.cyl(0, 0, 1.23, 0.62, 1.5, n=10, part=0)
    meshes["tank"] = m
    # solar water heater: tilted collector + horizontal tank
    m = MB(TYPE_ID["solar"])
    m.quad([(-1.0, -0.9, 0.3), (1.0, -0.9, 0.3), (1.0, 0.6, 1.3), (-1.0, 0.6, 1.3)], 0)
    m.quad([(1.0, -0.9, 0.25), (-1.0, -0.9, 0.25), (-1.0, 0.6, 1.25), (1.0, 0.6, 1.25)], 1)
    m.box(0, 0.75, 1.1, 2.1, 0.45, 0.45, part=1)
    m.box(0, -0.9, 0, 2.0, 0.06, 0.3, part=1)
    meshes["solar"] = m
    # TV antenna: mast + two crossbars
    m = MB(TYPE_ID["antenna"])
    m.box(0, 0, 0, 0.06, 0.06, 4.0, part=0)
    m.box(0, 0, 3.2, 1.6, 0.04, 0.04, part=0)
    m.box(0, 0, 3.7, 1.1, 0.04, 0.04, part=0)
    meshes["antenna"] = m
    # AC condenser
    m = MB(TYPE_ID["ac"])
    m.box(0, 0, 0, 0.9, 0.35, 0.7, part=0)
    m.quad([(-0.3, -0.176, 0.12), (0.3, -0.176, 0.12), (0.3, -0.176, 0.6), (-0.3, -0.176, 0.6)], 1)
    meshes["ac"] = m
    # cooling tower (towers / podiums)
    m = MB(TYPE_ID["cooling"])
    m.cyl(0, 0, 0, 1.6, 2.8, n=12, part=0)
    m.cyl(0, 0, 2.8, 1.2, 0.5, n=12, part=1)
    meshes["cooling"] = m
    # machine room / stair core (unit box)
    m = MB(TYPE_ID["machine"])
    m.box(0, 0, 0, 1.0, 1.0, 1.0, part=0)
    m.box(0, 0, 1.0, 1.04, 1.04, 0.04, part=1)
    meshes["machine"] = m
    # window-cleaning crane (BMU) on office towers
    m = MB(TYPE_ID["bmu"])
    m.box(0, 0, 0, 1.2, 1.2, 2.2, part=0)
    m.box(3.0, 0, 2.0, 7.0, 0.35, 0.45, part=0)
    m.box(6.3, 0, 1.4, 0.2, 0.2, 0.6, part=1)
    meshes["bmu"] = m
    # aviation obstruction light (emissive red)
    m = MB(TYPE_ID["avlight"])
    m.box(0, 0, 0, 0.1, 0.1, 1.2, part=1)
    m.box(0, 0, 1.2, 0.35, 0.35, 0.35, part=0)
    meshes["avlight"] = m
    info = {}
    for t, mb in meshes.items():
        bounds, tris = mb.write(OUT / f"props_{t}.glb")
        info[t] = {"mesh": f"props_{t}.glb", "triangles": tris, "expected_ue_local_bounds": bounds}
    return info


# --------------------------------------------------------------- placement ---
def rng_for(bid):
    return np.random.default_rng(int.from_bytes(hashlib.sha256(bid.encode()).digest()[:8], "little"))


def main():
    info = build_meshes()
    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    props = {f["id"]: f["properties"] for f in src["features"]}
    look = {}
    with gzip.open(LOOK / "look_buildings.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            look[r["building_id"]] = r
    wm = build_worldmodel(SOURCE, CITY, source_crs="EPSG:3826")
    inst = {t: [] for t in TYPES}

    def add(t, x, y, z, yaw, sx=1.0, sy=1.0, sz=1.0, v=0):
        inst[t].append({"e": round(x, 3), "n": round(y, 3), "z": round(z, 3), "yaw": round(yaw, 2),
                        "sx": round(sx, 3), "sy": round(sy, 3), "sz": round(sz, 3), "v": int(v)})

    for b in wm["buildings"]:
        if b["suppressed"] or b["id"] not in look:
            continue
        rec = look[b["id"]]
        arch = rec["archetype"]
        if rec["flags"] & FLAG_ROOFTOP:
            continue
        p = props[b["id"]]
        top = float(p["ground_elev_m"]) + float(b["height_m"])
        H = float(b["height_m"])
        rng = rng_for(b["id"])
        for part in b["polygons"]:
            poly = Polygon(part["footprint_enu"], part.get("holes_enu") or [])
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty or poly.geom_type != "Polygon" or poly.area < 12.0:
                continue
            inner = poly.buffer(-0.8)
            if inner.is_empty or inner.area < 4.0:
                continue
            ip = prep(inner)
            mrr = poly.minimum_rotated_rectangle
            c = np.asarray(mrr.exterior.coords)[:4]
            e1 = c[1] - c[0]
            ang = math.degrees(math.atan2(e1[1], e1[0]))
            cx, cy = inner.representative_point().coords[0]
            placed = []

            def free(x, y, r):
                return all((x - px) ** 2 + (y - py) ** 2 > (r + pr) ** 2 for px, py, pr in placed)

            def scatter(t, n, r, **kw):
                minx, miny, maxx, maxy = inner.bounds
                tries = 0
                k = 0
                while k < n and tries < n * 12:
                    tries += 1
                    x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
                    if ip.contains(Point(x, y)) and free(x, y, r):
                        placed.append((x, y, r))
                        add(t, x, y, top, ang + (90 if rng.random() < 0.5 else 0), v=rng.integers(0, 4), **kw)
                        k += 1

            area = inner.area
            if arch in (ARCH_LOW, ARCH_WALKUP, ARCH_HUAXIA):
                # 頂樓加蓋: a sheet-metal shed covering a large share of the roof
                shed_p = {ARCH_LOW: 0.25, ARCH_WALKUP: 0.62, ARCH_HUAXIA: 0.35}[arch]
                if area > 25 and rng.random() < shed_p:
                    frac = rng.uniform(0.35, 0.7)
                    w = math.dist(c[0], c[1]); d = math.dist(c[1], c[2])
                    sx, sy = max(2.0, (w - 1.6) * math.sqrt(frac)), max(2.0, (d - 1.6) * math.sqrt(frac))
                    shed = affinity.rotate(box(cx - sx / 2, cy - sy / 2, cx + sx / 2, cy + sy / 2), ang, origin=(cx, cy))
                    for _ in range(4):
                        if inner.contains(shed):
                            break
                        sx *= 0.8; sy *= 0.8
                        shed = affinity.rotate(box(cx - sx / 2, cy - sy / 2, cx + sx / 2, cy + sy / 2), ang, origin=(cx, cy))
                    if inner.contains(shed):
                        add("shed", cx, cy, top, ang, sx, sy, rng.uniform(2.4, 3.0), v=rng.integers(0, 4))
                        placed.append((cx, cy, 0.45 * max(sx, sy)))
                scatter("tank", 1 + int(area > 180) + int(rng.random() < 0.3), 0.8)
                if rng.random() < 0.35:
                    scatter("solar", 1, 1.2)
                if rng.random() < 0.5:
                    scatter("antenna", 1, 0.5, sz=rng.uniform(0.7, 1.2))
                scatter("ac", int(rng.integers(0, 4)) + int(area / 120), 0.5)
            elif arch in (ARCH_RESTOWER, ARCH_OFFICE):
                mw = min(12.0, math.sqrt(area) * 0.45)
                add("machine", cx, cy, top, ang, mw, mw * rng.uniform(0.6, 1.0), rng.uniform(3.0, 5.0), v=rng.integers(0, 4))
                placed.append((cx, cy, mw * 0.6))
                scatter("cooling", 1 + int(area > 600), 1.8)
                if arch == ARCH_OFFICE and area > 300 and rng.random() < 0.6:
                    scatter("bmu", 1, 2.0)
                scatter("antenna", int(rng.integers(0, 3)), 0.5, sz=rng.uniform(1.5, 3.0))
                scatter("ac", int(area / 150), 0.5)
            else:  # podium / department store: chillers + cooling towers
                scatter("cooling", 1 + int(area / 900), 1.8)
                scatter("machine", 1 + int(area / 1500), 3.0, sx=rng.uniform(4, 8), sy=rng.uniform(3, 6), sz=3.0)
                scatter("ac", int(area / 80), 0.5)
            # red aviation obstruction lights on tall buildings (corners of the roof)
            if H >= 60.0 and part is b["polygons"][0]:
                for q in np.asarray(inner.minimum_rotated_rectangle.exterior.coords)[:4]:
                    if ip.contains(Point(q[0] * 0.995 + cx * 0.005, q[1] * 0.995 + cy * 0.005)):
                        add("avlight", float(q[0]), float(q[1]), top, 0.0, v=0)

    total = sum(len(v) for v in inst.values())
    (OUT / "rooftop_instances.json").write_text(json.dumps({"count": total, "types": inst}) + "\n")
    report = {"types": {t: {**info[t], "instances": len(inst[t])} for t in TYPES}, "instances_total": total}
    (OUT / "rooftops.report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({t: len(inst[t]) for t in TYPES}), "total", total)


if __name__ == "__main__":
    main()
