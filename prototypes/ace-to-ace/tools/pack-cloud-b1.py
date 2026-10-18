"""Downsample the original B1 generated atlas; no painting or R2 files are changed."""
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parents[1] / 'assets' / 'cloud-b1'
image = Image.open(root / 'source' / 'cloud-materials-b1.png').convert('RGB')
# Mirror padding inside each tile prevents neighbouring views bleeding at mip levels.
atlas = Image.new('RGB', (1024, 1024))
for i in range(4):
    x, y = i % 2, i // 2
    tile = image.crop((x*image.width//2,y*image.height//2,(x+1)*image.width//2,(y+1)*image.height//2))
    tile = tile.resize((496,496), Image.Resampling.LANCZOS)
    atlas.paste(tile,(x*512+8,y*512+8))
    atlas.paste(tile.crop((0,0,1,496)).resize((8,496)),(x*512,y*512+8))
    atlas.paste(tile.crop((495,0,496,496)).resize((8,496)),(x*512+504,y*512+8))
    atlas.paste(atlas.crop((x*512,y*512+8,x*512+512,y*512+9)).resize((512,8)),(x*512,y*512))
    atlas.paste(atlas.crop((x*512,y*512+503,x*512+512,y*512+504)).resize((512,8)),(x*512,y*512+504))
atlas.save(root/'cloud-materials-b1.webp',quality=91,method=6)
print(f'Original: {image.size}; runtime: {atlas.size}; WebP bytes: {(root/"cloud-materials-b1.webp").stat().st_size}')

source=Image.open(root/'source'/'cloud-silhouettes-b1.png').convert('RGBA')
atlas=Image.new('RGBA',(1024,1024))
for i in range(4):
    x,y=i%2,i//2
    tile=source.crop((x*source.width//2,y*source.height//2,(x+1)*source.width//2,(y+1)*source.height//2)).resize((496,496),Image.Resampling.LANCZOS)
    # Technical guard bands prevent touching source wisps from bleeding into other views.
    alpha=tile.getchannel('A'); data=alpha.load()
    for py in range(496):
        for px in range(496):
            edge=min(px,py,495-px,495-py)
            data[px,py]=round(data[px,py]*min(1,edge/40))
    tile.putalpha(alpha)
    padded=Image.new('RGBA',(512,512));padded.paste(tile,(8,8));atlas.paste(padded,(x*512,y*512))
atlas.save(root/'cloud-silhouettes-b1.webp',quality=92,method=6,exact=True)
print(f'Silhouette WebP: {(root/"cloud-silhouettes-b1.webp").stat().st_size}')
