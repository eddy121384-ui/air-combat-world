"""Paired static estimates at run grain; dynamic GPU never used for ranking."""
import argparse,json,sys,math,statistics
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from perf_integrity import read_csv,sha256,validate_run
p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
spec=json.loads((a.repo/'tools/forestspike/b1a/registered.json').read_text());root=a.repo/'unreal/ForestSpike/Saved/ForestSpike/b1a'
schedule=json.loads((root/'schedule.json').read_text(encoding='utf-8-sig'))['runs']
runs=[];lookup={};errors=[]
def spread(values):
 values=list(map(float,values));mean=statistics.mean(values);sd=statistics.stdev(values) if len(values)>1 else 0
 return {'n':len(values),'median':statistics.median(values),'mean':mean,'sample_sd':sd,'min':min(values),'max':max(values),'cv_percent':sd/mean*100 if mean else None}
def calc(values):
 values=np.asarray(values,float);med=float(np.median(values));p95=float(np.percentile(values,95))
 ordered=sorted(values);x=(len(values)-1)*.95;i=int(x);manual=float(ordered[i]*(1-x+i)+ordered[min(i+1,len(values)-1)]*(x-i));assert abs(manual-p95)<1e-8
 assert abs(statistics.median(values)-med)<1e-8
 return {'median_ms':med,'p95_ms':p95,'max_ms':float(max(values))}
for row in schedule:
 d=root/'perf'/row['tag'];completion=json.loads((d/'completion.json').read_text());request=json.loads((d/'request.json').read_text(encoding='utf-8-sig'));state=json.loads((d/'run.json').read_text(encoding='utf-8-sig'))
 csvfile=Path(completion['csv']);log=Path(completion['log'])
 check=validate_run(csvfile,log,tag=row['tag'],level=request['level'],world_path=request['world_path'],run_id=request['run_id'],frames=601,cold=121,started_epoch=completion['started_epoch'],exit_code=state['exit_code'])
 motion=json.loads((d/'motion.json').read_text())
 assert state['status']=='PASS_FS_B1A_RUN' and check['status']=='PASS_FS_PERF_CAPTURE' and motion['status']=='PASS_FS_B1A_MOTION'
 assert sha256(csvfile)==completion['csv_sha256']==motion['csv_sha256'] and sha256(log)==completion['log_sha256']
 data=read_csv(csvfile);cols=data['columns'];warm=slice(121,601)
 arrays={k:np.asarray(cols[k][warm],float) for k in ['FrameTime','GPUTime','GameThreadTime','RenderThreadTime','RHIThreadTime']}
 arrays['CPUThreadMax']=np.maximum.reduce([arrays[k] for k in ['GameThreadTime','RenderThreadTime','RHIThreadTime']])
 metrics={k:calc(v) for k,v in arrays.items()};cold={k:calc(cols[k][1:121]) for k in ['FrameTime','GPUTime']}
 r={**row,'csv':str(csvfile),'csv_sha256':sha256(csvfile),'usable_frames':480,'metrics':metrics,'cold_first_120_valid':cold,'scope':'Intel UHD 770 only; static; no cross-platform inference'}
 runs.append(r);lookup[(row['round'],row['view'],row['group'])]=r
assert len(runs)==80
arms=[];pairs=[]
for pose in spec['static_poses']:
 view=pose['id']
 for group in spec['groups']:
  block=[lookup[(round,view,group)] for round in range(1,6)]
  arms.append({'view':view,'agl_m':pose['agl_m'],'group':group,'metrics':{k:{metric:spread(r['metrics'][k][metric] for r in block) for metric in ['median_ms','p95_ms']} for k in block[0]['metrics']}})
 contrasts={'S_A':{'A1':1,'A0':-1},'S_B':{'B1':1,'B0':-1},'S_main':{'A1':.5,'B1':.5,'A0':-.5,'B0':-.5}}
 if pose['agl_m'] in [50,200]:contrasts.update({'N_Soff':{'B0':1,'A0':-1},'N_Son':{'B1':1,'A1':-1},'N_main':{'B0':.5,'B1':.5,'A0':-.5,'A1':-.5},'interaction':{'B1':1,'B0':-1,'A1':-1,'A0':1}})
 for name,terms in contrasts.items():
  metricresults={}
  for metric in ['GPUTime','CPUThreadMax','FrameTime','GameThreadTime','RenderThreadTime','RHIThreadTime']:
   result={}
   for quantile in ['median_ms','p95_ms']:
    delta=[sum(weight*lookup[(rd,view,group)]['metrics'][metric][quantile] for group,weight in terms.items()) for rd in range(1,6)]
    stats=spread(delta);stats['cv_percent']=None;stats['paired_round_differences_ms']=delta
    half=2.776445105*stats['sample_sd']/math.sqrt(5)
    stats['mean_difference_t95_ci_ms']=[stats['mean']-half,stats['mean']+half]
    stats['positive_rounds']=sum(x>0 for x in delta);stats['negative_rounds']=sum(x<0 for x in delta);result[quantile]=stats
   metricresults[metric]=result
  pairs.append({'view':view,'agl_m':pose['agl_m'],'contrast':name,'terms':terms,'sign':'positive = cost increase of the positive terms; S on-off, N B-A','metrics':metricresults})
out={'status':'PASS_FS_B1A_STATIC_ANALYSIS','host_scope':'Intel UHD 770 only','runs':runs,'arms':arms,'paired_contrasts':pairs,
 'definitions':{'window':'CSV 0 invalid boot + 120 valid warm frames excluded; CSV 121..600 = 480 steady samples per run',
 'quantiles':'NumPy linear p95, independently checked against sorted-index interpolation; median independently checked using statistics.median',
 'CPUThreadMax':'Per-frame max(GameThreadTime, RenderThreadTime, RHIThreadTime), includes engine waits; proxy, not exclusive CPU work or sum of threads',
 'sampling_unit':'Five paired rounds. Run quantiles are contrasted within each view/round. No pooling of frame samples to pretend independent rounds.',
 'interval':'Student t 95% interval for mean paired difference, df4; n=5 and desktop/iGPU variability limit confidence. Not an equivalence test.',
 'far_views':'500/1000m report S within A and within B only; no N contrast or geometry ranking',
 'moving':'Excluded from static rankings; all moving GPU data diagnostic only'},'errors':errors}
with a.out.open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
print('80 static runs, paired analyses PASS')
