"""Per-frame fixed static / V3 / inward V5 motion gate; timing gate remains separate."""
import sys,json,math,csv,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from perf_integrity import read_csv,sha256
from motion_integrity import angle
def expected(spec,cfg,frame):
 if not cfg['path_id']:
  p=cfg['pose'];elapsed=0;segment=0;phase='static';t=None
 else:
  path=spec['paths'][cfg['path_id']];fpp=path['frames_per_pose'];elapsed=max(0,min(path['flight_intervals'],frame-120));segment=min(len(path['poses'])-2,elapsed//fpp)
  a,b=path['poses'][segment:segment+2];alpha=(elapsed-segment*fpp)/fpp
  p={'eye_enu':[x*(1-alpha)+y*alpha for x,y in zip(a['eye_enu'],b['eye_enu'])],
     'heading_deg':a['heading_deg']*(1-alpha)+b['heading_deg']*alpha,'pitch_deg':a['pitch_deg']*(1-alpha)+b['pitch_deg']*alpha}
  phase='warm_hold' if frame<120 else ('flight' if frame<=120+path['flight_intervals'] else 'endpoint_hold')
  t=path['poses'][0]['t_s']+elapsed/60
 e,n,z=p['eye_enu'];yaw=math.radians(p['heading_deg']-90);pitch=math.radians(p['pitch_deg'])
 return [e*100,-n*100,z*100],[math.cos(pitch)*math.cos(yaw),math.cos(pitch)*math.sin(yaw),math.sin(pitch)],[-math.sin(pitch)*math.cos(yaw),-math.sin(pitch)*math.sin(yaw),math.cos(pitch)],phase,segment,t
def verify(file,spec,cfg):
 errors=[];report={'status':'FAIL_FS_B1A_MOTION','csv_sha256':sha256(file),'group':cfg['group'],'view':cfg['view'],'errors':errors,'host_scope':'Intel UHD 770 only'}
 try:
  data=read_csv(file);cols=data['columns'];vectors={n:[[cols['View/'+n+k][i] for k in 'XYZ'] for i in range(data['frames'])] for n in ['Pos','Forward','Up']}
 except (ValueError,KeyError) as exc:
  errors.append(str(exc));return report,[]
 pos=vectors['Pos'];boot=next((i for i,x in enumerate(pos) if math.dist(x,[0,0,0])>1),len(pos));tol=spec['motion_tolerances']
 if boot>4 or any(math.dist(x,[0,0,0])<1 for x in pos[boot:]):errors.append('invalid world-view/boot samples')
 offset=min([0,1],key=lambda o:max((math.dist(x,expected(spec,cfg,i+o)[0]) for i,x in enumerate(pos[boot:])),default=float('inf')))
 rows=[];distance=0.
 for i,x in enumerate(pos):
  frame=i-boot+offset;xyz,fwd,up,phase,segment,t=expected(spec,cfg,frame)
  phase=phase if i>=boot else 'invalid_boot'
  step=math.dist(x,pos[i-1])/100 if i>boot else 0.
  if phase=='flight' and frame>120:distance+=step
  row={'csv_frame':i,'sequence_frame':frame if i>=boot else '', 'phase':phase,'segment':segment,'path_t_s':t,
       'x_cm':x[0],'y_cm':x[1],'z_cm':x[2],'position_error_m':math.dist(x,xyz)/100 if i>=boot else '',
       'forward_error_deg':angle(vectors['Forward'][i],fwd) if i>=boot else '', 'up_error_deg':angle(vectors['Up'][i],up) if i>=boot else '',
       'step_distance_m':step,'cumulative_flight_distance_m':distance}
  for n in ['Forward','Up']:
   row.update({n.lower()+'_'+k.lower():v for k,v in zip('XYZ',vectors[n][i])})
  rows.append(row)
 valid=rows[boot:];maxima={k:max((x[k] for x in valid),default=float('inf')) for k in ['position_error_m','forward_error_deg','up_error_deg']}
 if maxima['position_error_m']>tol['position_m'] or max(maxima['forward_error_deg'],maxima['up_error_deg'])>tol['orientation_deg']:errors.append('per-frame position/orientation differs from registration')
 warm=max((math.dist(x,expected(spec,cfg,0)[0])/100 for x in pos[boot:boot+120]),default=float('inf'))
 if len(pos[boot:boot+120])!=120 or warm>tol['warm_displacement_m']:errors.append('120 valid starting samples did not hold still')
 flight=[r for r in valid if r['phase']=='flight'];path=spec['paths'].get(cfg['path_id'])
 if path:
  if len(flight)!=path['flight_intervals']+1 or not flight or flight[0]['sequence_frame']!=120 or flight[-1]['sequence_frame']!=120+path['flight_intervals']:errors.append('flight window incomplete')
  exp=[expected(spec,cfg,f)[0] for f in range(120,121+path['flight_intervals'])];exp_distance=sum(math.dist(a,b) for a,b in zip(exp,exp[1:]))/100
  if distance<500 or abs(distance-exp_distance)>.1:errors.append('flight distance mismatch')
  fp=[pos[r['csv_frame']] for r in flight]
  if cfg['path_id']=='V3' and any(b[0]<=a[0] or b[1]>=a[1] for a,b in zip(fp,fp[1:])):errors.append('V3 nonmonotonic inbound motion')
  if cfg['path_id']=='V5':
   for row in flight:
    i=row['csv_frame'];x=pos[i];f=vectors['Forward'][i];rad=math.hypot(x[0],x[1])/100
    dot=-(x[0]*f[0]+x[1]*f[1])/(max(1,math.hypot(x[0],x[1]))*max(1e-9,math.hypot(f[0],f[1])))
    if not 315<=rad<=331 or dot<.95:errors.append('V5 radius/inward orientation invalid');break
  report.update({'flight_samples':len(flight),'flight_csv_range':[r['csv_frame'] for r in flight[::max(1,len(flight)-1)]],
     'flight_seconds':path['flight_intervals']/60,'registered_distance_m':exp_distance,'measured_distance_m':distance,'endpoint_error_m':math.dist(fp[-1],exp[-1])/100 if fp else None})
 report.update({'frames':data['frames'],'invalid_boot_frames':boot,'startup_sequence_frame':offset,'warm_displacement_m':warm,'max_errors':maxima})
 if not errors:report['status']='PASS_FS_B1A_MOTION'
 return report,rows
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for x in ['csv','spec','reopen','out','trace']:p.add_argument('--'+x,required=True,type=Path)
 p.add_argument('--group',required=True);p.add_argument('--view',required=True);a=p.parse_args()
 spec=json.loads(a.spec.read_text());reopen=json.loads(a.reopen.read_text());cfg=next(x for x in reopen['maps'] if x['group']==a.group and x['view']==a.view)
 report,rows=verify(a.csv,spec,cfg)
 with a.out.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
 with a.trace.open('x',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['csv_frame']);w.writeheader();w.writerows(rows)
 print(report['status'],report['errors']);raise SystemExit(0 if not report['errors'] else 2)
