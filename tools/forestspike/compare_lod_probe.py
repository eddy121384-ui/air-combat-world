"""Compare auto and forced-LOD diagnostic frames at native pixels."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from perf_integrity import sha256

ap = argparse.ArgumentParser()
ap.add_argument("--captures", type=Path, required=True)
ap.add_argument("--out", type=Path, required=True)
a = ap.parse_args()
rows = []
for p in sorted(a.captures.glob("*_lod-1.png")):
    auto = np.asarray(Image.open(p).convert("RGB"))
    row = {"pose": p.name.removeprefix("probe_").removesuffix("_lod-1.png"), "resolution": [auto.shape[1], auto.shape[0]],
           "automatic": {"file": p.name, "sha256": sha256(p)}, "forced_comparisons": []}
    for lod in range(3):
        q = p.with_name(p.name.replace("_lod-1", "_lod%d" % lod))
        forced = np.asarray(Image.open(q).convert("RGB"))
        diff = np.abs(auto.astype(int) - forced.astype(int))
        auto_range = (auto[..., 1].astype(int) * 256 + auto[..., 2]) / 7
        near = (auto[..., 0] == 240) & (auto_range <= 350)
        row["forced_comparisons"].append({"lod": lod, "file": q.name, "sha256": sha256(q),
                                           "different_pixels": int(np.any(diff, axis=2).sum()),
                                           "automatic_tree_pixels_le350m": int(near.sum()),
                                           "different_auto_tree_pixels_le350m": int((np.any(diff, axis=2) & near).sum()),
                                           "total_pixels": int(diff.shape[0] * diff.shape[1]), "max_channel_error": int(diff.max())})
    rows.append(row)
    print(row["pose"], [(c["lod"], c["different_pixels"], c["automatic_tree_pixels_le350m"], c["different_auto_tree_pixels_le350m"]) for c in row["forced_comparisons"]])
with a.out.open("x", encoding="utf-8") as fh:
    json.dump({"scope": "transient ID-render diagnostic; forced LOD bypasses normal cluster culling, so full-frame equality is invalid; compare automatic tree pixels <=350m, within 500m cull. Not performance/final visual acceptance",
               "expected_policy": "No approved B1a LOD screen-size/distance policy exists; original B0 B defaults must not imply near LOD0",
               "rows": rows}, fh, indent=2)
