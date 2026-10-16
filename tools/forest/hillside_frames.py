"""Hillside forest look-dev v1: evidence from the NATIVE standalone -game MRQ frames (numpy + Pillow; ffmpeg on PATH for the videos).

    python tools/forest/hillside_frames.py <terrain_dir> <movies_dir> <rev> <out_dir> [views_file instances_file]

1. Stills: frames still_hold-1, 2*hold-1, 3*hold-1 of hf_stills_{forest,empty}_<rev>_01 -> still_<view>.png (native 1920x1080, lossless),
   still_<view>.jpg (q92) and crop_<view>.png (native-pixel 640x360 centre crop).
2. Tree mask = pixels where the forest frame differs from the empty-forest frame of the same pose (max channel |diff| > 6/255), opened by
   one pixel. Canopy screen share = mask share of the frame; canopy cover in block = mask share among pixels whose ground hit (heightmap ray
   march, trees ignored, 192 x 108 rays) lies in the 250 m block - the dissolve proxy across 50 / 200 / 500 m AGL.
3. NATIVE MATERIAL GUARD (fails the run): among tree-mask pixels, median HSV saturation >= 0.12 and >= 70 % of them with hue 50-170 deg.
   The engine default material (the PR #31 failure) is grey: saturation ~0.
4. Flight: hf_flight_forest_<rev>_01 -> fly_<rev>.mp4 (clean, 60 fps, H.264 crf 16) and fly_<rev>_annotated.mp4 (frame, AGL, calculated
   LOD mix of in-frustum trees, a red bar at frames where >= 3 trees change calculated LOD). Pop proxy: per frame, mean |frame - previous
   frame| over the lower 2/3 of the image (canopy), divided by its 9-frame rolling median; frames with ratio > 1.5 are listed with the
   calculated switch count of that frame. Tile proxy: the same per 8 x 6 tile (> 2x the tile's rolling median and > 2 grey levels);
   the share of hit frames within +-1 frame of a calculated switch is compared with the chance share of all frames.
Writes <out_dir>/frames_report.json.
"""
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from hillside_scatter import BLOCK_HALF, MESH_SPHERE_R, Terrain  # noqa: E402
from hillside_views import ASPECT, HFOV, LOD_CUTS, dir_from  # noqa: E402

TD, MOV, REV, OUT = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
OUT.mkdir(parents=True, exist_ok=True)
V = json.loads((TD / (sys.argv[5] if len(sys.argv) > 5 else "views.json")).read_text(encoding="utf-8"))
INST = json.loads((TD / (sys.argv[6] if len(sys.argv) > 6 else "instances.json")).read_text(encoding="utf-8"))["instances"]
T = Terrain(TD)
rep = {"rev": REV, "stills": {}, "guard": {}, "flight": {}}


def frame(tag, f):
    return np.asarray(Image.open(MOV / tag / "frames" / ("frame_%04d.png" % f)).convert("RGB"), dtype=np.float32) / 255.0


