"""Inspect actual consecutive WebGL frames; no interpolation or generated pixels.

Pillow is a development QA tool only. Global RGB change locates frames to inspect;
it is not a quality score, because physical parallax also changes many pixels.
"""
from pathlib import Path
import json
from PIL import Image, ImageChops, ImageStat

root = Path(__file__).resolve().parents[1]
raw = root / 'tools/out/cloud-animfix/final'
out = root / 'docs/cloud-engine-b1-animfix/motion'
out.mkdir(parents=True, exist_ok=True)
report = {}
for directory in sorted(p for p in raw.iterdir() if p.is_dir()):
    files = sorted(directory.glob('frame-*.jpg'))
    if not files:
        continue
    previous, differences = None, []
    for path in files:
        with Image.open(path) as source:
            small = source.convert('RGB').resize((64, 36))
        if previous is not None:
            differences.append(sum(ImageStat.Stat(ImageChops.difference(small, previous)).mean) / (3 * 255))
        previous = small
    peak = max(range(len(differences)), key=differences.__getitem__) + 1
    report[directory.name] = {'frames': len(files), 'maxGlobalRgbDelta': max(differences),
                             'peakFrame': peak, 'frameDifferences': differences}
    selections = {'dense': [round((len(files)-1)*i/15) for i in range(16)]}
    if directory.name.split('-stable')[0].split('-anime')[0] in ['approach', 'side-pass', 'entry', 'turn180']:
        start = max(0, min(len(files)-6, peak-3))
        selections['peak'] = list(range(start, start+6))
    for name, indices in selections.items():
        columns, width, height = (4, 320, 180) if name == 'dense' else (3, 426, 240)
        sheet = Image.new('RGB', (columns*width, ((len(indices)+columns-1)//columns)*height))
        for i, index in enumerate(indices):
            with Image.open(files[index]) as image:
                sheet.paste(image.resize((width, height)), ((i%columns)*width, (i//columns)*height))
        sheet.save(out / f'{directory.name}-{name}.jpg', quality=90)
(out / 'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print(json.dumps({key: {k: v for k, v in value.items() if k != 'frameDifferences'} for key, value in report.items()}, indent=2))
