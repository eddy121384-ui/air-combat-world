"""Phase A numeric support for docs/research/ac7-forest-visual-benchmark-v0.md (analysis only)."""
import math
import numpy as np

V_FOV = math.radians(60.0)
H_PX = 1080
F_PX = (H_PX / 2) / math.tan(V_FOV / 2)
print("focal px", round(F_PX, 1))

# ---- 1. existing Xinyi hill-forest clump canopy coverage (replicates build_ground.write_forest_clump crowns) ----
def clump_crowns():
    rng = np.random.default_rng(11)
    out = []
    for k in range(5):
        a = 2 * math.pi * k / 5 + rng.uniform(-0.3, 0.3)
        r = 0.0 if k == 0 else rng.uniform(4.0, 6.5)
        c = np.array([math.cos(a) * r, rng.uniform(5.5, 8.5), math.sin(a) * r])
        sc = np.array([rng.uniform(3.2, 4.4), rng.uniform(2.6, 3.6), rng.uniform(3.2, 4.4)])
        rng.uniform(-0.15, 0.15, (12, 1))      # vertex jitter draw (keeps stream aligned; ignored for ellipse approx)
        out.append((c[0], c[2], sc[0], sc[2]))  # x, z centre, x/z radii (unit icosahedron circumradius 1)
    return out

crowns = clump_crowns()
rng = np.random.default_rng(3)
area = 400.0  # 400 m x 400 m sample of the 16 m jittered grid
res = 0.25
xs = np.arange(0, area, res) + res / 2
X, Y = np.meshgrid(xs, xs)
cov = np.zeros_like(X, bool)
n = 0
for gy in np.arange(8, area, 16.0):
    for gx in np.arange(8, area, 16.0):
        cx, cy = gx + rng.uniform(-5, 5), gy + rng.uniform(-5, 5)
        s = rng.uniform(0.9, 1.35)
        yaw = math.radians(rng.uniform(0, 360))
        ca, sa = math.cos(yaw), math.sin(yaw)
        n += 1
        for (x, z, rx, rz) in crowns:
            px, pz = (x * ca - z * sa) * s + cx, (x * sa + z * ca) * s + cy
            # icosahedron horizontal silhouette ~ inscribed between 0.79 and 1.0 of circumradius; use 0.9
            R = max(rx, rz) * s
            i0, i1 = max(0, int((pz - R) / res)), min(len(xs), int((pz + R) / res) + 2)
            j0, j1 = max(0, int((px - R) / res)), min(len(xs), int((px + R) / res) + 2)
            sx, sy = X[i0:i1, j0:j1], Y[i0:i1, j0:j1]
            m = (((sx - px) / (rx * s * 0.9)) ** 2 + ((sy - pz) / (rz * s * 0.9)) ** 2) <= 1.0
            cov[i0:i1, j0:j1] |= m
print("clumps", n, "per ha", round(n / (area * area / 1e4), 1), "crowns/ha", round(5 * n / (area * area / 1e4), 1))
print("MODEL ESTIMATE (geometric ellipse projection, 0.9 x circumradius, 400 m x 400 m sample of the placement rule;"
      " NOT pixel-measured, NOT the whole Xinyi forest, NOT GIS-validated): top-down canopy cover %.1f %%"
      % (100 * cov[80:-80, 80:-80].mean()))

# ---- 2. coverage vs instance density for random (Poisson) and for jittered grid ----
print("\nPoisson canopy cover 1-exp(-N*A): N per km2 for target cover")
for d in (6, 8, 10, 12):
    A = math.pi * (d / 2) ** 2
    row = []
    for c in (0.4, 0.7, 0.9):
        N = -math.log(1 - c) / A * 1e6
        row.append("%.0f%%:%dk" % (c * 100, round(N / 1000)))
    cov_at = {k: 100 * (1 - math.exp(-k * 1000 / 1e6 * A)) for k in (2, 5, 10, 20)}
    print("crown %2d m (A=%5.1f m2)" % (d, A), row, " cover at 2k/5k/10k/20k per km2:",
          ["%.0f" % v for v in cov_at.values()])

# ---- 3. pixel footprint at distance ----
print("\nm per px at 1080p/60 vFOV (fronto-parallel); crown px for 8 m / 12 m crowns")
for dist in (50, 150, 300, 600, 1000, 2000, 4000, 8000):
    mpp = dist / F_PX
    print("%5d m  %.3f m/px  8m crown %.1f px  12m crown %.1f px" % (dist, mpp, 8 / mpp, 12 / mpp))

