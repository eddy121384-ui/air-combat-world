"""Primary native MRQ static/F11 evidence; SceneCapture shaded data remain diagnostic."""
import json,sys,hashlib,shutil,time
from pathlib import Path
import numpy as np
from PIL import Image
r=Path(__file__).resolve().parents[3];raw=r/'unreal/ForestSpike/Saved/ForestSpike/b1a'
sys.path[:0]=[str(r/'tools/forestspike'),str(r/'tools/forestspike/b1a')]
from fs_ids import load_id
from analyze_visual import light as reference_light,quant95
v=np.arange(256,dtype=np.float64)/255
linear_lut=np.where(v<=.04045,v/12.92,((v+.055)/1.055)**2.4)
def light(rgb):
 y=linear_lut[rgb[...,0]]*.2126729+linear_lut[rgb[...,1]]*.7151522+linear_lut[rgb[...,2]]*.0721750
 return np.where(y>(6/29)**3,116*np.cbrt(y)-16,(29/3)**3*y)
configs=json.loads((raw/'native_static_reopen01/receipt.json').read_text())['configs'];assert len(configs)==16
out=raw/'native_static_primary';out.mkdir(exist_ok=False);f11=[];images={};source=[]
for c in configs:
 d=raw/'movies'/c['tag'];deadline=time.monotonic()+900
 while not (d/'validated.json').exists():
  assert time.monotonic()<deadline,'Native static validation timed out: '+c['tag'];time.sleep(1)
 valid=json.loads((d/'validated.json').read_text());assert valid['status']=='PASS_FS_B1A_NATIVE_MOVIE' and len(valid['frames'])==184
 frames={f['frame']:f for f in valid['frames']};pose=c['path_id'];group=c['group'];arm=group[0]
 dest=out/f'{pose}_{group}_visual.png';shutil.copyfile(frames[120]['file'],dest);images[(pose,group)]=dest
 sum_l=np.zeros((1080,1920),np.float64);sum_l2=sum_l.copy();small=[]
 for i in range(120,184):
  row=frames[i];p=Path(row['file']);assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
  rgb=np.asarray(Image.open(p).convert('RGB'));l=light(rgb)
  if i==120:assert np.max(abs(reference_light(rgb)-l))<1e-8
  sum_l+=l;sum_l2+=l*l;small.append(l[::64,::64])
 sigma=np.sqrt(np.maximum(0,sum_l2/64-(sum_l/64)**2));assert np.max(abs(np.std(np.stack(small),axis=0,ddof=0)-sigma[::64,::64]))<1e-4
 cls,rng,exact,_=load_id(raw/f'stills01/captures/{pose}_{arm}1_id.png');assert exact.mean()>.999
 forest=np.isin(cls,[2,4,5,6]);tree=np.isin(cls,[5,6]);far=np.isin(cls,[2,4])&(rng>=500);near=forest&~far
 metrics={name:{'pixels':int(mask.sum()),'p95_sigma_Lstar':quant95(sigma[mask]),'mean_sigma_Lstar':float(np.mean(sigma[mask]))} for name,mask in [('all_potential_forest',forest),('near',near),('tree_geometry',tree),('far_potential_forest',far)] if mask.any()}
 f11.append({'pose':pose,'group':group,'frames':64,'warm_render_ticks':120,'metrics':metrics,'scope':'Primary native-game MRQ PNG frame120..183 after120 fixed warm output frames; population sigma D65 display-referred sRGB L*. Source matches accepted movie pipeline; calibration-pending thresholds are not production acceptance.'})
 source.append({'pose':pose,'group':group,'primary':str(dest),'primary_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'validation_sha256':hashlib.sha256((d/'validated.json').read_bytes()).hexdigest()})
 print('Native F11 complete',pose,group,flush=True)
comparisons=[]
for pose in sorted({p for p,g in images}):
 lum={g:light(np.asarray(Image.open(images[(pose,g)]).convert('RGB'))) for g in ['A0','A1','B0','B1']}
 ca,ra,_,_=load_id(raw/f'stills01/captures/{pose}_A1_id.png');cb,rb,_,_=load_id(raw/f'stills01/captures/{pose}_B1_id.png')
 core=np.isin(ca,[1,2,5])|np.isin(cb,[1,2,6]);forest=np.isin(ca,[2,4,5])|np.isin(cb,[2,4,6]);agl=next(c['pose']['agl_m'] for c in configs if c['path_id']==pose)
 contrasts={'S_A':('A1','A0'),'S_B':('B1','B0')}
 if agl in [50,200]:contrasts.update({'N_Soff':('B0','A0'),'N_Son':('B1','A1')})
 changes={k:{'whole_frame_Lstar_MAE':float(np.mean(abs(lum[hi]-lum[lo]))),'projected_core_Lstar_MAE':float(np.mean(abs(lum[hi]-lum[lo])[core])),'potential_forest_Lstar_MAE':float(np.mean(abs(lum[hi]-lum[lo])[forest]))} for k,(hi,lo) in contrasts.items()}
 comparisons.append({'pose':pose,'agl_m':agl,'changes':changes,'scope':'Matched native display-referred image-change magnitude, not perceptual improvement. No N contrast at500/1000m.'})
result={'status':'PASS_FS_B1A_NATIVE_STATIC_F11_DATA','F11_static':f11,'matched_image_changes':comparisons,'sources':source,'host_scope':'Intel UHD 770 only','color_source':'UE5.8 MoviePipelineImageSequenceOutput.cpp:257 applies sRGB quantization unless OCIO enabled; no OCIO override in configs.','supersedes_for_primary_quality':'SceneCapture shaded images/F11 remain retained, secondary diagnostics only. Their export appearance differs; no cross-pipeline luminance inference.'}
with (raw/'analysis/native_static.json').open('x') as f:json.dump(result,f,indent=2)
print('Native static +16x64 F11 data integrity PASS')
