"""Standalone normal-game primary draw snapshots, separate from formal timings."""
import json,re,argparse,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--dir',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
build=json.loads(a.build.read_text());tri={k:r['triangles'] for k,r in build['mesh_readback'].items()};rows=[]
for d in sorted(a.dir.iterdir()):
 if not d.is_dir():continue
 req=json.loads((d/'request.json').read_text(encoding='utf-8-sig'));run=json.loads((d/'run.json').read_text(encoding='utf-8-sig'));motion=json.loads((d/'motion.json').read_text())
 assert run['status']=='PASS_FS_B1A_RUN' and motion['status']=='PASS_FS_B1A_MOTION' and motion['frames']==241
 log=(d/'engine.log').read_text(encoding='utf-8-sig',errors='replace');submissions=[]
 for line in log.splitlines():
  m=re.search(r'lod:(\d+)/3\s+section:0/1\s+runs:\s*(\d+)\s+inst:\s*(\d+)\s+tris:\s*(\d+).*?\s+shadow:0\s+(\S+)\s+',line)
  if not m:continue
  lod,runs,n,tris=map(int,m.group(1,2,3,4));mesh=m.group(5).split('/')[-1].split('.')[0]
  assert mesh in tri and tris==n*tri[mesh][lod]
  submissions.append({'mesh':mesh,'lod':lod,'runs':runs,'submitted_instances':n,'submitted_triangles':tris,'native_log_line':line})
 assert len({(s['mesh'],s['lod']) for s in submissions})==len(submissions),'ambiguous duplicate primary snapshots'
 near='agl50_' in req['view'] or 'agl200_' in req['view']
 if near:assert submissions,'missing normal-game near snapshot'
 rows.append({'tag':req['tag'],'view':req['view'],'group':req['group'],'primary_submissions':submissions,
  'submitted_instances_by_lod':[sum(s['submitted_instances'] for s in submissions if s['lod']==i) for i in range(3)] if submissions else None,
  'submitted_triangles_by_lod':[sum(s['submitted_triangles'] for s in submissions if s['lod']==i) for i in range(3)] if submissions else None,
  'snapshot_observed':bool(submissions),'log_sha256':hashlib.sha256((d/'engine.log').read_bytes()).hexdigest(),
  'scope':'One normal-game early primary render snapshot; same held camera verified in all 240 valid CSV rows, auto LOD. Not a full-run/per-instance histogram. Empty far logs are not relabelled measured zero; independent ID pixels verify visible geometry.'})
assert len(rows)==8
with a.out.open('x',encoding='utf-8') as f:json.dump({'status':'PASS_FS_B1A_RUNTIME_LOD_SNAPSHOTS','rows':rows,'host_scope':'Intel UHD 770 only','ranking':'Not used in formal performance aggregation'},f,indent=2)
print('8 standalone LOD diagnostics validated')
