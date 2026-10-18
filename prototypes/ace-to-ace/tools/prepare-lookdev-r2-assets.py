"""Pack the committed original ImageGen paintings for the web runtime (Pillow/NumPy).

No network/API needed. Does not regenerate or substitute the painted artwork.
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'lookdev'
sky = Image.open(ROOT / 'source' / 'r2-sky.png').convert('RGB')
sky.resize((1536, 768), Image.Resampling.LANCZOS).save(
    ROOT / 'sky-painting-r2.jpg', quality=92, optimize=True, subsampling=0)

source = Image.open(ROOT / 'source' / 'r2-clouds.png').convert('RGBA')
# The generated formations have unequal gutters; record exact normalized crops
# instead of assuming that a horizontal line through the middle is empty.
boxes = [(0, .015, .550, .596), (.557, 0, 1, .665),
         (0, .597, .525, 1), (.526, .666, 1, 1)]
atlas = Image.new('RGBA', (1024, 512))
for i, box in enumerate(boxes):
    crop = source.crop(tuple(round(v * (source.width if j % 2 == 0 else source.height))
                             for j, v in enumerate(box)))
    a = np.array(crop)
    # Remove invisible chroma in near-zero-alpha texels before filtering. Fade
    # clipped crop borders into the gutter; preserve the original painted alpha.
    yy, xx = np.mgrid[:crop.height, :crop.width]
    edge = np.minimum.reduce([xx, yy, crop.width - 1 - xx, crop.height - 1 - yy])
    fade = np.clip(edge / 12.0, 0, 1)
    a[:, :, 3] = np.uint8(np.where(a[:, :, 3] < 4, 0, a[:, :, 3]) * fade)
    crop = Image.fromarray(a)
    crop.thumbnail((484, 228), Image.Resampling.LANCZOS)
    tile = Image.new('RGBA', (512, 256))
    tile.paste(crop, ((512 - crop.width) // 2, (256 - crop.height) // 2))
    # Remove the source's bright extraction fringe without changing its painting.
    alpha = tile.getchannel('A').filter(ImageFilter.MinFilter(5)).filter(ImageFilter.GaussianBlur(0.6))
    tile.putalpha(alpha)
    atlas.paste(tile, ((i % 2) * 512, (i // 2) * 256))
atlas.save(ROOT / 'cloud-paintings-r2.png', optimize=True)
for name in ['sky-painting-r2.jpg', 'cloud-paintings-r2.png']:
    print(f'{name}: {(ROOT / name).stat().st_size:,} bytes')
