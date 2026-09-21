"""Diagnose full-Xinyi strict failures without changing production geometry policy."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import shapely
from shapely.ops import polygonize
from shapely.geometry import LineString, Point, shape
import trimesh

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
sys.path.insert(0,str(REPO/"tools/compiler"))
sys.path.insert(0,str(HERE))

from geometry import extrude_geos_polygon, repair_worldmodel_polygon, _polygonal_parts
from serialization_space import prepare_footprint, tile_origin, quantize_polygon
from strict_qa import strict_mesh_gate
from worldmodel import build_worldmodel

SOURCE=REPO/"data/generated/taipei/sample_buildings_epsg3826.geojson"
CITY=REPO/"cities/taipei/city.yaml"


def contact_summary(poly):
    exterior=LineString(poly.exterior.coords)
    contacts=[]
    holes=[LineString(h.coords) for h in poly.interiors]
    for i,h in enumerate(holes):
        g=exterior.intersection(h)
        if not g.is_empty:
            contacts.append({"kind":"exterior-hole","hole":i,"geom_type":g.geom_type,
                             "length":float(getattr(g,"length",0.0))})
    for i in range(len(holes)):
        for j in range(i+1,len(holes)):
            g=holes[i].intersection(holes[j])
            if not g.is_empty:
                contacts.append({"kind":"hole-hole","a":i,"b":j,"geom_type":g.geom_type,
                                 "length":float(getattr(g,"length",0.0))})
    return contacts


def polygonize_candidate(poly):
    lines=[LineString(poly.exterior.coords)]+[LineString(h.coords) for h in poly.interiors]
    noded=shapely.unary_union(lines)
    faces=list(polygonize(noded))
    kept=[p for p in faces if poly.covers(p.representative_point()) and p.area>0]
    if not kept:
        return {"faces":0,"pass":False,"reason":"no_kept_faces"}
    union=shapely.union_all(kept)
    rows=[]
    for i,p in enumerate(kept):
        try:
            m=extrude_geos_polygon(p,1.0)
            g=strict_mesh_gate(m,p,1.0,precision="float64")
            rows.append({"face":i,"area":float(p.area),"holes":len(p.interiors),
                         "pass":g["pass"],"failures":g["failures"]})
        except Exception as exc:
            rows.append({"face":i,"area":float(p.area),"holes":len(p.interiors),
                         "pass":False,"failures":[f"{type(exc).__name__}:{exc}"]})
    return {"faces":len(kept),"pass":all(r["pass"] for r in rows),
            "symmetric_difference_m2":float(union.symmetric_difference(poly).area),
            "rows":rows}


def adaptive_wall_probe(mesh, poly, gate):
    bad=gate.get("wrong_wall_face_indices",[])
    if not bad:
        return {"bad_faces":0,"resolvable":0,"unresolved":[]}
    v=np.asarray(mesh.vertices); f=np.asarray(mesh.faces); tri=v[f]
    cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    mag=np.linalg.norm(cross,axis=1)
    normals=np.divide(cross,mag[:,None],out=np.zeros_like(cross),where=mag[:,None]>0)
    coords=shapely.get_coordinates(poly)
    xy_error=max(1e-6,2*float(np.max(np.abs(np.spacing(coords.astype(np.float32))))))
    probes=sorted(set([.001,.0005,.0002,.0001,.00005,.00002,.00001,16*xy_error,8*xy_error,4*xy_error]),reverse=True)
    unresolved=[]; resolved=0
    for idx in bad:
        normal=normals[idx]
        center=tri[idx].mean(axis=0)[[0,2]]*[1,-1]
        outward=normal[[0,2]]*[1,-1]
        ok=False
        for probe in probes:
            if probe <= 2*xy_error: continue
            outside=Point(center+probe*outward)
            inside=Point(center-probe*outward)
            if (not poly.covers(outside)) and poly.covers(inside):
                ok=True; break
        if ok: resolved+=1
        else: unresolved.append(int(idx))
    return {"bad_faces":len(bad),"resolvable":resolved,"unresolved":unresolved,
            "minimum_probe_m":float(min(probes)),"xy_error_m":xy_error}


def candidate_policy(poly, height, kind, value):
    if kind == "set_precision":
        geom = shapely.set_precision(poly, grid_size=value, mode="valid_output")
    elif kind == "close":
        geom = poly.buffer(value, join_style=2).buffer(-value, join_style=2)
    elif kind == "set_precision_close":
        geom = shapely.set_precision(poly, grid_size=value, mode="valid_output")
        geom = geom.buffer(value, join_style=2).buffer(-value, join_style=2)
    else:
        raise ValueError(kind)
    parts=[quantize_polygon(p) for p in _polygonal_parts(geom)]
    if not parts or any(p.is_empty or not p.is_valid or p.area <= 0 for p in parts):
        return {"pass":False,"reason":"invalid_or_empty","parts":len(parts)}
    union=shapely.union_all(parts)
    rows=[]
    for i,p in enumerate(parts):
        try:
            m=extrude_geos_polygon(p,height)
            g=strict_mesh_gate(m,p,height,precision="float64")
            rows.append({"part":i,"pass":g["pass"],"failures":g["failures"]})
        except Exception as exc:
            rows.append({"part":i,"pass":False,"failures":[f"{type(exc).__name__}:{exc}"]})
    holes=sum(len(p.interiors) for p in parts)
    return {
        "pass":all(r["pass"] for r in rows),
        "parts":len(parts),
        "holes":holes,
        "original_holes":len(poly.interiors),
        "hole_count_changed":holes != len(poly.interiors),
        "area_delta_m2":float(union.area-poly.area),
        "symmetric_difference_m2":float(union.symmetric_difference(poly).area),
        "bounds_displacement_m":float(np.max(np.abs(np.asarray(union.bounds)-np.asarray(poly.bounds)))),
        "rows":rows,
    }


def run(report_path,out_path):
    report=json.loads(report_path.read_text())
    target={(f.get("building_id"),f.get("polygon_index")) for f in report["failures"]
            if f.get("building_id") is not None}
    wm=build_worldmodel(SOURCE,CITY,source_crs="EPSG:3826")
    rows=[]
    for b in wm["buildings"]:
        for pi,rec in enumerate(b["polygons"]):
            if (b["id"],pi) not in target: continue
            repaired,repair=repair_worldmodel_polygon(rec)
            origin=tile_origin(rec["centroid_enu"])
            for ri,p in enumerate(repaired):
                serial,fg=prepare_footprint(p,origin)
                for si,q in enumerate(serial):
                    mesh=extrude_geos_polygon(q,float(b["height_m"]))
                    gate=strict_mesh_gate(mesh,q,float(b["height_m"]),precision="float64")
                    policies={}
                    for kind,value in [
                        ("set_precision",0.0005),
                        ("set_precision",0.001),
                        ("set_precision",0.002),
                        ("close",0.0005),
                        ("close",0.001),
                        ("close",0.002),
                        ("set_precision_close",0.001),
                        ("set_precision_close",0.002),
                    ]:
                        key=f"{kind}_{value:g}"
                        policies[key]=candidate_policy(q,float(b["height_m"]),kind,value)
                    rows.append({
                        "building_id":b["id"],"polygon_index":pi,"repaired_part_index":ri,
                        "serialization_part_index":si,"repair_status":repair["status"],
                        "valid":bool(q.is_valid),"holes":len(q.interiors),
                        "area_m2":float(q.area),"minimum_clearance_m":float(q.minimum_clearance),
                        "wkt":q.wkt,
                        "strict_failures":gate["failures"],
                        "boundary_contacts":contact_summary(q),
                        "adaptive_wall_probe":adaptive_wall_probe(mesh,q,gate),
                        "polygonize":polygonize_candidate(q),
                        "candidate_policies":policies,
                    })
    result={
        "failed_source_parts":len(target),
        "diagnosed_components":len(rows),
        "rows":rows,
    }
    out_path.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({
        "failed_source_parts":len(target),
        "diagnosed_components":len(rows),
        "with_boundary_contacts":sum(bool(r["boundary_contacts"]) for r in rows),
        "polygonize_all_pass":sum(r["polygonize"]["pass"] for r in rows),
        "adaptive_wall_all_resolved":sum(
            r["adaptive_wall_probe"]["bad_faces"]>0 and
            not r["adaptive_wall_probe"]["unresolved"] for r in rows),
        "candidate_policy_pass_counts":{
            key:sum(r["candidate_policies"][key]["pass"] for r in rows)
            for key in (rows[0]["candidate_policies"] if rows else {})
        },
    },indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    run(a.report,a.out)
