"""Fresh offline recheck of all paths, core dwell and moving-only timing diagnostics."""
import json,sys,math,argparse
from pathlib import Path
import numpy as np
r=Path(__file__).resolve().parents[3];raw=r/'unreal/ForestSpike/Saved/ForestSpike/b1a'
sys.path[:0]=[str(r/'tools/forestspike/b1a'),str(r/'tools/forestspike')]
from integrity import verify
from perf_integrity import read_csv,validate_run,sha256
import fs_world as world
spec=json.loads((r/'tools/forestspike/b1a/registered.json').read_text());reopen=json.loads((raw/'reopen02/receipt.json').read_text())
def hits(eyes,dirs):
 n=len(eyes);alive=np.ones(n,bool);hit=np.full(n,np.nan);t=0.;step=2.
 while t<9000 and alive.any():
  previous=t;t+=step;idx=np.where(alive)[0];xyz=eyes[idx]+t*dirs[idx]
  outside=(abs(xyz[:,0])>world.CTX_HALF)|(abs(xyz[:,1])>world.CTX_HALF)
  cross=(xyz[:,2]<world.height(xyz[:,0],xyz[:,1]))&~outside
  ci=idx[cross]
  if len(ci):
   lo=np.full(len(ci),previous);hi=np.full(len(ci),t)
   for _ in range(14):
    mid=(lo+hi)*.5;p=eyes[ci]+mid[:,None]*dirs[ci];below=p[:,2]<world.height(p[:,0],p[:,1]);hi=np.where(below,mid,hi);lo=np.where(below,lo,mid)
   hit[ci]=(lo+hi)*.5;alive[ci]=False
  alive[idx[outside]]=False;step=min(step*1.01,12.)
 return eyes+hit[:,None]*dirs
rows=[]
for path in ['V3','V5']:
 for group in ['A0','A1','B0','B1']:
  tag=f'dynamic_{group}_{path}_01';d=raw/'perf'/tag;c=json.loads((d/'completion.json').read_text());req=json.loads((d/'request.json').read_text(encoding='utf-8-sig'));run=json.loads((d/'run.json').read_text(encoding='utf-8-sig'))
  cfg=next(x for x in reopen['maps'] if x['group']==group and x['view']==path);csv=Path(c['csv'])
  gate=validate_run(csv,Path(c['log']),tag=tag,level=req['level'],world_path=req['world_path'],run_id=req['run_id'],frames=req['frames'],cold=req['cold'],started_epoch=c['started_epoch'],exit_code=run['exit_code'])
  motion,trace=verify(csv,spec,cfg);assert gate['status']=='PASS_FS_PERF_CAPTURE' and motion['status']=='PASS_FS_B1A_MOTION'
  assert sha256(csv)==c['csv_sha256'] and sha256(Path(c['log']))==c['log_sha256']
  flight=[x for x in trace if x['phase']=='flight'];eyes=np.array([[x['x_cm']/100,-x['y_cm']/100,x['z_cm']/100] for x in flight]);dirs=np.array([[x['forward_x'],-x['forward_y'],x['forward_z']] for x in flight]);ground=hits(eyes,dirs)
  eligible=(abs(eyes[:,:2])<=500).all(axis=1)&(abs(ground[:,:2])<=500).all(axis=1)&np.isfinite(ground).all(axis=1)
  interval_eligible=eligible[:-1]&eligible[1:];duration=float(interval_eligible.sum()/60)
  indices=[x['csv_frame'] for x in flight];columns=read_csv(csv)['columns'];metrics={}
  for key in ['GPUTime','FrameTime','GameThreadTime','RenderThreadTime','RHIThreadTime']:
   v=np.array([columns[key][i] for i in indices]);metrics[key]={'median_ms':float(np.median(v)),'p95_ms':float(np.percentile(v,95))}
  rows.append({'tag':tag,'motion':motion,'core_camera_and_centre_ground_ray':{'eligible_flight_samples':int(eligible.sum()),'eligible_intervals':int(interval_eligible.sum()),'eligible_seconds':duration,'first_path_t_s':next((x['path_t_s'] for x,e in zip(flight,eligible) if e),None),'last_path_t_s':next((x['path_t_s'] for x,e in zip(reversed(flight),reversed(eligible)) if e),None)},'moving_timing_diagnostic_only':metrics,'prohibition':'Intel UHD 770 only; GPU moving timings are diagnostic, never ranked or used for N/S performance conclusions.'})
out={'status':'PASS_FS_B1A_EIGHT_PATH_RECHECKS','rows':rows,'scope':'Fixed-step sequence time, not achieved real-time FPS. Analytic centre-ray/core dwell is a view eligibility check, not visibility attribution.'}
with (raw/'analysis/motion.json').open('x') as f:json.dump(out,f,indent=2)
print('Eight full paths revalidated, core dwell quantified; moving GPU remains diagnostic')
