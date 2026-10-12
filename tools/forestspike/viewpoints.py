"""ForestSpike B0 pre-registered viewpoints (absolute ENU poses derived from the analytic terrain).

  python tools/forestspike/viewpoints.py     -> tools/forestspike/viewpoints.json

All poses are fixed here BEFORE any d_S / transition-width decision is made; the B0 gate analyses them as they are.
Camera: 1920 x 1080, 60 deg VERTICAL FOV (= 91.5 deg horizontal), heading = degrees clockwise from north,
pitch negative = looking down, roll 0. AGL = height above the terrain directly under the eye.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fs_world as w  # noqa: E402

FOV_V = 60.0
FOV_H = math.degrees(2.0 * math.atan(math.tan(math.radians(FOV_V) / 2.0) * 16.0 / 9.0))
HERE = Path(__file__).resolve().parent


def pose(pid, group, e, n, agl, heading, pitch, **extra):
    u = float(w.height(np.array([e]), np.array([n]))[0]) + agl
    d = {"id": pid, "group": group, "eye_enu": [round(e, 3), round(n, 3), round(u, 3)], "agl_m": agl,
         "heading_deg": heading, "pitch_deg": pitch, "fov_h_deg": round(FOV_H, 4), "fov_v_deg": FOV_V}
    d.update(extra)
    return d


def build():
    poses = []
    # V1: locked stills, camera at the south-west of the core looking north-east across it
    eye = (-420.0, -420.0)
    for agl, pitch in ((50, -5), (50, -15), (200, -10), (200, -25), (500, -15), (500, -35), (1000, -20), (1000, -45)):
        poses.append(pose("v1_agl%d_p%d" % (agl, -pitch), "V1", eye[0], eye[1], agl, 45.0, float(pitch)))
    # V3: slow dolly along the core diagonal at 200 m AGL (30 m/s -> 1,273 m in 42.4 s), sampled every 2 s
    for k in range(22):
        t = 2.0 * k
        s = -450.0 + 30.0 * t / math.sqrt(2.0)
        poses.append(pose("v3_t%02d" % int(t), "V3", s, s, 200, 45.0, -10.0, t_s=t, speed_mps=30.0))
    # V5: orbit radius 330 m around the core centre, clockwise, camera along the tangent, 12 azimuths each
    for agl, pitch in ((200, -10), (500, -25)):
        for k in range(12):
            az = 30.0 * k                                    # position azimuth from north, clockwise
            e = 330.0 * math.sin(math.radians(az))
            n = 330.0 * math.cos(math.radians(az))
            hdg = (az + 90.0) % 360.0                        # clockwise orbit: tangent heading
            poses.append(pose("v5_agl%d_a%03d" % (agl, int(az)), "V5", e, n, agl, hdg, float(pitch), orbit_az_deg=az,
                              speed_mps=150.0))
    # --- revision 1 (made after the first observability preflight: the registered V3 / V5 above looked mostly
    # outside the core, see docs). The first-pass poses stay in the table as group V3o / V5t for the record.
    for p in poses:
        if p["group"] == "V3":
            p["group"] = "V3o"
        if p["group"] == "V5":
            p["group"] = "V5t"
    # V3 (inbound): approach the core along the diagonal at 200 m AGL, 30 m/s, from 1,414 m out to the centre, so the
    # d_S ring sweeps the whole core forest as the range to it shrinks; sampled every 2 s
    for k in range(25):
        t = 2.0 * k
        s = -1000.0 + 30.0 * t / math.sqrt(2.0)
        poses.append(pose("v3i_t%02d" % int(t), "V3", s, s, 200, 45.0, -10.0, t_s=t, speed_mps=30.0))
    # V5 (inward orbit): radius 330 m, 150 m/s -> 26 deg/s yaw, camera looking at the core centre (same yaw rate as a
    # tangent-looking 7 g turn, but the core stays in view); 12 azimuths per altitude
    for agl, pitch in ((200, -25), (500, -45)):
        for k in range(12):
            az = 30.0 * k
            e = 330.0 * math.sin(math.radians(az))
            n = 330.0 * math.cos(math.radians(az))
            poses.append(pose("v5i_agl%d_a%03d" % (agl, int(az)), "V5", e, n, agl, (az + 180.0) % 360.0, float(pitch),
                              orbit_az_deg=az, speed_mps=150.0))
    return poses


def main():
    poses = build()
    out = {"schema": "forestspike.viewpoints/0", "terrain_seed": w.SEED, "resolution": [1920, 1080],
           "fov_v_deg": FOV_V, "fov_h_deg": round(FOV_H, 4), "poses": poses}
    (HERE / "viewpoints.json").write_text(json.dumps(out, indent=1) + "\n")
    print(len(poses), "poses;", sorted({p["group"] for p in poses}))


if __name__ == "__main__":
    main()
