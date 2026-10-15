"""Camera flight paths for the moving-camera visual gate (research/forest-tree-lod-budget-v1, stdlib + numpy).

python tools/treegen/flight_paths.py <out.json>

UE units: cm, X east, Y = -north, Z up; the 100-tree patch is centred on the origin (ground z = 0, trees 8-14 m tall, patch +-125 m).
Approach bearing = the PR #30 agl50 / slant cameras (eye south-south-east of the tree): ub = (0.2747, 0.9615) in UE xy.
60 fps fixed step; every path starts with HOLD frames at the first pose (warm-up, shared stationary segment), then flies at constant speed.
All keys are LINEAR in the Level Sequence, so the per-frame camera pose is the linear interpolation of the keys (flight_analyze.py recomputes it).

  P1_250  level inbound: AGL 120 m, pitch -12 deg, 900 m -> -300 m along the bearing (over the patch centre), 250 m/s   (crosses ~430 m and ~175 m slant)
  P2_250  dive onto the patch centre: (800 m, 300 m AGL) -> (100 m, 37.5 m AGL), nose on the line to the centre (pitch -20.6 deg), 250 m/s
  P2_100  same line at 100 m/s (slow: easier to see temporal artefacts)
  P3_250  lateral pass at 400 m offset, AGL 150 m (slant at closest approach 427 m = the LOD2/LOD3 boundary of the far-LOD candidates),
          along-track -600 m -> +600 m at 250 m/s, always looking at the patch centre (0, 0, 6 m)
Slant distance in the analysis = camera to the patch-centre tree centre (z = 6 m), as in the still-image experiment.
"""
import json
import math
import sys

import numpy as np

FPS, HOLD, TAIL = 60, 90, 30
UB = np.array([40.0, 140.0]) / math.hypot(40.0, 140.0)  # patch -> approach start (UE xy)
F = -UB                                                  # flight direction (inbound)
L = np.array([-UB[1], UB[0]])                            # lateral (left of the flight direction when facing F is -L; sign irrelevant here)
YAW_F = math.degrees(math.atan2(F[1], F[0]))


def keys_line(p0, p1, pitch, yaw, speed):
    """Hold at p0 for HOLD frames, then linear flight to p1 at `speed` m/s, then TAIL frames at p1. Positions in metres (x, y, z)."""
    n = int(round(np.linalg.norm(np.array(p1) - np.array(p0)) / speed * FPS))
    mk = lambda f, p: dict(frame=f, pos_m=[float(v) for v in p], rot=[0.0, pitch, yaw])  # noqa: E731
    return [mk(0, p0), mk(HOLD, p0), mk(HOLD + n, p1), mk(HOLD + n + TAIL, p1)], HOLD, HOLD + n


def build():
    paths = {}
    # P1 level inbound
    p0 = (*(UB * 900.0), 120.0)
    p1 = (*(UB * -300.0), 120.0)
    k, a, b = keys_line(p0, p1, -12.0, YAW_F, 250.0)
    paths["P1_250"] = dict(keys=k, flight_start=a, flight_end=b, speed_mps=250.0, desc="level inbound AGL 120 m, pitch -12")
    # P2 dive
    h0, d0, h1, d1 = 300.0, 800.0, 37.5, 100.0
    pitch = -math.degrees(math.atan2(h0, d0))
    p0 = (*(UB * d0), h0)
    p1 = (*(UB * d1), h1)
    for pid, sp in (("P2_250", 250.0), ("P2_100", 100.0)):
        k, a, b = keys_line(p0, p1, pitch, YAW_F, sp)
        paths[pid] = dict(keys=k, flight_start=a, flight_end=b, speed_mps=sp, desc="dive onto patch centre, pitch %.1f" % pitch)
    # P3 lateral, looking at the patch centre
    along = np.arange(-600.0, 600.0 + 1e-6, 250.0 / FPS * 4)  # one key every 4 frames
    pos = [(*(F * s + L * 400.0), 150.0) for s in along]
    tgt = np.array([0.0, 0.0, 6.0])
    yaws, pitches = [], []
    for p in pos:
        d = tgt - np.array(p)
        yaws.append(math.degrees(math.atan2(d[1], d[0])))
        pitches.append(math.degrees(math.atan2(d[2], math.hypot(d[0], d[1]))))
    yaws = np.degrees(np.unwrap(np.radians(yaws)))
    keys = [dict(frame=0, pos_m=list(map(float, pos[0])), rot=[0.0, pitches[0], float(yaws[0])])]
    for i, (p, pt, yw) in enumerate(zip(pos, pitches, yaws)):
        keys.append(dict(frame=HOLD + i * 4, pos_m=list(map(float, p)), rot=[0.0, pt, float(yw)]))
    end = HOLD + (len(pos) - 1) * 4
    keys.append(dict(frame=end + TAIL, pos_m=list(map(float, pos[-1])), rot=[0.0, pitches[-1], float(yaws[-1])]))
    paths["P3_250"] = dict(keys=keys, flight_start=HOLD, flight_end=end, speed_mps=250.0, desc="lateral pass 400 m offset, AGL 150 m, look-at patch centre")
    return dict(fps=FPS, hold_frames=HOLD, tail_frames=TAIL, hfov_deg=60.0, res=[1920, 1080], units="positions in metres (UE x east, y = -north, z up); rotation (roll, pitch, yaw) degrees",
                bearing_ue_xy=[float(UB[0]), float(UB[1])], paths=paths)


if __name__ == "__main__":
    out = build()
    json.dump(out, open(sys.argv[1], "w"), indent=1)
    for k, v in out["paths"].items():
        print(k, "flight frames %d..%d (%.1f s), sequence end %d" % (v["flight_start"], v["flight_end"], (v["flight_end"] - v["flight_start"]) / FPS, v["keys"][-1]["frame"]))