def block_mask(cam, bearing, pitch, w=192, h=108):
    tx = math.tan(math.radians(HFOV / 2))
    ty = tx / ASPECT
    f = dir_from(bearing, pitch)
    r = np.cross(f, [0, 0, 1.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    sx = (2 * (np.arange(w) + 0.5) / w - 1) * tx
    sy = (1 - 2 * (np.arange(h) + 0.5) / h) * ty
    SX, SY = np.meshgrid(sx, sy)
    D = f[None, None, :] + SX[..., None] * r + SY[..., None] * u
    D = (D / np.linalg.norm(D, axis=-1, keepdims=True)).reshape(-1, 3)
    hit = np.zeros(len(D), bool)
    p = np.zeros((len(D), 3))
    alive = np.ones(len(D), bool)
    for k in range(1, 1500):
        q = cam[None, :] + D * (k * 1.5)
        ing = (np.abs(q[:, 0]) < T.half - 2) & (np.abs(q[:, 1]) < T.half - 2)
        hh = alive & ing & (q[:, 2] <= T.height(q[:, 0], q[:, 1]))
        hit |= hh
        p[hh] = q[hh]
        alive &= ~hh & ing
        if not alive.any():
            break
    inb = hit & (np.abs(p[:, 0]) <= BLOCK_HALF) & (np.abs(p[:, 1]) <= BLOCK_HALF)
    m = Image.fromarray((inb.reshape(h, w) * 255).astype(np.uint8)).resize((1920, 1080), Image.NEAREST)
    return np.asarray(m) > 127


def hsv(rgb):
    mx, mn = rgb.max(-1), rgb.min(-1)
    c = mx - mn
    s = np.where(mx > 1e-6, c / np.maximum(mx, 1e-6), 0)
    r_, g_, b_ = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.zeros_like(mx)
    nz = c > 1e-6
    i = nz & (mx == r_)
    hue[i] = (60 * ((g_[i] - b_[i]) / c[i]) + 360) % 360
    i = nz & (mx == g_) & ~(mx == r_)
    hue[i] = 60 * ((b_[i] - r_[i]) / c[i]) + 120
    i = nz & (mx == b_) & ~(mx == r_) & ~(mx == g_)
    hue[i] = 60 * ((r_[i] - g_[i]) / c[i]) + 240
    return hue, s, mx


def opened(m):
    e = m.copy()
    e[1:, :] &= m[:-1, :]
    e[:-1, :] &= m[1:, :]
    e[:, 1:] &= m[:, :-1]
    e[:, :-1] &= m[:, 1:]
    d = e.copy()
    d[1:, :] |= e[:-1, :]
    d[:-1, :] |= e[1:, :]
    d[:, 1:] |= e[:, :-1]
    d[:, :-1] |= e[:, 1:]
    return d


hold = V["still_hold_frames"]
guard_ok = True
for i, s in enumerate(V["stills"]):
    f = (i + 1) * hold - 1
    a, b = frame("hf_stills_forest_%s_01" % REV, f), frame("hf_stills_empty_%s_01" % REV, f)
    name = s["name"]
    Image.fromarray((a * 255).astype(np.uint8)).save(OUT / ("still_%s.png" % name))
    Image.fromarray((a * 255).astype(np.uint8)).save(OUT / ("still_%s.jpg" % name), quality=92)
    Image.fromarray((a[360:720, 640:1280] * 255).astype(np.uint8)).save(OUT / ("crop_%s.png" % name))
    tree = opened(np.abs(a - b).max(-1) > 6 / 255)
    blk = block_mask(np.array(s["pos_local_m"]), s["bearing_deg"], s["pitch_deg"])
    hue, sat, val = hsv(a[tree])
    green = float(((hue >= 50) & (hue <= 170)).mean()) if tree.any() else 0.0
    med_s = float(np.median(sat)) if tree.any() else 0.0
    ok = bool(tree.mean() > 0.02 and med_s >= 0.12 and green >= 0.70)
    guard_ok &= ok
    rep["stills"][name] = {"frame": f, "agl_m": s["agl_m"], "pitch_deg": s["pitch_deg"], "tree_pixel_share": round(float(tree.mean()), 4),
                           "block_pixel_share": round(float(blk.mean()), 4),
                           "canopy_cover_in_block_screen": round(float((tree & blk).sum() / max(blk.sum(), 1)), 4),
                           "tree_px_median_saturation": round(med_s, 3), "tree_px_green_hue_share": round(green, 3),
                           "tree_px_median_value": round(float(np.median(val)), 3) if tree.any() else None,
                           "lod_calc_in_frustum": s["lod_calc_in_frustum"], "native_material_guard": "PASS" if ok else "FAIL"}
    vis = (a * 255).astype(np.uint8).copy()
    vis[tree] = (0.5 * vis[tree] + [0, 127, 0]).astype(np.uint8)
    vis[blk & ~tree] = (0.5 * vis[blk & ~tree] + [127, 0, 0]).astype(np.uint8)
    Image.fromarray(vis).resize((960, 540), Image.BILINEAR).save(OUT / ("mask_%s.jpg" % name), quality=85)
rep["guard"] = {"native_material_guard": "PASS" if guard_ok else "FAIL",
                "rule": "tree pixels: median saturation >= 0.12 and >= 70 % hue 50-170 deg, tree share > 2 %"}

# ----------------------------------------------------------------------------- flight
FL = V["flight"]
tag = "hf_flight_forest_%s_01" % REV
fdir = MOV / tag / "frames"
if fdir.is_dir():
    n = FL["frames"] + 1
    # calculated LOD per instance per frame (in-frustum) -> switch counts
    C = np.array([[it["x_m"], it["y_m"], it["z_m"] + it.get("crown_z_m", 7.1) * it["scale_z"]] for it in INST])
    R = np.array([it.get("sphere_r_m", MESH_SPHERE_R) * max(it["scale_x"], it["scale_y"], it["scale_z"]) for it in INST])
    prev, lod_counts, switches = None, [], []
    for k in FL["keys"]:
        cam = np.array(k["pos_local_m"])
        d = np.linalg.norm(C - cam, axis=1)
        ss = 3.08 * R / np.maximum(d, 1)
        lod = (ss[:, None] < np.array(LOD_CUTS)[None, :]).sum(1)
        pitch, bearing = k["ue_rot"][1], k["ue_rot"][2] + 90
        f = dir_from(bearing, pitch)
        r = np.cross(f, [0, 0, 1.0])
        r /= np.linalg.norm(r)
        u = np.cross(r, f)
        v = C - cam
        z = v @ f
        tx = math.tan(math.radians(HFOV / 2))
        vis = (z > -R) & (np.abs(v @ r) <= z * tx + 1.2 * R) & (np.abs(v @ u) <= z * tx / ASPECT + 1.2 * R)
        lod_counts.append([int(((lod == L) & vis).sum()) for L in range(4)])
        switches.append(int(((lod != prev) & vis).sum()) if prev is not None else 0)
        prev = lod
    diffs, tiles, last = [], [], None
    tmp = OUT / ("_ann_" + REV)
    tmp.mkdir(exist_ok=True)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    for fr in range(n):
        im = Image.open(fdir / ("frame_%04d.png" % fr)).convert("RGB")
        g = np.asarray(im.convert("L").resize((480, 270)), dtype=np.float32)
        if last is not None:
            ad = np.abs(g - last)
            diffs.append(float(ad[90:, :].mean()))
            tiles.append(ad.reshape(6, 45, 8, 60).mean(axis=(1, 3)).ravel())
        last = g
        dr = ImageDraw.Draw(im)
        k = FL["keys"][fr]
        lc = lod_counts[fr]
        txt = "frame %d  t=%.2fs  %d m/s  AGL %.0f m  calc. LOD0/1/2/3 in view: %d/%d/%d/%d  switches %d" % (
            fr, fr / 60.0, FL["speed_mps"], k["agl_m"], lc[0], lc[1], lc[2], lc[3], switches[fr])
        w = int(dr.textlength(txt, font=font)) + 16
        dr.rectangle((0, 1040, w, 1080), fill=(0, 0, 0))
        dr.text((8, 1048), txt, fill=(255, 255, 255), font=font)
        if any(switches[max(0, fr - 3):fr + 1][j] >= 3 for j in range(len(switches[max(0, fr - 3):fr + 1]))):
            dr.rectangle((0, 0, 1919, 8), fill=(220, 0, 0))
        im.save(tmp / ("a_%04d.jpg" % fr), quality=92)
    diffs = np.array([diffs[0]] + diffs)
    roll = np.array([np.median(diffs[max(0, i - 4):i + 5]) for i in range(len(diffs))])
    ratio = diffs / np.maximum(roll, 1e-6)
    spikes = [{"frame": int(i), "ratio": round(float(ratio[i]), 2), "calc_switches": switches[i]} for i in np.where(ratio > 1.5)[0]]
    # tile level (8 x 6 tiles of 60 x 45 px at 480 x 270): a few trees switching LOD change one tile, not the frame mean
    TL = np.array([tiles[0]] + tiles)
    troll = np.stack([np.median(TL[max(0, i - 4):i + 5], axis=0) for i in range(len(TL))])
    tr = TL / np.maximum(troll, 0.5)
    tile_hits = (tr > 2.0) & (TL > 2.0)  # > 2x the tile's own rolling median and > 2 grey levels
    hit_frames = np.where(tile_hits.any(1))[0]
    sw_arr = np.array(switches)
    near_sw = [int(f) for f in hit_frames if sw_arr[max(0, f - 1):f + 2].sum() > 0]
    rate_hit = len(near_sw) / max(len(hit_frames), 1)
    base_rate = float((np.convolve((sw_arr > 0).astype(float), np.ones(3), mode="same") > 0).mean())
    tile_proxy = {"rule": "tile |frame - prev| > 2 x its rolling median(9) and > 2 grey levels; 8 x 6 tiles at 480 x 270",
                  "frames_with_tile_hit": [int(f) for f in hit_frames], "n_frames_with_tile_hit": int(len(hit_frames)),
                  "share_within_1_frame_of_a_calc_switch": round(rate_hit, 3),
                  "chance_share_of_frames_within_1_frame_of_a_calc_switch": round(base_rate, 3)}
    ff = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", "60"]
    enc = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "slow"]
    subprocess.run(ff + ["-i", str(fdir / "frame_%04d.png")] + enc + [str(OUT / ("fly_%s.mp4" % REV))], check=True)
    subprocess.run(ff + ["-i", str(tmp / "a_%04d.jpg")] + enc + [str(OUT / ("fly_%s_annotated.mp4" % REV))], check=True)
    for p in tmp.iterdir():
        p.unlink()
    tmp.rmdir()
    sw = np.array(switches)
    rep["flight"] = {"frames": n, "speed_mps": FL["speed_mps"], "length_m": FL["length_m"], "agl_range_m": FL["agl_range_m"],
                     "lod_calc_in_view_frame0": lod_counts[0], "lod_calc_in_view_mid": lod_counts[n // 2], "lod_calc_in_view_last": lod_counts[-1],
                     "lod_calc_in_view_mean": [round(float(np.mean([c[L] for c in lod_counts])), 1) for L in range(4)],
                     "calc_switches_total": int(sw.sum()), "frames_with_ge3_switches": int((sw >= 3).sum()),
                     "pop_proxy": {"rule": "mean |frame - prev| (lower 2/3, 480x270 grey) / rolling median(9) > 1.5",
                                   "spikes": spikes, "n_spikes": len(spikes), "median_diff": round(float(np.median(diffs)), 3)},
                     "pop_proxy_tiles": tile_proxy}
    (OUT / "flight_lod_calc.json").write_text(json.dumps({"lod_counts": lod_counts, "switches": switches, "diff": [round(float(x), 4) for x in diffs]}) + "\n")
(OUT / "frames_report.json").write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in rep.items() if k != "flight"}, indent=1))
print(json.dumps({k: v for k, v in rep.get("flight", {}).items() if k != "pop_proxy"}, indent=1))
if rep.get("flight"):
    print("pop spikes:", rep["flight"]["pop_proxy"]["n_spikes"], rep["flight"]["pop_proxy"]["spikes"][:20])
    print("tile proxy:", json.dumps(rep["flight"]["pop_proxy_tiles"]))
sys.exit(0 if guard_ok else 3)
