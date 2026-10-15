"""First-order check: does masked-card FRAGMENT count (not triangles) track the measured GPU delta? (calculated + measured, stdlib only)
python tools/treegen/budget_fragment_model.py <evidence_dir>
fragments(tree) = card_fragments_total(LOD, camera sl150 reference from card_overdraw.py) * (150 / d)^2 * scale^2   [card footprint ~ 1/d^2, layers constant]
LOD choice per tree as in budget_patch_lods.py. Fragments are the offline rasteriser's worst case (no early-Z), branches excluded."""
import json, math, random, sys, os
E = sys.argv[1]
ov = {p: json.load(open(os.path.join(E, "overdraw_%s.json" % p)))["results"] for p in ("v1", "budget", "balanced")}
views = {v["name"]: v for v in json.load(open(os.path.join(E, "views_budget.json")))["views"]}
perf = json.load(open(os.path.join(E, "budget_perf_q1.json")))["candidate_minus_empty"]
frag = lambda prof, lod: ov[prof]["sl150/lod%d" % lod]["card_fragments_total"]  # noqa: E731
chain = {"A": ("v1", 3, (0.5, 0.15)), "B": ("budget", 3, (0.5, 0.15)), "C": ("budget", 4, (0.5, 0.15, 0.06)), "D": ("balanced", 4, (0.5, 0.15, 0.06))}
rng = random.Random(20261015)
tr = [(0.0, 0.0, 1.0)]
for i in range(-5, 5):
    for j in range(-5, 5):
        if i == 0 and j == 0:
            continue
        x, y = 25.0 * i + rng.uniform(-4, 4), 25.0 * j + rng.uniform(-4, 4)
        s = rng.uniform(0.85, 1.15); rng.uniform(0, 360)
        tr.append((x, y, s))
audit = json.load(open(os.path.join(E, "mesh_audit.json")))
print("| view | cand | masked fragments (M) | triangles submitted (M) | measured GPU delta (ms) | ms per M fragments | ms per M triangles |")
print("|---|---|---:|---:|---:|---:|---:|")
for view in ("sl150", "sl300", "sl500", "sl1000"):
    L = views[view]["loc"]
    for c, (prof, nl, cuts) in chain.items():
        tot = 0.0
        tt = 0
        for x, y, s in tr:
            d = math.dist(L, (x, y, 6.0))
            lod = sum(3.08 * 8.377 * s / d < k for k in cuts)
            tt += audit[c]["tris"][lod]
            tot += frag(prof, lod) * (150.0 / d) ** 2 * s * s
        g = perf["%s/patch/%s" % (view, c)]["agg"]["GPUTime"]["mean"]
        print("| %s | %s | %.2f | %.2f | %+.2f | %.2f | %.1f |" % (view, c, tot / 1e6, tt / 1e6, g, g / (tot / 1e6), g / (tt / 1e6)))
