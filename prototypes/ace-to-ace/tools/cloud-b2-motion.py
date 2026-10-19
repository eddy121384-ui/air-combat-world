"""Inspect every actual runtime JPEG; delta is a locator, never an art score."""
import json
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
root = Path(__file__).resolve().parents[1]
round_name = sys.argv[1] if len(sys.argv)>1 else 'final'
raw = root / f'tools/out/cloud-b2/{round_name}'
out = root / ('docs/cloud-engine-b2/motion' if round_name=='final' else f'docs/cloud-engine-b2/motion-{round_name}')
out.mkdir(parents=True, exist_ok=True)
source = json.loads((root / f'docs/cloud-engine-b2/{round_name}/report.json').read_text())
report = {'frames': 0, 'series': {}, 'method': '64x36 RGB average adjacent absolute delta; locate changes, not a quality metric'}
for scene, modes in source['scenes'].items():
    rows = []
    peak_rows = []
    for mode, series in modes.items():
        files = sorted((raw / f'{scene}-{mode}').glob('frame-*.jpg'))
        assert len(files) == source['frames']
        previous = None
        deltas = []
        for file in files:
            with Image.open(file) as im:
                a = np.asarray(im.resize((64,36)),dtype=np.float32)/255
            if previous is not None:
                deltas.append(float(np.mean(np.abs(a-previous))))
            previous = a
        peak = int(np.argmax(deltas))+1
        report['series'][f'{scene}-{mode}'] = {'count':len(files),'maxDelta':max(deltas),'peakFrame':peak,'adjacentDeltas':deltas}
        report['frames'] += len(files)
        samples = [round((len(files)-1)*i/11) for i in range(12)]
        peaks = list(range(max(0,min(peak-3,len(files)-6)),max(0,min(peak-3,len(files)-6))+6))
        def row(indices, width):
            canvas = Image.new('RGB',(width*len(indices),int(width*9/16)+22),'#172331')
            draw = ImageDraw.Draw(canvas)
            for j,i in enumerate(indices):
                with Image.open(files[i]) as im:
                    canvas.paste(im.resize((width,int(width*9/16))),(j*width,22))
                draw.text((j*width+4,4),f'{mode} frame {i}',fill='white')
            return canvas
        rows.append(row(samples,180))
        peak_rows.append(row(peaks,320))
    for suffix, parts in [('dense',rows),('peak-adjacent',peak_rows)]:
        canvas=Image.new('RGB',(parts[0].width,sum(p.height for p in parts)))
        y=0
        for part in parts:canvas.paste(part,(0,y));y+=part.height
        canvas.save(out/f'{scene}-{suffix}.jpg',quality=90)
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'frames':report['frames'],'series':len(report['series'])}))
