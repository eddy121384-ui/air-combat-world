"""Native MRQ completeness gate. No CSV-exists or frame-log-only success."""
import argparse,json,re,hashlib,datetime
from pathlib import Path
from PIL import Image
p=argparse.ArgumentParser();p.add_argument('--dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
request=json.loads((a.dir/'request.json').read_text(encoding='utf-8-sig'));proc=json.loads((a.dir/'process.json').read_text(encoding='utf-8-sig'));cfg=request['config'];log=(a.dir/'engine.log').read_text(encoding='utf-8-sig',errors='replace');errors=[]
def digest(f):return hashlib.sha256(f.read_bytes()).hexdigest()
frames=sorted((a.dir/'frames').rglob('frame_*.png'));expected=cfg['frames'];started=datetime.datetime.fromisoformat(request['started_utc']).timestamp()
if len(frames)!=expected or [int(re.search(r'frame_(\d+)\.png$',f.name).group(1)) for f in frames]!=list(range(expected)):errors.append('incomplete or noncontiguous native PNG sequence')
if proc['exit_code']!=0:errors.append('native render did not exit normally')
if 'Finished rendering last shot. Moving to Finalize to finish writing items to disk.' not in log or 'LogExit: Exiting.' not in log:errors.append('authoritative render/finalization/exit record missing')
leaf=cfg['map'].split('/')[-1]
if not re.search('Bringing World '+re.escape(cfg['map'])+r'\.'+re.escape(leaf)+' up for play',log):errors.append('wrong or unconfirmed native world')
if '-LevelSequence='+cfg['sequence'] not in request['args']:errors.append('wrong native sequence request')
for name,val in [('foliage.ForceLOD',-1),('r.ForceLOD',-1),('foliage.LODDistanceScale',1),('foliage.RandomLODRange',0),('r.ViewDistanceScale',1)]:
 if not re.search(r'Applying CVar "'+re.escape(name)+r'" PreviousValue: [^\n]+ NewValue: '+str(val)+r'\.0+',log):errors.append('automatic render setting not confirmed: '+name)
if cfg['game_overrides_enabled'] or cfg['force_lod_zero'] or cfg['cinematic_quality']:errors.append('forbidden cinematic/LOD overrides')
rows=[]
for f in frames:
 size=Image.open(f).size
 if size!=(1920,1080) or f.stat().st_mtime<started:errors.append('wrong resolution/stale frame: '+f.name)
 b=f.read_bytes()
 if b[:8]!=b'\x89PNG\r\n\x1a\n' or b[-12:]!=b'\x00\x00\x00\x00IEND\xaeB`\x82':errors.append('truncated PNG: '+f.name)
 rows.append({'frame':int(re.search(r'(\d+)\.png$',f.name).group(1)),'file':str(f),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
result={'status':'PASS_FS_B1A_NATIVE_MOVIE' if not errors else 'FAIL_FS_B1A_NATIVE_MOVIE','tag':request['tag'],'scope':'Native MRQ image sequence identity, automatic settings, completeness/freshness, normal exit. Actual path separately cross-checked with saved bindings and game CSV. Not real-time FPS.','errors':errors,'config':cfg,'request_sha256':digest(a.dir/'request.json'),'engine_log_sha256':digest(a.dir/'engine.log'),'frames':rows,'host_scope':'Intel UHD 770 only'}
with a.out.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
print(result['status'],len(frames),errors);raise SystemExit(0 if not errors else 2)
