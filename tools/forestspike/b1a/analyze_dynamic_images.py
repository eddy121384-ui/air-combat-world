"""Exploratory 64px boundary tile trace; not isolated instance-LOD telemetry."""
import json,sys,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
r=Path(__file__).resolve().parents[3];raw=r/'unreal/ForestSpike/Saved/ForestSpike/b1a'
sys.path[:0]=[str(r/'tools/forestspike'),str(r/'tools/forestspike/b1a')]
from fs_ids import load_id
from analyze_visual import light
rows=[];sheets=raw/'review_media';sheets.mkdir(exist_ok=True)
for path,pose,start,end in [('V3','v3i_t24',720,1080),('V5','v5i_agl200_a000',120,400)]:
 cls,rng,_,_=load_id(raw/f'stills01/captures/{pose}_A1_id.png')
 cb,rb,_,_=load_id(raw/f'stills01/captures/{pose}_B1_id.png')
 ring=(np.isin(cls,[2,4,5])&(rng>=400)&(rng<=500))|(np.isin(cb,[2,4,6])&(rb>=400)&(rb<=500))
 candidates=[(float(ring[y:y+64,x:x+64].mean()),y,x) for y in range(0,1080-63,64) for x in range(0,1920-63,64)]
 score,y,x=max(candidates,key=lambda a:(a[0],-a[1],-a[2]));roi=[x,y,x+64,y+64]
 for group in ['A0','A1','B0','B1']:
  tag=f'native_{group}_V3_03' if path=='V3' else f'clip_{group}_V5_01';d=raw/'movies'/tag;valid=json.loads((d/'validated.json').read_text());assert valid['status']=='PASS_FS_B1A_NATIVE_MOVIE'
  frames={z['frame']:Path(z['file']) for z in valid['frames']};deltas=[];previous=None
  for index in range(start,end+1):
   lum=light(np.asarray(Image.open(frames[index]).convert('RGB').crop(roi)))
   if previous is not None:deltas.append({'frame':index,'mean_abs_delta_Lstar':float(np.mean(abs(lum-previous)))})
   previous=lum
  values=np.array([z['mean_abs_delta_Lstar'] for z in deltas]);peak=max(deltas,key=lambda z:z['mean_abs_delta_Lstar']);median=float(np.median(values))
  stats={'median_tile_delta_Lstar':median,'p95_tile_delta_Lstar':float(np.percentile(values,95)),'max_tile_delta_Lstar':peak['mean_abs_delta_Lstar'],'max_over_median':peak['mean_abs_delta_Lstar']/median if median else None,'peak_frame':peak['frame']}
  # No scaling: pixel-exact crops around the deterministic peak, labelled outside crops.
  canvas=Image.new('RGB',(64*12,96),(0,0,0));draw=ImageDraw.Draw(canvas)
  selected=list(range(max(start,peak['frame']-6),min(end,peak['frame']+5)+1))
  for i,f in enumerate(selected):canvas.paste(Image.open(frames[f]).convert('RGB').crop(roi),(i*64,24));draw.text((i*64,5),str(f),fill='white')
  target=sheets/f'{path}_{group}_boundary_peak_1x.png';canvas.save(target)
  rows.append({'path':path,'group':group,'frames':[start,end],'roi_xyxy':roi,'ring_fraction_at_first_frame':score,'rule':'64x64 grid tile with maximum union A/B ID forest pixels at slant range 400..500m in the first clip pose; ties top-left; same ROI for all four arms.',**stats,'trace':deltas,'peak_native_crop_sheet':str(target),'scope':'Exploratory post-sweep screen-space tile diagnostic. Camera motion, occlusion, shadows, HISM culling and LOD selection can all contribute. Not a production F9 PASS, not an isolated per-instance LOD pop measurement.'})
with (raw/'analysis/dynamic_images.json').open('x') as f:json.dump({'status':'PASS_FS_B1A_EXPLORATORY_TILE_DATA','host_scope':'Intel UHD 770 only','rows':rows},f,indent=2)
print('Eight matched dynamic boundary tile diagnostics and native crop sheets generated')
