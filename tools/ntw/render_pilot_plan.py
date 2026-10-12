"""Plan-view PNG of a pilot, drawn from the EXPORTED GLB tiles (roof triangles, colour = building height).

usage: render_pilot_plan.py --tiles <dir/tiles> --out plan.png [--px 1000] [--title text]
Axes: x = NTW east, glTF -z = NTW north. Tile boundaries (500 m) are drawn as thin lines.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw


def ramp(h):
    # 3 m (pale) -> 25 m -> 100 m+ (dark), simple perceptual-ish ramp
    t = min(max((np.log(max(h, 3.0)) - np.log(3.0)) / (np.log(150.0) - np.log(3.0)), 0), 1)
    return (int(235 - 190 * t), int(235 - 150 * t), int(215 - 60 * t) if t < 0.5 else int(215 - 60 * t))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--px", type=int, default=1000)
    ap.add_argument("--title", default="")
    a = ap.parse_args()
    tris, heights = [], []
    for f in sorted(a.tiles.glob("*.glb")):
        sc = trimesh.load_scene(str(f), process=False)
        for n in sc.graph.nodes_geometry:
            tr, g = sc.graph[n]
            m = sc.geometry[g].copy()
            m.apply_transform(tr)
            v, fc = np.asarray(m.vertices), np.asarray(m.faces)
            top = v[:, 1].max()
            roof = fc[np.all(np.isclose(v[fc][:, :, 1], top, atol=1e-4), axis=1)]
            if top <= 0.1 or len(roof) == 0:
                continue
            for t in roof:
                tris.append(v[t][:, [0, 2]])
                heights.append(top)
    allp = np.concatenate(tris)
    x0, x1 = allp[:, 0].min(), allp[:, 0].max()
    z0, z1 = allp[:, 1].min(), allp[:, 1].max()
    s = (a.px - 20) / max(x1 - x0, z1 - z0)
    W, H = int((x1 - x0) * s) + 20, int((z1 - z0) * s) + 40
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    order = np.argsort(heights)
    for i in order:
        pts = [((p[0] - x0) * s + 10, (p[1] - z0) * s + 30) for p in tris[i]]
        d.polygon(pts, fill=ramp(heights[i]))
    gx = np.arange(np.floor(x0 / 500) * 500, x1 + 500, 500)
    gz = np.arange(np.floor(z0 / 500) * 500, z1 + 500, 500)
    for gxx in gx:
        d.line([((gxx - x0) * s + 10, 30), ((gxx - x0) * s + 10, H)], fill=(200, 60, 60), width=1)
    for gzz in gz:
        d.line([(10, (gzz - z0) * s + 30), (W, (gzz - z0) * s + 30)], fill=(200, 60, 60), width=1)
    d.text((10, 8), f"{a.title}  |  {len(set(map(id, tris)))} roof tris  |  red = 500 m tile grid, colour = height (3-150 m)", fill=(0, 0, 0))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(a.out, optimize=True)
    print(a.out, a.out.stat().st_size)


if __name__ == "__main__":
    main()
