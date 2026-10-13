"""Range-guided review annotation; original images and materials remain unchanged."""
import sys,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
r=Path(__file__).resolve().parents[3];raw=r/'unreal/ForestSpike/Saved/ForestSpike/b1a'
sys.path.insert(0,str(r/'tools/forestspike'))
from fs_ids import load_id
rows=[]
for arm in ['A','B']:
 pose='v1_agl200_p10';p=raw/f'native_static_primary/{pose}_{arm}1_visual.png';idp=raw/f'stills01/captures/{pose}_{arm}1_id.png'
 cls,rng,exact,_=load_id(idp);assert exact.mean()>.999
 im=np.array(Image.open(p).convert('RGB'));forest=np.isin(cls,[2,5,6])
 im[forest&(rng>=400)&(rng<=403)]=[255,255,0];im[forest&(rng>=497)&(rng<=500)]=[255,0,0]
 out=raw/f'review_media/{pose}_{arm}1_range_overlay.png';assert not out.exists();Image.fromarray(im).save(out)
 rows.append({'file':str(out),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'source':str(p),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'id_source':str(idp),'id_sha256':hashlib.sha256(idp.read_bytes()).hexdigest(),'annotation':'Yellow400..403m / red497..500m slant range only in core forest/tree ID classes. Existing open clearings are not marked as seams. Original native pixels unchanged elsewhere; no rescaling.'})
with (raw/'review_media/range_overlays.json').open('x') as f:json.dump(rows,f,indent=2)
