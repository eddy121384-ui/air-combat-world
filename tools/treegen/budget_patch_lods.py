"""Expected LOD mix of the 10x10 same-tree patch per camera (calculated, not read from the engine).
python tools/treegen/budget_patch_lods.py <views_budget.json> -- screen = 3.08 * R / d (PR #30 convention), R = 8.377 m * instance scale,
thresholds of candidate A/B: 0.5 / 0.15 ; C/D add 0.06. Same RNG sequence as adapters/unreal/treelookdev/tl_budget_common.patch_transforms()."""
import json, math, random, sys
V = {v["name"]: v for v in json.load(open(sys.argv[1]))["views"]}
rng = random.Random(20261015)
tr = [(0.0, 0.0, 1.0)]
for i in range(-5, 5):
    for j in range(-5, 5):
        if i == 0 and j == 0:
            continue
        x, y = 25.0 * i + rng.uniform(-4, 4), 25.0 * j + rng.uniform(-4, 4)
        s = rng.uniform(0.85, 1.15)
        rng.uniform(0, 360)
        tr.append((x, y, s))
for name in ("sl150", "sl300", "sl500", "sl1000"):
    L = V[name]["loc"]
    for label, cuts in (("A/B", (0.5, 0.15)), ("C/D", (0.5, 0.15, 0.06))):
        cnt = [0] * (len(cuts) + 1)
        for x, y, s in tr:
            d = math.dist(L, (x, y, 6.0))
            sc = 3.08 * 8.377 * s / d
            lod = sum(sc < c for c in cuts)
            cnt[lod] += 1
        print(name, label, "LOD counts", cnt)
