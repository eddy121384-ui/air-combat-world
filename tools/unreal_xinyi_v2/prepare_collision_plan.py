"""Build deterministic, source-certified Xinyi collision probes without touching assets.

The accepted placement manifest contains conservative per-building world AABBs.
A point outside *every* AABB (with a margin) is necessarily outside every
building solid. Roof/wall probes instead use triangle barycentres from the
accepted runtime GLB, whose hash is checked against the contract.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import struct
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def glb_faces(path):
    data = path.read_bytes()
    if data[:4] != b"glTF" or struct.unpack_from("<I", data, 8)[0] != len(data):
        raise ValueError(f"bad GLB: {path}")
    n = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20+n])
    offset = 20 + n
    bin_len, bin_type = struct.unpack_from("<II", data, offset)
    if bin_type != 0x004E4942:
        raise ValueError("GLB BIN missing")
    binary = memoryview(data)[offset+8:offset+8+bin_len]
    primitive = doc["meshes"][0]["primitives"][0]
    def accessor(index):
        acc = doc["accessors"][index]
        view = doc["bufferViews"][acc["bufferView"]]
        fmt = {5125: "I", 5123: "H", 5126: "f"}[acc["componentType"]]
        dim = {"SCALAR": 1, "VEC3": 3}[acc["type"]]
        size = struct.calcsize(fmt) * dim
        stride = view.get("byteStride", size)
        start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        return [struct.unpack_from("<" + fmt*dim, binary, start+i*stride)
                for i in range(acc["count"])]
    vertices = accessor(primitive["attributes"]["POSITION"])
    indices = accessor(primitive["indices"])
    for a, b, c in zip(indices[0::3], indices[1::3], indices[2::3]):
        yield vertices[a[0]], vertices[b[0]], vertices[c[0]]


def terrain_z(raw, x, y):
    # All planned in-bounds points are exact R16 vertices, so interpolation is unnecessary.
    col = round((x + 150000.0) / (250000.0 / 630.0))
    row = round((y + 150000.0) / (250000.0 / 630.0))
    if not (0 <= row <= 630 and 0 <= col <= 630):
        raise ValueError((x, y, row, col))
    value = struct.unpack_from("<H", raw, 2*(row*631+col))[0]
    return (value - 32768) * 200.0 / 128.0, row, col


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--run-root", type=Path, required=True)
    ap.add_argument("--plan-name", default="10-collision-plan.json")
    args = ap.parse_args()
    repo, run = args.repo.resolve(), args.run_root.resolve()
    base = repo / "unreal/Saved/XinyiUnrealV2Inputs/run-35822928983/unreal/Saved/XinyiUnrealV2Contract"
    contract_path = base / "xinyi_unreal_v2_contract.json"
    contract = json.loads(contract_path.read_text())
    r16_path = base / contract["outputs"]["heightmap_r16"]["path"]
    place_path = base / contract["outputs"]["building_component_placement"]["path"]
    for path, wanted in [(r16_path,contract["outputs"]["heightmap_r16"]["sha256"]),
                         (place_path,contract["outputs"]["building_component_placement"]["sha256"])]:
        if sha(path) != wanted:
            raise ValueError(f"source hash mismatch: {path}")
    raw = r16_path.read_bytes()
    if len(raw) != 631*631*2:
        raise ValueError("R16 dimensions")
    with gzip.open(place_path, "rt") as f:
        header = json.loads(next(f))["header"]
        boxes = [json.loads(line) for line in f]
    if len(boxes) != header["count"] or len(boxes) != 11130:
        raise ValueError("placement count")

    steps = []
    def add_step(id, x, y, kind, terrain=True):
        if terrain:
            z, row, col = terrain_z(raw, x, y)
            source_z = z + 1000
            ts = [{"id":id, "kind":kind, "xy_cm":[x,y], "expected_z_cm":z,
                   "heightmap_row_col":[row,col], "expect_hit":True}]
        elif terrain is False:
            source_z = 1000
            ts = [{"id":id, "kind":kind, "xy_cm":[x,y], "expect_hit":False}]
        else:
            source_z = 1000
            ts = []
        row = {"id":id,"kind":kind,"source_cm":[x,y,source_z],
               "terrain_samples":ts,"building_samples":[]}
        steps.append(row)
        return row

    spacing = 250000.0 / 630.0
    # Component centres and exact shared vertices of the accepted 5x5 heightfield.
    for r in range(5):
        for c in range(5):
            add_step(f"terrain_center_{r}_{c}", -150000+(c*126+63)*spacing,
                     -150000+(r*126+63)*spacing, "component_center")
    for r,c in [(1,1),(2,2),(3,3),(1,3)]:
        edge_x=-150000+c*126*spacing
        edge_y=-150000+r*126*spacing
        middle_y=-150000+(r*126+63)*spacing
        middle_x=-150000+(c*126+63)*spacing
        add_step(f"terrain_edge_x_{r}_{c}",edge_x,middle_y,"shared_edge")
        add_step(f"terrain_edge_y_{r}_{c}",middle_x,edge_y,"shared_edge")
        for side,delta in [("before",-spacing),("after",spacing)]:
            add_step(f"terrain_edge_x_{r}_{c}_{side}",edge_x+delta,middle_y,"shared_edge_flank")
            add_step(f"terrain_edge_y_{r}_{c}_{side}",middle_x,edge_y+delta,"shared_edge_flank")
    for r,c in [(1,1),(2,2),(3,3),(4,4)]:
        add_step(f"terrain_corner_{r}_{c}", -150000+c*126*spacing,
                 -150000+r*126*spacing,"shared_corner")
    add_step("xiangshan_slope", 75000, 75000, "southeast_slope")
    for id,x,y in [("west_outside",-170000,0),("east_outside",120000,0),
                    ("north_outside",0,-170000),("south_outside",0,120000)]:
        add_step(id,x,y,"outside_control",False)

    # Negative candidates are certified globally, including neighboring tiles.
    # The 5 m exclusion margin exceeds source coordinate rounding and import drift.
    margins = 500.0
    candidate_rows=[]
    added_border=False
    added_gap=False
    def add_empty(tile_id,x,y,kind,extra=None):
        step=add_step(f"{kind}_{tile_id}",x,y,kind,None)
        certificate={"basis":"outside every accepted building component AABB",
                     "manifest_sha256":sha(place_path),"global_component_count":len(boxes),
                     "minimum_aabb_clearance_cm":margins}
        if extra: certificate.update(extra)
        step["building_samples"].append({"id":f"{kind}_{tile_id}","kind":kind,
            "expected_tile":tile_id,"start_cm":[x,y,25000],"end_cm":[x,y,-1000],
            "expect_hit":False,"certificate":certificate})
        candidate_rows.append((tile_id,x,y,kind))
    for tile in contract["tiles"]:
        tx, north = tile["origin_enu_m"]
        x0, y0 = tx*100, -north*100-50000
        candidates=[]
        for ix in range(1,20):
            for iy in range(1,20):
                x,y=x0+ix*2500, y0+iy*2500
                covering=[b for b in boxes if
                          b["expected_ue_bounds_min_cm"][0]-margins <= x <= b["expected_ue_bounds_max_cm"][0]+margins and
                          b["expected_ue_bounds_min_cm"][1]-margins <= y <= b["expected_ue_bounds_max_cm"][1]+margins]
                if not covering:
                    candidates.append((x,y))
        if not candidates:
            continue
        x,y=min(candidates,key=lambda p:abs(p[0]-(x0+25000))+abs(p[1]-(y0+25000)))
        add_empty(tile["tile"],x,y,"open_area")
        if not added_border:
            border=min(candidates,key=lambda p:min(p[0]-x0,x0+50000-p[0],p[1]-y0,y0+50000-p[1]))
            border_distance=min(border[0]-x0,x0+50000-border[0],border[1]-y0,y0+50000-border[1])
            if border_distance<=2500:
                add_empty(tile["tile"],*border,"tile_border_empty",{"distance_to_tile_edge_cm":border_distance})
                added_border=True
        if not added_gap and tile["tile"]=="+000_+000":
            best=None
            for cx,cy in candidates:
                nearest=[]
                for b in boxes:
                    lo,hi=b["expected_ue_bounds_min_cm"],b["expected_ue_bounds_max_cm"]
                    dx=max(lo[0]-cx,0,cx-hi[0]);dy=max(lo[1]-cy,0,cy-hi[1])
                    d=math.hypot(dx,dy)
                    if d<5000:nearest.append((d,b["building_id"]))
                nearest.sort()
                distinct=[]
                for pair in nearest:
                    if pair[1] not in [p[1] for p in distinct]:distinct.append(pair)
                    if len(distinct)==2:break
                if len(distinct)==2 and (best is None or distinct[1][0]<best[0]):
                    best=(distinct[1][0],cx,cy,distinct)
            if best and best[0]<3000:
                add_empty(tile["tile"],best[1],best[2],"gap_between_buildings",
                          {"neighbor_buildings":[{"id":bid,"aabb_distance_cm":d} for d,bid in best[3]]})
                added_gap=True

    # Representative hit probes use actual source triangles, never AABB guesses.
    reps=[("low_rise","-003_-002"),("dense","+000_+000"),
          ("high_rise","+000_+001"),("hero_neighborhood","+000_+000"),
          ("tile_boundary","+001_+000")]
    selected=[]
    for category,tile_id in reps:
        tile=next(t for t in contract["tiles"] if t["tile"]==tile_id)
        glb=base / "building_runtime_tiles" / tile["runtime_building_glb"]
        if sha(glb)!=tile["runtime_building_sha256"]:
            raise ValueError(f"GLB hash mismatch {tile_id}")
        ox,oy,_=tile["expected_ue_translation_cm"]
        best_roof=None; best_wall=None
        low_boxes=[b for b in boxes if b["tile"]==tile_id and
                   b["expected_ue_bounds_max_cm"][2]-b["expected_ue_bounds_min_cm"][2] <=2500]
        wall_candidates=[]
        low_building=None
        for a,b,c in glb_faces(glb):
            # Source/game coordinates: x=east, y=up, z=-north. UE x/y/z = x/z/y.
            ux=b[0]-a[0]; uy=b[1]-a[1]; uz=b[2]-a[2]
            vx=c[0]-a[0]; vy=c[1]-a[1]; vz=c[2]-a[2]
            nx=uy*vz-uz*vy; ny=uz*vx-ux*vz; nz=ux*vy-uy*vx
            area=math.sqrt(nx*nx+ny*ny+nz*nz)
            if area < 1e-5: continue
            center=[ox+100*(a[0]+b[0]+c[0])/3,
                    oy+100*(a[2]+b[2]+c[2])/3,
                    100*(a[1]+b[1]+c[1])/3]
            # Winding may vary, so roof is near-horizontal; confirm top-down mesh hit later.
            if abs(ny)/area>.97 and area>2:
                if category=="low_rise":
                    for candidate in low_boxes:
                        lo,hi=candidate["expected_ue_bounds_min_cm"],candidate["expected_ue_bounds_max_cm"]
                        if lo[0]<=center[0]<=hi[0] and lo[1]<=center[1]<=hi[1] and abs(center[2]-hi[2])<=10:
                            if best_roof is None or area>best_roof[2]:
                                best_roof=(center[2],center,area);low_building=candidate
                            break
                elif best_roof is None or center[2]>best_roof[0]:
                    best_roof=(center[2],center,area)
            if math.hypot(nx,nz)/area>.97 and area>2:
                distance_to_border=min(abs(center[0]-ox),abs(center[0]-(ox+50000)),
                                       abs(center[1]-oy),abs(center[1]-(oy-50000)))
                score=(1/(1+distance_to_border) if category=="tile_boundary" else area)
                if category=="low_rise":
                    wall_candidates.append((score,center,(nx/area,nz/area),area))
                elif best_wall is None or score>best_wall[0]:
                    best_wall=(score,center,(nx/area,nz/area),area)
        if category=="low_rise" and low_building:
            lo,hi=low_building["expected_ue_bounds_min_cm"],low_building["expected_ue_bounds_max_cm"]
            eligible=[w for w in wall_candidates if lo[0]<=w[1][0]<=hi[0] and
                      lo[1]<=w[1][1]<=hi[1] and lo[2]<=w[1][2]<=hi[2]]
            if eligible:best_wall=max(eligible,key=lambda w:w[3])
        if not best_roof or not best_wall: raise ValueError(f"no source triangles: {tile_id}")
        selected.append((category,tile_id,best_roof,best_wall,sha(glb)))
        for kind,center,normal in [("roof",best_roof[1],None),("wall",best_wall[1],best_wall[2]),
                                   ("mass",best_wall[1],best_wall[2])]:
            x,y,z=center
            if normal is None:
                start=[x,y,z+1000];end=[x,y,z-1000]
            else:
                nx,ny=normal; reach=1000 if kind=="wall" else 3000
                start=[x+nx*reach,y+ny*reach,z];end=[x-nx*reach,y-ny*reach,z]
            step=add_step(f"positive_{category}_{kind}",x,y,"building_positive",None)
            step["building_samples"].append({"id":f"{category}_{kind}","kind":kind,
                "expected_tile":tile_id,"expect_hit":True,"start_cm":start,"end_cm":end,
                "certificate":{"source_glb_sha256":sha(glb),"triangle_center_cm":center,
                               "triangle_area_m2_x2":best_roof[2] if kind=="roof" else best_wall[3],
                               "source_building_id":low_building["building_id"] if category=="low_rise" else None,
                               "source_building_height_cm":(low_building["expected_ue_bounds_max_cm"][2]-low_building["expected_ue_bounds_min_cm"][2]) if category=="low_rise" else None}})
    # A terrain vertex beside source-derived building geometry tests the terrain/building transition.
    bx, by = selected[0][2][1][:2]
    c = round((bx+150000)/spacing); r = round((by+150000)/spacing)
    add_step("terrain_building_transition",-150000+c*spacing,-150000+r*spacing,
             "terrain_building_transition")
    doc={"schema":"xinyi-collision-plan/v1","status":"PLAN_ONLY",
         "world":"/Game/XinyiV2/L_XinyiV2_Contract_WP",
         "sources":{"contract_sha256":sha(contract_path),"heightmap_sha256":sha(r16_path),
                    "placement_sha256":sha(place_path)},
         "terrain_tolerance_cm":2.0,
         "terrain_tolerance_rationale":"Exact accepted R16 vertices; quantization half-step is 0.78125 cm; 2 cm allows float/Chaos position rounding, not source DTM accuracy",
         "steps":steps,"certified_negative_count":len(candidate_rows),
         "positive_categories":[x[0] for x in selected],
         "negative_categories":sorted({x[3] for x in candidate_rows}),
         "probe_channel":"ECC_Visibility"}
    out=run/args.plan_name
    with out.open("x",encoding="utf-8") as f: json.dump(doc,f,indent=2)
    print(json.dumps({"status":"PLAN_ONLY","steps":len(steps),"terrain_samples":sum(len(s['terrain_samples']) for s in steps),
                      "negative_samples":len(candidate_rows),"positive_samples":len(selected)*3,
                      "plan":str(out)}))


if __name__=="__main__": main()
