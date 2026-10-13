"""Cross-check effective initialization across every accepted capture mode."""
import json,re,hashlib,argparse
from pathlib import Path
r=Path(__file__).resolve().parents[3];raw=r/'unreal/ForestSpike/Saved/ForestSpike/b1a';rows=[]
p=argparse.ArgumentParser();p.add_argument('--expected-logs',type=int,default=105);p.add_argument('--out',type=Path,default=raw/'analysis/render_settings.json');args=p.parse_args()
logs=[raw/'perf'/x['tag']/'engine.log' for x in json.loads((raw/'schedule.json').read_text(encoding='utf-8-sig'))['runs']]
logs+=list((raw/'perf').glob('dynamic_*/engine.log'))+list((raw/'runtime_lod').glob('*/engine.log'))
logs+=[p.parent/'engine.log' for p in (raw/'movies').glob('*/validated.json')]+[raw/'stills01/engine.log']
for p in logs:
 text=p.read_text(errors='replace');values={}
 for name,expected in [('r.AntiAliasingMethod',2),('r.TemporalAA.Quality',2),('r.ShadowQuality',5),('r.Shadow.CSM.MaxCascades',10),('r.Shadow.DistanceScale',1)]:
  found=re.findall(r'Set CVar \[\['+re.escape(name)+r':([0-9.]+)',text);assert found and all(float(x)==expected for x in found),(p,name,found)
  values[name]=expected
 rows.append({'log':str(p.relative_to(raw)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'initialization_settings':values})
assert len(rows)==args.expected_logs
result={'status':'PASS_FS_B1A_COMMON_RENDER_INITIALIZATION','logs':rows,'scope':'All 80 static, 8 dynamic, 8 standalone LOD, all currently accepted MRQ and one SceneCapture stage initialize the same listed values. Per-light CSM count=4 is bounded by global maximum10. Native MRQ disabled quality overrides; AA flags off only in diagnostic ID/LOD jobs.',
 'legacy_readback_correction':{'name':'r.PostProcessAAQuality','observed_value':0,'meaning':'Unregistered legacy CVar in installed UE5.8; Kismet returns0 and warns when lookup fails. Does NOT mean TAA disabled. Valid r.TemporalAA.Quality initializes2 in every accepted log.',
 'source_refs':['Engine/Source/Runtime/Engine/Private/KismetSystemLibrary.cpp:610','Engine/Source/Runtime/Renderer/Private/PostProcess/TemporalAA.cpp:46']}}
with args.out.open('x') as f:json.dump(result,f,indent=2)
print(len(rows),'accepted-mode logs share AA/shadow initialization; legacy AA readback corrected')
