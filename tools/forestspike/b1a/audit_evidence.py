"""Check review exports against immutable raw sources; no reclassification of failures."""
import json,hashlib,zipfile,re
from pathlib import Path
r=Path(__file__).resolve().parents[3];raw=r/'unreal/ForestSpike/Saved/ForestSpike/b1a';out=r/'docs/evidence/forestspike-b1a'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
entries=0
for archive in read(out/'csv-archive-index.json'):
 assert sha(out/archive['file'])==archive['sha256']
 with zipfile.ZipFile(out/archive['file']) as z:
  for e in archive['entries']:
   d=raw/'perf'/e['tag'];c=read(d/'completion.json');p=Path(c['csv']);b=p.read_bytes();login=c['metadata']['loginid'].encode();public=z.read(e['entry'])
   assert b.count(login)==1,'loginid replacement must affect only its one metadata value'
   assert public==b.replace(login,b'[redacted UE loginid]')
   assert sha(p)==e['raw_sha256']==c['csv_sha256']
   assert sha(Path(c['log']))==c['log_sha256']
   assert hashlib.sha256(public).hexdigest()==e['public_sha256']
   assert read(d/'run.json')['status']=='PASS_FS_B1A_RUN' and read(d/'motion.json')['status']=='PASS_FS_B1A_MOTION'
   entries+=1
assert entries==80
primary=read(out/'primary-image-provenance.json');assert len(primary)==24
for e in primary:assert sha(out/'images'/e['public_file'])==e['sha256']==sha(Path(e['raw_file']))
report=r/'docs/forestspike-b1a-factorial-result.md'
links=re.findall(r'\]\(([^)]+)\)',report.read_text(encoding='utf-8'));checked=[]
for link in links:
 if '://' in link or link.startswith('#'):continue
 assert (report.parent/link).exists(),link;checked.append(link)
preserved=read(out/'preserved-originals.json');assert preserved['status']=='PASS_ORIGINALS_UNCHANGED' and preserved['count']==1100
result={'status':'PASS_FS_B1A_REVIEW_EXPORT_AUDIT','formal_csv_count':entries,'numeric_export_scope':'Exact byte identity except the single UE loginid metadata value; hashes of all formal raw CSV/log files rechecked.','primary_png_count':len(primary),'relative_report_links_checked':checked,'preserved_originals':1100,'scope':'Export/data integrity only; does not turn incomplete F9/F11 or failed F10 into visual PASS.'}
with (out/'final-export-audit.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
print(result['status'])
