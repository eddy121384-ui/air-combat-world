"""Annotate the project's own UE5.8 look-dev capture for the AC7 forest benchmark doc (no third-party pixels)."""
import hashlib
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

src, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)
im = Image.open(src).convert("RGB")
assert im.size == (1920, 1080), im.size
print("source sha256", hashlib.sha256(src.read_bytes()).hexdigest(), im.size)

try:
    font = ImageFont.truetype("arialbd.ttf", 30)
    small = ImageFont.truetype("arial.ttf", 22)
except OSError:
    font = small = ImageFont.load_default()

# full frame annotated at native coordinates, then reduced to 50 %
ann = im.copy()
d = ImageDraw.Draw(ann)
marks = [  # (x, y, label) in native 1920x1080 px
    (700, 880, "1"),   # hard coverage boundary: clumps stop at the Xinyi build bbox
    (330, 560, "2"),   # bare Landscape slope: smooth 'felt' hill with no canopy grain
    (240, 900, "3"),   # clump field: dark crown speckle + light ground through gaps
    (1150, 445, "4"),  # far ridges: flat green, no canopy texture, no ridge/valley value split
    (1500, 650, "5"),  # canopy-free hill reaches straight into the city fringe
]
for x, y, t in marks:
    d.ellipse([x - 26, y - 26, x + 26, y + 26], outline=(255, 214, 0), width=5)
    d.text((x - 9, y - 18), t, fill=(255, 214, 0), font=font)
d.rectangle([0, 720, 640, 1079], outline=(0, 220, 255), width=4)
d.text((10, 684), "native crop", fill=(0, 220, 255), font=small)
half = ann.resize((960, 540), Image.LANCZOS)
half.save(out_dir / "baseline_ue58_hillside_annotated_50pct.jpg", quality=86, optimize=True)

# unchanged native-pixel crop of the forest clump field (no resize, no annotation)
crop = im.crop((0, 720, 640, 1080))
crop.save(out_dir / "baseline_ue58_hillside_native_crop.png", optimize=True)
for p in sorted(q for q in out_dir.iterdir() if q.is_file()):
    print(p.name, p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest())
