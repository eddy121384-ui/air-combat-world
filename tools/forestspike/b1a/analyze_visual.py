"""Native ID/LOD attribution, matched image change and locked-camera F11 diagnostics."""
import argparse,json,re,sys,hashlib,math
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fs_ids import load_id
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def light(rgb):
 v=np.asarray(rgb,dtype=np.float64)/255
 linear=np.where(v<=.04045,v/12.92,((v+.055)/1.055)**2.4)
 y=linear@np.array([.2126729,.7151522,.0721750])
 return np.where(y>(6/29)**3,116*np.cbrt(y)-16,(29/3)**3*y)
def quant95(v):
 v=np.asarray(v);actual=float(np.percentile(v,95));ordered=np.sort(v);x=(len(v)-1)*.95;i=int(x)
 manual=float(ordered[i]*(1-x+i)+ordered[min(i+1,len(v)-1)]*(x-i));assert abs(actual-manual)<1e-8
 return actual
def main():
 p=argparse.ArgumentParser();p.add_argument('--dir',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 receipt=json.loads((a.dir/'receipt.json').read_text());assert receipt['status']=='PASS_FS_B1A_STILLS_CAPTURE'
 log=(a.dir/'engine.log').read_text(encoding='utf-8-sig',errors='replace');build=json.loads(a.build.read_text())
 triangles={k:v['triangles'] for k,v in build['mesh_readback'].items()};rows=[];images={};ids={};temporal=[]
 for c in receipt['captures']:
  j=c['job'];file=Path(c['file']);assert sha(file)==c['sha256'];im=np.asarray(Image.open(file).convert('RGB'));assert im.shape==(1080,1920,3)
  arm=j['group'][0];pose=j['pose']['id'];treeblock=re.search('FS_B1A_TREE_BEGIN '+re.escape(j['name'])+r'\n(.*?)FS_B1A_TREE_END '+re.escape(j['name']),log,re.S)
  assert treeblock and 'Rebuild Foliage Trees' in treeblock.group(1)
  render=re.search('FS_B1A_RENDER_BEGIN '+re.escape(j['name'])+r'\n(.*?)FS_B1A_RENDER_END '+re.escape(j['name']),log,re.S);assert render
  submissions=[]
  for line in render.group(1).splitlines():
   m=re.search(r'lod:(\d+)/3\s+section:0/1\s+runs:\s*(\d+)\s+inst:\s*(\d+)\s+tris:\s*(\d+).*?\s+shadow:0\s+(\S+)\s+',line)
   if not m:continue
   lod,runs,n,tris=map(int,m.group(1,2,3,4));mesh=m.group(5).split('/')[-1].split('.')[0]
   assert mesh in triangles and tris==n*triangles[mesh][lod]
   submissions.append({'mesh':mesh,'lod':lod,'runs':runs,'submitted_instances':n,'submitted_triangles':tris})
  assert len({(s['mesh'],s['lod']) for s in submissions})==len(submissions),'ambiguous primary views'
  row={'name':j['name'],'pose':j['pose'],'group':j['group'],'kind':j['kind'],'file':str(file),'sha256':c['sha256'],'primary_submissions':submissions}
  if j['kind']=='id':
   cls,rng,exact,_=load_id(file);assert exact.mean()>.999
   tree=np.isin(cls,[5,6]);core=np.isin(cls,[1,2,5,6]);forest=np.isin(cls,[2,4,5,6])
   row.update({'code_exact_fraction':float(exact.mean()),'tree_pixels':int(tree.sum()),'core_projected_pixels':int(core.sum()),
    'tree_fraction_frame':float(tree.mean()),'core_fraction_frame':float(core.mean()),'tree_fraction_projected_core':float(tree.sum()/core.sum()) if core.any() else None,
    'forest_pixels':int(forest.sum()),'core_forest_pixels':int(((cls==2)|tree).sum()),'forest_core_fraction':float(((cls==2)|tree).sum()/forest.sum()) if forest.any() else None,
    'range_caveat':'Tree crowns can overhang the core boundary; primary submitted instances are not unique visible IDs or pixel histograms.'})
   ids[(pose,arm)]=(cls,rng)
  elif j['kind']=='lod':
   counts=[int(((im[...,i]>200)&(im[...,(i+1)%3]<30)&(im[...,(i+2)%3]<30)).sum()) for i in range(3)]
   row['lod_color_pixels']=counts
   assert set(i for i,n in enumerate(counts) if n).issubset({s['lod'] for s in submissions})
  else:
   images[(pose,j['group'])]=file
   if c.get('temporal'):temporal.append(c)
  rows.append(row)
 comparisons=[]
 for pose in sorted({k[0] for k in images}):
  lum={g:light(np.asarray(Image.open(images[(pose,g)]).convert('RGB'))) for g in ['A0','A1','B0','B1']}
  ca,ra=ids[(pose,'A')];cb,rb=ids[(pose,'B')];core=np.isin(ca,[1,2,5])|np.isin(cb,[1,2,6]);potential_forest=np.isin(ca,[2,4,5])|np.isin(cb,[2,4,6])
  agl=next(x['pose']['agl_m'] for x in rows if x['pose']['id']==pose)
  contrasts={'S_A':('A1','A0'),'S_B':('B1','B0')}
  if agl in [50,200]:contrasts.update({'N_Soff':('B0','A0'),'N_Son':('B1','A1')})
  changes={name:{'whole_frame_Lstar_MAE':float(np.mean(abs(lum[hi]-lum[lo]))),
    'projected_core_Lstar_MAE':float(np.mean(abs(lum[hi]-lum[lo])[core])) if core.any() else None,
    'potential_forest_Lstar_MAE':float(np.mean(abs(lum[hi]-lum[lo])[potential_forest])) if potential_forest.any() else None} for name,(hi,lo) in contrasts.items()}
  comparisons.append({'pose':pose,'agl_m':agl,'changes':changes,'scope':'Image-change magnitude, not perceptual improvement or calibrated AC7 fidelity. No geometry contrast at 500/1000m.'})
 f11=[]
 for c in temporal:
  j=c['job'];pose=j['pose']['id'];arm=j['group'][0];frames=c['temporal'];assert len(frames)==64 and c['warm_capture_ticks']==120
  sum_l=np.zeros((1080,1920),np.float64);sum_l2=sum_l.copy();small=[]
  for f in frames:
   file=Path(f['file']);assert sha(file)==f['sha256'];l=light(np.asarray(Image.open(file).convert('RGB')))
   sum_l+=l;sum_l2+=l*l;small.append(l[::64,::64])
  sigma=np.sqrt(np.maximum(0,sum_l2/64-(sum_l/64)**2));independent=np.std(np.stack(small),axis=0,ddof=0)
  assert np.max(abs(independent-sigma[::64,::64]))<1e-4
  cls,rng=ids[(pose,arm)];forest=np.isin(cls,[2,4,5,6]);tree=np.isin(cls,[5,6]);far=np.isin(cls,[2,4])&(rng>=500);near=forest&~far
  metrics={name:{'pixels':int(mask.sum()),'p95_sigma_Lstar':quant95(sigma[mask]),'mean_sigma_Lstar':float(np.mean(sigma[mask]))} for name,mask in [('all_potential_forest',forest),('near',near),('tree_geometry',tree),('far_potential_forest',far)] if mask.any()}
  f11.append({'pose':pose,'group':j['group'],'frames':64,'warm_render_ticks':120,'metrics':metrics,
    'scope':'Locked-camera native SceneCapture diagnostic; population sigma, D65 display-referred sRGB L*. S-off far forest is absent. Calibration-pending thresholds cannot establish a production PASS.'})
 assert len(f11)==16
 result={'status':'PASS_FS_B1A_VISUAL_DATA_INTEGRITY','rows':rows,'matched_image_changes':comparisons,'F11_static':f11,'cvars':receipt['cvars'],
  'scope':'Data integrity and descriptive metrics only, not automatic visual acceptance. Normal primary submissions exclude shadow cascades and do not prove per-instance pixel visibility.',
  'host_scope':'Intel UHD 770 only','receipt_sha256':sha(a.dir/'receipt.json'),'log_sha256':sha(a.dir/'engine.log')}
 with a.out.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
 print('Native stills / ID / LOD / 16x64 temporal data integrity PASS')
if __name__=='__main__':main()
