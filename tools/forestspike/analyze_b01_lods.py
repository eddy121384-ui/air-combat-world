"""Classify actual auto-selected LOD material colors, without forcing LOD."""
import argparse
import json
import re
from datetime import datetime
from pathlib import Path
import numpy as np
from PIL import Image
from perf_integrity import sha256

p=argparse.ArgumentParser()
p.add_argument('--dir',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--base-dir',type=Path,help='Combine base non-boundary controls with a new boundary-only receipt; retain both originals')
a=p.parse_args()
errors=[]
rows=[]
inputs=[]
captures=[]
for directory in ([a.base_dir,a.dir] if a.base_dir else [a.dir]):
    receipt=json.loads((directory/'receipt.json').read_text(encoding='utf-8'))
    log=(directory/'engine.log').read_text(encoding='utf-8-sig',errors='replace')
    request=json.loads((directory/'request.json').read_text(encoding='utf-8-sig'))
    process=json.loads((directory/'process.json').read_text(encoding='utf-8-sig'))
    started=datetime.fromisoformat(request['started_utc']).timestamp()
    assert receipt['status']=='PASS_FS_B01_LOD_CAPTURE'
    assert process['fresh_receipt'] and process['status']==receipt['status']
    assert (directory/'receipt.json').stat().st_mtime>=started
    assert receipt['cvars']['foliage.ForceLOD']==receipt['cvars']['r.ForceLOD']==-1
    assert receipt['cvars']['foliage.LODDistanceScale']==receipt['cvars']['r.ViewDistanceScale']==1
    assert receipt['cvars']['foliage.RandomLODRange']==0
    assert receipt['capture_lod_distance_factor']==1
    inputs.append({'directory':str(directory),'receipt_sha256':sha256(directory/'receipt.json'),
                   'engine_log_sha256':sha256(directory/'engine.log'),'observed_exit_code':process['exit_code'],
                   'fresh_capture_receipt':True,'shutdown_success':process['exit_code']==0})
    for capture in receipt['captures']:
        boundary=capture['job']['name'].startswith('boundary_')
        if a.base_dir and ((directory==a.base_dir and boundary) or (directory==a.dir and not boundary)):
            continue
        captures.append((directory,log,capture))
assert len({c['job']['name'] for _,_,c in captures})==len(captures)
if a.base_dir:
    assert len(captures)==81
    assert sum(c['job']['kind']=='forest' for _,_,c in captures)==16
    assert sum(c['job']['kind']=='cull' for _,_,c in captures)==20
    assert sum(c['job']['name'].startswith('boundary_') for _,_,c in captures)==20
assert captures,'missing LOD captures'
triangles={'Tree_A':[28,28,28],'Tree_B_dense_rounded':[120,36,20],
           'Tree_B_horizontal_tiered':[112,38,20],'Tree_B_open_vase':[102,40,20],'Tree_B_tall_columnar':[108,38,20]}
for directory,log,capture in captures:
    job=capture['job']
    file=directory/'captures'/(job['name']+'.png')
    assert sha256(file)==capture['sha256']
    assert file.stat().st_mtime>=datetime.fromisoformat(json.loads((directory/'request.json').read_text(encoding='utf-8-sig'))['started_utc']).timestamp()
    rgb=np.asarray(Image.open(file).convert('RGB'))
    assert rgb.shape==(1080,1920,3)
    counts=[int(((rgb[...,i]>200)&(rgb[...,(i+1)%3]<30)&(rgb[...,(i+2)%3]<30)).sum()) for i in range(3)]
    selected=[i for i,n in enumerate(counts) if n]
    state=capture['hism_state']
    assert all(s['forced_lod_model']==0 and s['instance_lod_distance_scale']==1 for s in state.values())
    assert sum(s['instance_count'] for s in state.values())==({'A':30200,'B':30100}[job['arm']] if job['kind']=='forest' else 1)
    tree_block=re.search('FS_B01_TREE_BEGIN '+re.escape(job['name'])+r'\n(.*?)FS_B01_TREE_END '+re.escape(job['name']),log,re.S)
    built=bool(tree_block and 'Rebuild Foliage Trees' in tree_block.group(1) and job.get('tree_build_method'))
    render_block=re.search('FS_B01_RENDER_BEGIN '+re.escape(job['name'])+r'\n(.*?)FS_B01_RENDER_END '+re.escape(job['name']),log,re.S)
    native_lines=[line for line in render_block.group(1).splitlines() if 'lod:' in line] if render_block else []
    primary=[]
    for line in native_lines:
        m=re.search(r'lod:(\d+)/3\s+section:0/1\s+runs:\s*(\d+)\s+inst:\s*(\d+)\s+tris:\s*(\d+).*?\s+shadow:0\s+(\S+)\s+M_LOD(\d+)',line)
        if not m:continue
        lod,runs,instances,tris=map(int,m.group(1,2,3,4))
        mesh=re.search(r'/Debug/(Tree_.*?)_(legacy|policy)\.',m.group(5)).group(1)
        assert lod==int(m.group(6)) and tris==instances*triangles[mesh][lod],line
        primary.append({'mesh':mesh,'lod':lod,'runs':runs,'submitted_instances':instances,'submitted_triangles':tris})
    assert len({(r['mesh'],r['lod']) for r in primary})==len(primary),'ambiguous duplicate primary draw log'
    submitted=sorted({r['lod'] for r in primary if r['submitted_instances']})
    native_valid=set(selected).issubset(submitted) and bool(render_block)
    row={'name':job['name'],'kind':job['kind'],'job':job,'lod_color_pixels':counts,'selected_lods':selected,
         'built_tree_verified':built,'hism_state':state,'native_lod_log_lines':native_lines,
         'native_primary_submissions':primary,'native_submitted_lods':submitted,'evidence_directory':str(directory),
         'sha256':capture['sha256']}
    if job['kind']=='single':
        row['pass']=selected==[job['expected_lod']] and built and native_valid and len(primary)==1 and primary[0]['submitted_instances']==1 and submitted==selected
        row['visible_instance_count']=1 if selected else 0
        if selected==[job['expected_lod']]:
            row['confidence']='one HISM instance, per-LOD section material identifies submitted render LOD; not forced'
        if not row['pass']:errors.append('single-instance LOD mismatch: '+job['name'])
    elif job['kind']=='cull':
        row['pass']=bool(selected)==job['expected_visible'] and built and native_valid and bool(primary)==job['expected_visible']
        if not row['pass']:errors.append('normal cull visibility mismatch: '+job['name'])
    else:
        row['pass']=bool(selected) and built and native_valid
        if job['policy']=='policy':
            if 'agl50' in job['pose_id']:
                row['pass'] &= selected==[0,1,2]
            else:
                # Screen policy is based on projected bounds, not altitude.
                # Large instances / cluster grouping may also submit LOD0.
                row['pass'] &= 1 in selected and 2 in selected
        if not row['pass']:errors.append('forest LOD colors or cluster build mismatch: '+job['name'])
    rows.append(row)
out={'status':'PASS_FS_B01_AUTO_LOD' if not errors else 'FAIL_FS_B01_AUTO_LOD','errors':errors,'rows':rows,
     'inputs':inputs,'composition':'base non-boundary cases plus separately retested boundary cases; previous failures remain in their original receipts' if a.base_dir else 'single capture receipt',
     'scope':'Controlled isolated HISM instances plus actual 50m/200m automatic forest color evidence. Not a full-forest per-instance/triangle histogram.',
     'colors':{'red':'LOD0','green':'LOD1','blue':'LOD2'},'host_scope':'Intel UHD 770 only',
     'culling_scope':'Auto LOD is retained in all cases; 450m/550m single-instance cull on/off controls independently test normal HISM visibility. Forest cull on/off pixels are reported separately.'}
with a.out.open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
print(out['status'],out['errors'])
for r in rows:
    if r['kind']=='forest':print(r['name'],r['lod_color_pixels'],'built',r['built_tree_verified'])
raise SystemExit(0 if not errors else 2)