# ---- 4. screen share of each distance band on flat ground ----
bands = [(0, 150, "near"), (150, 600, "mid"), (600, 2000, "far"), (2000, 1e9, "theater")]
print("\nshare of GROUND rows per slant-range band, flat ground, 1080 rows, horizon visible when pitch shallow")
for h, pitch in ((50, 5), (50, 15), (200, 10), (200, 25), (500, 15), (500, 35), (1000, 20), (1000, 45)):
    shares = {b[2]: 0 for b in bands}
    sky = 0
    gaze = []
    for row in range(H_PX):
        yoff = (row + 0.5 - H_PX / 2)                     # +down
        ang = math.radians(pitch) + math.atan(yoff / F_PX)  # angle below horizon
        if ang <= 0:
            sky += 1
            continue
        r = h / math.sin(ang)
        for lo, hi, name in bands:
            if lo <= r < hi:
                shares[name] += 1
        gaze.append(math.degrees(ang))
    centre_r = h / math.sin(math.radians(pitch))
    print("h=%4d pitch=-%2d  centre slant %5.0f m  sky %4.1f%%  " % (h, pitch, centre_r, 100 * sky / H_PX) +
          "  ".join("%s %4.1f%%" % (k, 100 * v / H_PX) for k, v in shares.items()) +
          "  grazing range %.0f-%.0f deg" % (min(gaze), max(gaze)))

# ---- 5. gap visibility: fraction of ground visible between crowns vs grazing angle (cylinder-crown model) ----
print("\nprobability a ray reaches ground (Poisson crowns, cylinder canopy layer of depth D) vs grazing angle")
for d, N_km2, D in ((8, 10000, 6.0), (8, 20000, 6.0), (10, 10000, 7.0)):
    A = math.pi * (d / 2) ** 2
    lam = N_km2 / 1e6
    out = []
    for g in (90, 45, 30, 15, 8):
        # projected crown shadow area on ground for a cylinder of radius r height D at grazing angle g
        r = d / 2
        proj = A + 2 * r * D / math.tan(math.radians(g))
        out.append("%2d deg %.0f%%" % (g, 100 * math.exp(-lam * proj)))
    print("crown %dm  %dk/km2  layer %.0fm  ground seen:" % (d, N_km2 // 1000, D), ", ".join(out))

# ---- 6. image-plane speed at high-speed flight ----
print("\nimage-plane speed px/frame @60fps for ground point, aircraft speed v, slant r, angle off velocity a")
for v in (250, 400):
    for r, a in ((150, 20), (300, 15), (600, 10), (1500, 10), (3000, 5)):
        w = v * math.sin(math.radians(a)) / r
        print("v=%d m/s  r=%5d m  off-axis %2d deg  %.1f px/frame" % (v, r, a, F_PX * w / 60.0))

# ---- 7. Phase B sizing: B1 in-core segments, turn radii / yaw rates, B2 corridor ----
G = 9.81
H_FOV = 2 * math.atan(math.tan(V_FOV / 2) * 16 / 9)
print("\nhorizontal FOV at 16:9: %.1f deg" % math.degrees(H_FOV))
diag, margin = 1000 * math.sqrt(2), 300.0
print("B1 straight segment inside 1 km core along the diagonal (%.0f m) with %.0f m margin each end:" % (diag, margin))
for v in (60, 120, 250, 400):
    print("  v=%3d m/s  max %.1f s" % (v, (diag - 2 * margin) / v))
print("level turn radius r = v^2 / (g sqrt(n^2-1)), yaw rate v/r, whole-frame image speed f*w/60:")
for v, n in ((250, 9), (250, 6), (150, 7), (120, 5), (80, 4)):
    r = v * v / (G * math.sqrt(n * n - 1))
    w = v / r
    print("  v=%3d m/s n=%dg  r=%5.0f m  yaw %.2f rad/s (%.0f deg/s)  %.1f px/frame  fits 1 km core (r<=400 m): %s"
          % (v, n, r, w, math.degrees(w), F_PX * w / 60, r <= 400))
print("B2 corridor: length >= v*T + 2*600 m; width for mid band (600 m) when level = 2*600*tan(hFOV/2)")
for v, T in ((250, 20), (400, 20), (400, 15)):
    print("  v=%d m/s T=%d s  length >= %.1f km" % (v, T, (v * T + 1200) / 1000))
print("  width >= %.2f km (level); add bank margin" % (2 * 600 * math.tan(H_FOV / 2) / 1000))
