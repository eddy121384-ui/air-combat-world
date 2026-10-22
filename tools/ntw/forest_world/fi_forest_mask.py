"""Far-LOD research v2: export the Landscape's forest-cover mask (T_NF_Mask1 R, build_region.py: land-cover class "trees") as raw bytes
for fi_build.py. A tree whose ground is not painted as forest by the Landscape (farmland, grassland, town) gets no far impostor: its
true-size impostor fades out with the 3D range, so open land stays the terrain's colour at distance (docs section 10).
Output: <out>/fi_forest_mask.bin (uint8, row 0 = north = UE Y -4,000,000 cm) + fi_forest_mask.json.
    python tools/ntw/forest_world/fi_forest_mask.py <run_dir> <out_dir>
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def main(run, out):
    run, out = Path(run), Path(out)
    t = json.loads((run / "terrain.json").read_text(encoding="utf-8"))
    m = np.asarray(Image.open(run / "T_NF_Mask1.png"))[..., 0]
    x0, y0 = t["landscape"]["location_cm"][:2]
    ext_cm = (t["bbox_3826"][2] - t["bbox_3826"][0]) * 100.0
    (out / "fi_forest_mask.bin").write_bytes(m.astype(np.uint8).tobytes())
    meta = {"size": list(m.shape), "origin_cm": [x0, y0], "extent_cm": ext_cm, "source": "T_NF_Mask1.png R (land cover: trees)",
            "forest_fraction_gt_half": float((m > 127).mean())}
    (out / "fi_forest_mask.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(meta))


if __name__ == "__main__":
    main(*sys.argv[1:])
