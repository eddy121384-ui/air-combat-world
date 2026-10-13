"""Separate screenshot identity/dimension check; does not rehabilitate its failed CSV."""
import json,hashlib,datetime
from pathlib import Path
from PIL import Image
r=Path(r'D:\Users\EDDY\Documents\GitHub\air-combat-world')
d=r/'unreal/ForestSpike/Saved/ForestSpike/b1a/resolution/resolution01'
req=json.loads((d/'request.json').read_text(encoding='utf-8-sig'))
state=json.loads((d/'run.json').read_text(encoding='utf-8-sig'))
log=(d/'engine.log').read_text(errors='replace')
p=d/'viewport_1x.png'
assert Image.open(p).size==(1920,1080)
assert p.stat().st_mtime>=datetime.datetime.fromisoformat(req['started_utc']).timestamp()
assert state['exit_code']==0 and 'LogExit: Exiting.' in log
assert 'Bringing World '+req['world_path']+'.'+req['level']+' up for play' in log
assert 'HighResShot 1 filename=' in ' '.join(req['args'])
result={'status':'PASS_FS_B1A_VIEWPORT_DIMENSIONS_ONLY','resolution':[1920,1080],
 'scope':'Fresh 1x game viewport screenshot with the same static launch settings. This auxiliary CSV FAIL is retained and excluded from performance analysis; screenshot interrupts normal profiling startup.',
 'csv_status_retained':state['status'],'exit_code':state['exit_code'],'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
with (d/'dimensions_only.json').open('x') as f:json.dump(result,f,indent=2)
print(result['status'])
