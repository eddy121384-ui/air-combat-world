"""Extract only the two packed PNGs and provenance after a real baseline passes."""
import hashlib
import io
import json
from pathlib import Path
import subprocess

from PIL import Image
import numpy as np

REPO = Path(__file__).resolve().parents[2]
SHA = 'b0e00f2256bfe67ba76798d73450fa3c5412930f'
PREFIX = 'assets/materials/xinyi/shared_masks/v1/'
baseline = json.loads((REPO / 'unreal/Saved/XinyiLook/unreal/look_capture.report.json').read_text())
if baseline.get('status') != 'PASS_LOOK_CAPTURE' or not baseline.get('reopen_ok'):
    raise RuntimeError('A genuine UE baseline must pass before extracting PR #62')
if not baseline.get('captures'):
    raise RuntimeError('No baseline screenshot')
for cap in baseline['captures']:
    if not Path(cap['path']).read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
        raise RuntimeError('Invalid UE screenshot')

def blob(relative):
    return subprocess.run(['git', '-c', f'safe.directory={REPO.as_posix()}', 'show', f'{SHA}:{PREFIX}{relative}'],
                          cwd=REPO, check=True, stdout=subprocess.PIPE).stdout

manifest = blob('manifest.json')
target = REPO / 'assets/materials/xinyi/ue58_round1'
target.mkdir(parents=True, exist_ok=True)
records = []
for name in ('T_XinyiFacadeAge', 'T_XinyiRoofSurface'):
    source_path = f'textures/{name}.png'
    raw = blob(source_path)
    sha = hashlib.sha256(raw).hexdigest()
    if sha not in manifest.decode('utf-8'):
        raise RuntimeError('PNG hash absent from PR manifest: ' + name)
    with Image.open(io.BytesIO(raw)) as im:
        if im.mode != 'RGBA' or im.size != (512, 512) or raw[24:26] != bytes([8, 6]):
            raise RuntimeError('Expected RGBA8 512x512 PNG: ' + name)
        a = np.array(im)
    if any(np.ptp(a[..., ch]) == 0 for ch in range(4)):
        raise RuntimeError('Lost or constant data channel: ' + name)
    (target / f'{name}.png').write_bytes(raw)
    records.append({'name': name, 'sha256': sha, 'source_path': PREFIX + source_path,
                    'mode': 'RGBA8', 'size': [512, 512],
                    'channel_min': a.min(axis=(0, 1)).tolist(), 'channel_max': a.max(axis=(0, 1)).tolist(),
                    'channel_mean': a.mean(axis=(0, 1)).tolist()})
(target / 'PR62_SOURCES.md').write_bytes(blob('SOURCES.md'))
doc = {'source_pr': 62, 'source_commit': SHA, 'source_base_pr': 14,
       'source_base_commit': '6c2feb1611a3d07436c8222c3b67246a9b1ad8cd',
       'scene_base_commit': 'ede7960d8ec05b2aa521b1e4c65b5bbd667c456d',
       'source_manifest_sha256': hashlib.sha256(manifest).hexdigest(),
       'source_manifest_url': f'https://github.com/eddy121384-ui/air-combat-world/blob/{SHA}/{PREFIX}manifest.json',
       'scope': 'Two packed PNGs and provenance only; no PR merge or unrelated changes.', 'textures': records}
(target / 'source.json').write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
print('Extracted 2 RGBA8 textures; all four data channels retained and manifest hashes verified.')
