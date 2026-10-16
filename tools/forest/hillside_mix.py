"""Hillside forest mix v0: turn the single-紅楠 placement (instances.json, version A) into a two-crown-form mix (version B).

    python tools/forest/hillside_mix.py <terrain_dir> [seed]
Writes <terrain_dir>/instances_mix.json and mix_stats.json, mix_map.png. instances.json (the A baseline) is read only.

Every tree keeps its position-derived canopy footprint (crown centre and radius) from A; about 40 % of them become crown form B
(紅楠 second crown form: lower, broader, lopsided, looser; tools/treegen/params/machilus_crown_b.json). Which ones is ecological, not
per-tree random, so the mix reads as stands, not noise:
* score = 0.55 x a 30 m clump field + 0.25 x ridge (TPI) + 0.20 x slope + 0.35 x "next to a gap" (next to a
  real opening: an uncovered hole with inscribed radius >= 2.5 m, crown edge within 6 m), small jitter; the top MIX_SHARE of trees by score become B -> B forms clumps on ridges, steep faces and gap
  edges (light-demanding, wind-shaped crowns), the A dome dominates valleys and gentle slopes;
* B instance scale = crown radius / 8.4 m (B mesh crown half-width); height x U(1.05, 1.30) -> at equal footprint B is ~20-25 % lower than A,
  which adds height layering; the lopsided side (+1.8 m local X) is turned downslope (+-25 deg), and the trunk is placed so the CROWN
  centre stays where A's crown was;
* B leaves use their own two tints (existing M_TL_LeafCards parameters, lighter / yellower than A's family): variants 3 / 4.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt, gaussian_filter, map_coordinates

sys.path.insert(0, str(Path(__file__).parent))
from hillside_scatter import BLOCK_HALF, Terrain  # noqa: E402

MIX_SHARE = 0.40
B_CROWN_R = 8.4  # m, crown half-width of the crown-B mesh at scale 1 (UE bounds extent 8.73 / 8.15 m)
B_SPHERE_R = 9.067  # m, UE bounds sphere radius of crown B
B_CROWN_OFFSET = (1.784, -0.176)  # m, crown-bounds centre relative to the trunk, UE local X / Y
B_CROWN_Z = 6.07  # m, crown-bounds centre height at scale 1
A_SPHERE_R, A_CROWN_Z = 8.377, 7.1
SEED = 20261017


def main(d, seed=SEED):
    d = Path(d)
    T = Terrain(d)
    src = json.loads((d / "instances.json").read_text(encoding="utf-8"))
    inst = src["instances"]
    h_ref = src["h_ref_m"]
    rng = np.random.default_rng(seed)
    n = len(inst)
    x = np.array([i["x_m"] for i in inst])
    y = np.array([i["y_m"] for i in inst])
    r = np.array([i["crown_r_m"] for i in inst])
    N = 300
    f = gaussian_filter(rng.standard_normal((N, N)), 30.0 / 2.355, mode="wrap")
    f = (f - f.mean()) / f.std()
    clump = map_coordinates(f, [np.clip(N / 2 - y, 0, N - 1), np.clip(x + N / 2, 0, N - 1)], order=1)
    tpi = T.sample(T.tpi, x, y)
    slope = T.sample(T.slope, x, y)
    # gap pixels = block cells farther than their own crown from every crown centre (the designated gaps are exactly where no tree stands)
    res = 1.0
    m = int(2 * BLOCK_HALF / res)
    occ = np.zeros((m, m), bool)
    yy, xx = np.mgrid[0:m, 0:m]
    xc, yc = -BLOCK_HALF + (xx + 0.5) * res, BLOCK_HALF - (yy + 0.5) * res
    for k in range(n):
        r0, c0 = int((BLOCK_HALF - y[k]) / res), int((x[k] + BLOCK_HALF) / res)
        rad = int(r[k] / res) + 1
        a0, a1, b0, b1 = max(r0 - rad, 0), min(r0 + rad + 1, m), max(c0 - rad, 0), min(c0 + rad + 1, m)
        occ[a0:a1, b0:b1] |= (xc[a0:a1, b0:b1] - x[k]) ** 2 + (yc[a0:a1, b0:b1] - y[k]) ** 2 <= r[k] ** 2
    # real openings only: uncovered cells whose inscribed radius is >= 2.5 m (the closure pass filled every hole wider than 3 m outside
    # the designated gaps, so these are the gaps); "next to a gap" = crown edge within 6 m of one
    gap_core = distance_transform_edt(~occ) * res >= 2.5
    dist_gap = distance_transform_edt(~gap_core) * res
    near_gap = map_coordinates(dist_gap, [np.clip((BLOCK_HALF - y) / res, 0, m - 1), np.clip((x + BLOCK_HALF) / res, 0, m - 1)], order=1) < r + 6.0
    z = lambda a: (a - a.mean()) / (a.std() + 1e-9)  # noqa: E731
    score = 0.55 * clump + 0.25 * z(tpi) + 0.20 * z(slope) + 0.35 * near_gap + rng.normal(0, 0.15, n)
    is_b = score >= np.quantile(score, 1 - MIX_SHARE)

    gx, gy = T.sample(T.gx, x, y), T.sample(T.gy, x, y)
    down = np.degrees(np.arctan2(-gy, -gx))  # steepest descent, deg ccw from east (north up)
    out = []
    for k, it in enumerate(inst):
        it = dict(it)
        if not is_b[k]:
            it.update(form="A", sphere_r_m=A_SPHERE_R, crown_z_m=A_CROWN_Z)
            out.append(it)
            continue
        s = r[k] / B_CROWN_R
        aniso = rng.uniform(0.92, 1.08)
        sz = s * rng.uniform(1.05, 1.30)
        yaw_ue = -down[k] + math.degrees(math.atan2(B_CROWN_OFFSET[1], B_CROWN_OFFSET[0])) * -1 + rng.uniform(-25, 25)
        # trunk = crown centre - rotated crown offset (UE frame: Y = south)
        cy, sy_ = math.cos(math.radians(yaw_ue)), math.sin(math.radians(yaw_ue))
        ox, oy = B_CROWN_OFFSET[0] * s * aniso, B_CROWN_OFFSET[1] * s / aniso
        dx_ue, dy_ue = ox * cy - oy * sy_, ox * sy_ + oy * cy
        tx, ty = x[k] - dx_ue, y[k] + dy_ue  # local east = UE X, local north = -UE Y
        tz = float(T.height(tx, ty)[0]) - (0.25 + 0.35 * math.tan(math.radians(min(float(T.sample(T.slope, tx, ty)[0]), 60.0))))
        variant = 3 if rng.random() < 0.6 else 4
        it.update(form="B", x_m=round(tx, 3), y_m=round(ty, 3), z_m=round(tz, 3),
                  ue_cm=[round(tx * 100, 1), round(-ty * 100, 1), round((tz - h_ref) * 100, 1)],
                  yaw_deg=round(yaw_ue % 360, 2), lean_east_deg=round(it["lean_east_deg"] * 0.5, 2), lean_north_deg=round(it["lean_north_deg"] * 0.5, 2),
                  scale_xy=round(s, 4), scale_x=round(s * aniso, 4), scale_y=round(s / aniso, 4), scale_z=round(sz, 4),
                  variant=variant, sphere_r_m=B_SPHERE_R, crown_z_m=B_CROWN_Z, crown_centre_m=[round(float(x[k]), 3), round(float(y[k]), 3)])
        out.append(it)
    nb = int(is_b.sum())
    hA = np.array([14.2 * i["scale_z"] for i in out if i["form"] == "A"])
    hB = np.array([12.2 * i["scale_z"] for i in out if i["form"] == "B"])
    st = {"seed": seed, "trees": n, "form_A": n - nb, "form_B": nb, "mix_B_share": round(nb / n, 3),
          "variants": {str(v): sum(1 for i in out if i["variant"] == v) for v in range(5)},
          "height_m_est": {"A_median": float(np.median(hA)), "B_median": float(np.median(hB)), "A_p90": float(np.percentile(hA, 90)),
                           "B_p90": float(np.percentile(hB, 90))},
          "B_on": {"ridge_tpi_gt2": float((tpi[is_b] > 2).mean()), "slope_gt35": float((slope[is_b] > 35).mean()), "near_gap": float(near_gap[is_b].mean())},
          "A_on": {"ridge_tpi_gt2": float((tpi[~is_b] > 2).mean()), "slope_gt35": float((slope[~is_b] > 35).mean()), "near_gap": float(near_gap[~is_b].mean())},
          "rules": {"mix_share": MIX_SHARE, "b_crown_r_m": B_CROWN_R, "b_sphere_r_m": B_SPHERE_R}}
    (d / "instances_mix.json").write_text(json.dumps({"stats": st, "h_ref_m": h_ref, "instances": out}, indent=0) + "\n", encoding="utf-8")
    (d / "mix_stats.json").write_text(json.dumps(st, indent=1) + "\n", encoding="utf-8")
    # map
    hs = Image.open(d / "terrain_hillshade.png").convert("RGB")
    c0 = (T.n - 1) / 2.0
    px = BLOCK_HALF / T.sp
    crop = hs.crop((int(c0 - px - 10), int(c0 - px - 10), int(c0 + px + 11), int(c0 + px + 11))).resize((1060, 1060), Image.BILINEAR)
    sc = 1060 / (2 * BLOCK_HALF + 20 * T.sp)
    ov = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    for k in range(n):
        u, v = (x[k] + BLOCK_HALF + 10 * T.sp) * sc, (BLOCK_HALF - y[k] + 10 * T.sp) * sc
        col = (200, 170, 30, 140) if is_b[k] else (30, 110, 40, 120)
        dr.ellipse((u - r[k] * sc, v - r[k] * sc, u + r[k] * sc, v + r[k] * sc), fill=col, outline=(0, 0, 0, 160))
    o = Image.alpha_composite(crop.convert("RGBA"), ov).convert("RGB")
    ImageDraw.Draw(o).text((8, 8), "mix v0: %d A (green, dome) + %d B (yellow, crown form B), N up" % (n - nb, nb), fill=(255, 0, 0))
    o.save(d / "mix_map.png")
    print(json.dumps(st, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else SEED)
