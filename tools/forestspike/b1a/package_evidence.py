"""Archive reviewable B1a evidence without rewriting any raw output."""
import json,hashlib,shutil,re,zipfile,datetime,subprocess
from pathlib import Path
from PIL import Image,ImageDraw
r=Path(__file__).resolve().parents[3]
raw=r/'unreal/ForestSpike/Saved/ForestSpike/b1a'
out=r/'docs/evidence/forestspike-b1a'
out.mkdir(parents=True,exist_ok=False)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def scrub(v):
 if isinstance(v,dict):return {k:('[redacted UE loginid]' if k.lower()=='loginid' else scrub(x)) for k,x in v.items()}
 if isinstance(v,list):return [scrub(x) for x in v]
 return v
def dump(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf-8') as f:json.dump(v,f,indent=2)
copied=[]
for p in raw.rglob('*.json'):
 # Full raw manifests/validation receipts stay inspectable, including failures.
 dest=out/'records'/p.relative_to(raw)
 dump(dest,scrub(read(p)));copied.append(str(dest.relative_to(out)))
schedule=read(raw/'schedule.json')['runs'];assert len(schedule)==80
archives=[]
for rd in range(1,6):
 path=out/f'csv-round-{rd:02d}-metadata-redacted.zip';entries=[]
 with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for row in schedule:
   if row['round']!=rd:continue
   d=raw/'perf'/row['tag'];c=read(d/'completion.json');p=Path(c['csv']);b=p.read_bytes()
   login=c['metadata'].get('loginid','');public=b.replace(login.encode(),b'[redacted UE loginid]') if login else b
   assert sha(p)==c['csv_sha256']
   name=row['tag']+'/'+p.name;z.writestr(name,public)
   entries.append({'tag':row['tag'],'entry':name,'raw_sha256':sha(p),'public_sha256':hashlib.sha256(public).hexdigest(),'bytes':len(public),'transformation':'Only UE loginid metadata redacted; all timing values, frames and other metadata unchanged.'})
 archives.append({'file':path.name,'sha256':sha(path),'entries':entries})
dump(out/'csv-archive-index.json',archives)
# Complete per-frame camera evidence for all eight paths.
for path in ['V3','V5']:
 for group in ['A0','A1','B0','B1']:
  tag=f'dynamic_{group}_{path}_01';p=raw/'perf'/tag/'camera_trace.csv'
  dest=out/'camera'/f'{tag}.csv';dest.parent.mkdir(exist_ok=True);shutil.copyfile(p,dest)
# Relevant engine lines are excerpts; their raw source hashes remain in the inventory.
keep=re.compile(r'FS_B1|LogCsvProfiler|LogFoliage|Bringing World|LogMovieRenderPipeline|Applying CVar|LogExit|Fatal|Crash|Resolution')
for p in raw.rglob('engine.log'):
 dest=out/'log-excerpts'/p.relative_to(raw);dest.parent.mkdir(parents=True,exist_ok=True)
 text=''.join(line for line in p.read_text(errors='replace').splitlines(keepends=True) if keep.search(line))
 text=re.sub(r'(LoginId[=: ]+)[0-9a-fA-F]{32}',r'\1[redacted UE loginid]',text,flags=re.I)
 text='\n'.join(line.rstrip() for line in text.splitlines())+'\n'
 dest.write_text(text,encoding='utf-8')
# Original PNG bytes, same fixed view; 4K comparison JPEGs are navigation aids only.
captures=raw/'stills01/captures';images=out/'images';images.mkdir()
poses=['v1_agl50_p15','v1_agl200_p10','v1_agl500_p15','v1_agl1000_p20','v3i_t26','v5i_agl200_a000']
available={p.name:p for p in captures.glob('*_visual.png')}
available.update({p.name:p for p in (raw/'native_static_primary').glob('*.png')})
for group in ['A0','A1','B0','B1']:
 available[f'v3i_t26_{group}_visual.png']=next((raw/f'movies/native_{group}_V3_03/frames').rglob('frame_0840.png'))
 available[f'v5i_agl200_a000_{group}_visual.png']=next((raw/f'movies/clip_{group}_V5_01/frames').rglob('frame_0120.png'))
selection=[]
for pose in poses:
 groupfiles=[]
 for group in ['A0','A1','B0','B1']:
  name=f'{pose}_{group}_visual.png'
  if name not in available:continue
  p=available[name];shutil.copyfile(p,images/name);groupfiles.append((group,p));selection.append({'public_file':name,'raw_file':str(p),'sha256':sha(p),'pipeline':'Native MRQ PNG; unchanged original bytes'})
 if len(groupfiles)!=4:continue
 canvas=Image.new('RGB',(3840,2160));draw=ImageDraw.Draw(canvas)
 for i,(group,p) in enumerate(groupfiles):
  x=(i%2)*1920;y=(i//2)*1080;canvas.paste(Image.open(p).convert('RGB'),(x,y));draw.rectangle((x,y,x+180,y+32),fill='black');draw.text((x+8,y+8),group+' '+('S-off' if group.endswith('0') else 'S-on'),fill='white')
 canvas.save(images/f'{pose}_four_arm_review.jpg',quality=95,subsampling=0)
for p in (raw/'review_media').glob('*.mp4'):
 dest=out/'video'/p.name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(p,dest)
for p in (raw/'review_media').glob('*.png'):shutil.copyfile(p,images/p.name)
for p in (raw/'coverage03/captures').glob('*.png'):shutil.copyfile(p,images/p.name)
shutil.copyfile(captures/'v3i_t26_A1_visual.png',images/'diagnostic_scenecapture_v3i_t26_A1.png')
dump(out/'primary-image-provenance.json',selection)
# Assert immutable pre-existing evidence, including GLBs, Content and B0 receipts.
baseline=read(raw/'preserved_before_b1a.json')
verified=[]
for f in baseline['files']:
 p=r/f['file'];actual=sha(p);assert actual==f['sha256'],f['file'];assert p.stat().st_size==f['bytes']
 verified.append({'file':f['file'],'sha256':actual,'bytes':f['bytes']})
dump(out/'preserved-originals.json',{'status':'PASS_ORIGINALS_UNCHANGED','base_head':baseline['base_head'],'count':len(verified),'files':verified})
# Reuse independent complete-movie hash validation to avoid needlessly rereading GBs.
cache={}
for p in (raw/'movies').glob('*/validated.json'):
 for f in read(p)['frames']:cache[str(Path(f['file']))]=f['sha256']
inventory=[]
for p in sorted(raw.rglob('*')):
 if p.is_file():inventory.append({'file':str(p.relative_to(raw)),'bytes':p.stat().st_size,'sha256':cache.get(str(p)) or sha(p)})
dump(out/'raw-output-inventory.json',{'root':str(raw),'status':'COMPLETE_RETAINED_B1A_OUTPUT_INVENTORY','generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':inventory})
assets=r/'unreal/ForestSpike/Content/ForestSpike/B1a_20261013a'
dump(out/'generated-asset-inventory.json',{'root':str(assets),'files':[{'file':str(p.relative_to(assets)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(assets.rglob('*')) if p.is_file()]})
shutil.copyfile(raw/'tests-pre-sweep-40.txt',out/'tests-pre-sweep-40.txt')
print('Packaged B1a evidence; original files unchanged:',len(verified),'raw files:',len(inventory))
