"""相思樹 lookdev v1: turn Mix T (instances_mix.json: 紅楠 A + crown B, 989 trees) into a two-species forest (instances_acacia.json).

    python tools/forest/hillside_acacia_mix.py <terrain_dir> [share] [seed]
Writes <terrain_dir>/instances_acacia.json, acacia_stats.json, acacia_map.png. instances_mix.json (the Mix T baseline) is read only.

Ecology used (docs/research/taiwan-acacia-confusa-lookdev-v1.md): in the low hills around Taipei 相思樹 is mostly the legacy of
Japanese-era / post-war fuelwood, charcoal and mine-prop plantations. The old stands persist on ridges, upper and sunny (S-SW facing,
leeward of the NE winter monsoon) slopes and on disturbed ground, while ravines and lower, moister slopes are taken by the native evergreen
broadleaf forest (紅楠 and companions) that is succeeding the plantations. So 相思樹 is placed by SITE, as stands, not tree by tree:
* score = 0.55 x a 30 m plantation-patch field + 0.35 x ridge (TPI) + 0.20 x sunny aspect (S-SW, weighted by slope) + 0.10 x upper slope
  (height within the block) + 0.15 x next to a gap - 1.0 in valleys (TPI < -2 m) + small jitter; then smoothed with the neighbours
  within 11 m (0.5 own + 0.5 mean) so it forms stands with ragged edges; the top `share` (default 25 %) become 相思樹 (form C);
* every tree keeps its canopy footprint: crown radius and crown centre from Mix T. 相思樹 instance scale = crown radius / 6.95 m (the
  acacia mesh crown half-width), height x U(1.05, 1.30) (stand-grown crowns are narrower / taller than the open-grown golden); the crown
  offset of the leaning trunk (+0.56 m local X) is turned downslope (+-30 deg), the trunk is placed so the CROWN centre stays put;
* leaf tints = M_TL_Acacia_LeafCards instances 5 / 6 (sunny yellow-olive) / 7 (greyer) from a 20 m tone field biased toward 6 on sunny faces
  (+20 % random), so the stands are not one flat colour;
* the total tree count is unchanged (989), so A (Mix T) vs B (this file) compare the same canopy footprint.
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

SHARE = 0.25
C_CROWN_R = 6.95  # m, crown half-width of the acacia LOD0 cards at scale 1 (bounds half-extents 7.50 / 6.40 m)
C_SPHERE_R = 8.22  # m, bounds sphere radius at scale 1
C_CROWN_OFFSET = (0.563, -0.126)  # m, crown centre relative to the trunk, UE local X / Y
C_CROWN_Z = 6.69  # m, bounds centre height at scale 1
SUNNY_AZ = -115.0  # deg ccw from east: SSW-facing (downslope toward SSW)
PATCH_M = 30.0  # plantation-patch field scale
NB_M = 11.0  # neighbour smoothing radius
SEED = 20261018


def main(d, share=SHARE, seed=SEED):
    d = Path(d)
    T = Terrain(d)
    src = json.loads((d / "instances_mix.json").read_text(encoding="utf-8"))
    inst = src["instances"]
    h_ref = src["h_ref_m"]
    rng = np.random.default_rng(seed)
    n = len(inst)
    # crown centre (B trees store it separately; their x / y is the trunk)
    cx = np.array([i.get("crown_centre_m", [i["x_m"], i["y_m"]])[0] for i in inst])
    cy = np.array([i.get("crown_centre_m", [i["x_m"], i["y_m"]])[1] for i in inst])
    r = np.array([i["crown_r_m"] for i in inst])
    N = 300
    f = gaussian_filter(rng.standard_normal((N, N)), PATCH_M / 2.355, mode="wrap")
    f = (f - f.mean()) / f.std()
    patch = map_coordinates(f, [np.clip(N / 2 - cy, 0, N - 1), np.clip(cx + N / 2, 0, N - 1)], order=1)
    tpi = T.sample(T.tpi, cx, cy)
    slope = T.sample(T.slope, cx, cy)
    elev = T.height(cx, cy)
    gx, gy = T.sample(T.gx, cx, cy), T.sample(T.gy, cx, cy)
    down = np.degrees(np.arctan2(-gy, -gx))
    sunny = np.cos(np.radians(down - SUNNY_AZ)) * np.clip(slope / 20.0, 0.0, 1.0)
    # gaps: same definition as hillside_mix.py (uncovered cells with inscribed radius >= 2.5 m)
    res = 1.0
    m = int(2 * BLOCK_HALF / res)
    occ = np.zeros((m, m), bool)
    yy, xx = np.mgrid[0:m, 0:m]
    xc, yc = -BLOCK_HALF + (xx + 0.5) * res, BLOCK_HALF - (yy + 0.5) * res
    for k in range(n):
        r0, c0 = int((BLOCK_HALF - cy[k]) / res), int((cx[k] + BLOCK_HALF) / res)
        rad = int(r[k] / res) + 1
        a0, a1, b0, b1 = max(r0 - rad, 0), min(r0 + rad + 1, m), max(c0 - rad, 0), min(c0 + rad + 1, m)
        occ[a0:a1, b0:b1] |= (xc[a0:a1, b0:b1] - cx[k]) ** 2 + (yc[a0:a1, b0:b1] - cy[k]) ** 2 <= r[k] ** 2
    gap_core = distance_transform_edt(~occ) * res >= 2.5
    dist_gap = distance_transform_edt(~gap_core) * res
    near_gap = map_coordinates(dist_gap, [np.clip((BLOCK_HALF - cy) / res, 0, m - 1), np.clip((cx + BLOCK_HALF) / res, 0, m - 1)], order=1) < r + 6.0
    z = lambda a: (a - a.mean()) / (a.std() + 1e-9)  # noqa: E731
    valley = tpi < -2.0
    s0 = 0.55 * patch + 0.35 * z(tpi) + 0.20 * sunny + 0.10 * z(elev) + 0.15 * near_gap - 1.0 * valley + rng.normal(0, 0.12, n)
    dd = np.hypot(cx[:, None] - cx[None, :], cy[:, None] - cy[None, :])
    nb = (dd < NB_M) & (dd > 0)
    s_nb = np.where(nb.any(1), (nb * s0[None, :]).sum(1) / np.maximum(nb.sum(1), 1), s0)
    score = 0.5 * s0 + 0.5 * s_nb
    is_c = score >= np.quantile(score, 1 - share)
    ft = gaussian_filter(rng.standard_normal((N, N)), 20.0 / 2.355, mode="wrap")
    tone = map_coordinates((ft - ft.mean()) / ft.std(), [np.clip(N / 2 - cy, 0, N - 1), np.clip(cx + N / 2, 0, N - 1)], order=1)

    out = []
    for k, it in enumerate(inst):
        it = dict(it)
        if not is_c[k]:
            out.append(it)
            continue
        prev = it["form"]
        s = r[k] / C_CROWN_R
        aniso = rng.uniform(0.92, 1.08)
        sz = s * rng.uniform(1.05, 1.30)
        yaw_ue = -down[k] - math.degrees(math.atan2(C_CROWN_OFFSET[1], C_CROWN_OFFSET[0])) + rng.uniform(-30, 30)
        cyw, syw = math.cos(math.radians(yaw_ue)), math.sin(math.radians(yaw_ue))
        ox, oy = C_CROWN_OFFSET[0] * s * aniso, C_CROWN_OFFSET[1] * s / aniso
        dx_ue, dy_ue = ox * cyw - oy * syw, ox * syw + oy * cyw
        tx, ty = cx[k] - dx_ue, cy[k] + dy_ue  # local east = UE X, local north = -UE Y
        sl_t = float(T.sample(T.slope, tx, ty)[0])
        tz = float(T.height(tx, ty)[0]) - (0.25 + 0.35 * math.tan(math.radians(min(sl_t, 60.0))))
        t = tone[k] + 0.4 * sunny[k]
        variant = 6 if t > 0.45 else (7 if t < -0.45 else 5)
        if rng.random() < 0.2:
            variant = int(rng.integers(5, 8))
        # acacias lean more than the 紅楠 (light-seeking, shallow-rooted on slopes): keep the slope lean, add a little downslope
        lean = min(0.15 * slope[k], 8.0)
        le = lean * math.cos(math.radians(down[k])) + rng.uniform(-2.5, 2.5)
        ln = lean * math.sin(math.radians(down[k])) + rng.uniform(-2.5, 2.5)
        it.update(form="C", replaced_form=prev, x_m=round(tx, 3), y_m=round(ty, 3), z_m=round(tz, 3),
                  ue_cm=[round(tx * 100, 1), round(-ty * 100, 1), round((tz - h_ref) * 100, 1)],
                  yaw_deg=round(yaw_ue % 360, 2), lean_east_deg=round(le, 2), lean_north_deg=round(ln, 2),
                  scale_xy=round(s, 4), scale_x=round(s * aniso, 4), scale_y=round(s / aniso, 4), scale_z=round(sz, 4),
                  variant=variant, sphere_r_m=C_SPHERE_R, crown_z_m=C_CROWN_Z, crown_centre_m=[round(float(cx[k]), 3), round(float(cy[k]), 3)])
        out.append(it)
    forms = np.array([i["form"] for i in out])
    H = {"A": 14.2, "B": 12.2, "C": 13.2}
    hts = {f: np.array([H[f] * i["scale_z"] for i in out if i["form"] == f]) for f in "ABC"}
    # crown-area share (nominal discs) - what the aerial view sees
    area = {f: float(sum(math.pi * i["crown_r_m"] ** 2 for i in out if i["form"] == f)) for f in "ABC"}
    tot = sum(area.values())
    # stand structure: share of acacia whose nearest-3 neighbours include >= 2 acacia
    idx_c = np.flatnonzero(is_c)
    nn3 = np.argsort(dd[idx_c], 1)[:, 1:4]
    clumped = float(np.mean(is_c[nn3].sum(1) >= 2))
    st = {"seed": seed, "trees": n, "per_form": {f: int((forms == f).sum()) for f in "ABC"}, "acacia_share_trees": round(float(is_c.mean()), 3),
          "crown_area_share": {f: round(area[f] / tot, 3) for f in "ABC"},
          "replaced_from": {f: int(sum(1 for i in out if i.get("replaced_form") == f)) for f in "AB"},
          "variants": {str(v): sum(1 for i in out if i["variant"] == v) for v in range(8)},
          "height_m_est": {f: {"median": round(float(np.median(hts[f])), 2), "p90": round(float(np.percentile(hts[f], 90)), 2)} for f in "ABC"},
          "acacia_on": {"ridge_tpi_gt2": float((tpi[is_c] > 2).mean()), "valley_tpi_lt-2": float((tpi[is_c] < -2).mean()),
                        "sunny_gt0.35": float((sunny[is_c] > 0.35).mean()), "near_gap": float(near_gap[is_c].mean())},
          "others_on": {"ridge_tpi_gt2": float((tpi[~is_c] > 2).mean()), "valley_tpi_lt-2": float((tpi[~is_c] < -2).mean()),
                        "sunny_gt0.35": float((sunny[~is_c] > 0.35).mean()), "near_gap": float(near_gap[~is_c].mean())},
          "acacia_with_2of3_nearest_acacia": round(clumped, 3),
          "rules": {"share": share, "patch_m": PATCH_M, "neighbour_m": NB_M, "c_crown_r_m": C_CROWN_R, "c_sphere_r_m": C_SPHERE_R, "sunny_azimuth_ccw_from_east_deg": SUNNY_AZ}}
    (d / "instances_acacia.json").write_text(json.dumps({"stats": st, "h_ref_m": h_ref, "instances": out}, indent=0) + "\n", encoding="utf-8")
    (d / "acacia_stats.json").write_text(json.dumps(st, indent=1) + "\n", encoding="utf-8")
    hs = Image.open(d / "terrain_hillshade.png").convert("RGB")
    c0 = (T.n - 1) / 2.0
    px = BLOCK_HALF / T.sp
    crop = hs.crop((int(c0 - px - 10), int(c0 - px - 10), int(c0 + px + 11), int(c0 + px + 11))).resize((1060, 1060), Image.BILINEAR)
    sc = 1060 / (2 * BLOCK_HALF + 20 * T.sp)
    ov = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    col = {"A": (30, 110, 40, 120), "B": (60, 160, 120, 120), "C": (230, 200, 30, 170)}
    for k, it in enumerate(out):
        u, v = (cx[k] + BLOCK_HALF + 10 * T.sp) * sc, (BLOCK_HALF - cy[k] + 10 * T.sp) * sc
        dr.ellipse((u - r[k] * sc, v - r[k] * sc, u + r[k] * sc, v + r[k] * sc), fill=col[it["form"]], outline=(0, 0, 0, 160))
    o = Image.alpha_composite(crop.convert("RGBA"), ov).convert("RGB")
    ImageDraw.Draw(o).text((8, 8), "acacia mix: %d Machilus A (dark green) + %d Machilus crown B (teal) + %d Acacia confusa (yellow), N up" % tuple(st["per_form"][f] for f in "ABC"),
                           fill=(255, 0, 0))
    o.save(d / "acacia_map.png")
    print(json.dumps(st, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else SHARE, int(sys.argv[3]) if len(sys.argv) > 3 else SEED)
