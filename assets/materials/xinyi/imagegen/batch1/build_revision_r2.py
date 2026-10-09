"""Rebuild r2 review from preserved originals; no Unreal or runtime code.
Requires Pillow/NumPy. --validate audits hashes and preservation without writes.
"""
from pathlib import Path
import argparse, hashlib, json, shutil
import numpy as np
from PIL import Image, ImageDraw
from build_review import ROOT, digest, font, metrics, edge_blend, repeat

def sample(a,u,v):
    h,w=a.shape; x=(u%1)*w; y=(v%1)*h
    x0=np.floor(x).astype(int)%w; y0=np.floor(y).astype(int)%h
    tx=x-np.floor(x); ty=y-np.floor(y)
    return ((1-ty)*((1-tx)*a[y0,x0]+tx*a[y0,(x0+1)%w])+
            ty*((1-tx)*a[(y0+1)%h,x0]+tx*a[(y0+1)%h,(x0+1)%w]))

def spatial_stats(a,lag):
    def corr(x,y): return round(float(np.corrcoef(x.ravel(),y.ravel())[0,1]),4)
    return {'horizontal_one_tile_lag_correlation':corr(a[:,:-lag],a[:,lag:]),
            'vertical_one_tile_lag_correlation':corr(a[:-lag],a[lag:]),
            'std_255':round(float(a.std()),4),
            'mean_abs_dx':round(float(np.abs(np.diff(a,axis=1)).mean()),4),
            'mean_abs_dy':round(float(np.abs(np.diff(a,axis=0)).mean()),4)}

def repair_coverage(im):
    a=np.asarray(im.convert('L'),dtype=float); background=float(np.median(a))
    return {'method':'fraction farther than 6 grayscale levels from image median; proxy, not semantic segmentation',
            'background_median_255':background,'fraction':round(float((np.abs(a-background)>6).mean()),4)}

def build():
    previous=json.loads((ROOT/'manifest_r1.json').read_text())
    log=json.loads((ROOT/'generation_log_r2.json').read_text())
    m=json.loads(json.dumps(previous)); m['revision']='r2'; m['revision_parent_commit']=log['parent_commit']
    m['active_sources']={'a1':'a1_r2','a2':'a2','a3':'a3_r2','b1':'b1','b2':'b2_r2','b3':'b3'}
    new={}
    for a in log['assets']:
        sid=a['id']; src=ROOT/'sources'/a['file']; original=Path(a['original_path'])
        if not src.exists(): shutil.copyfile(original,src)
        if original.exists(): assert digest(src)==digest(original)
        with Image.open(src) as native:
            native.load(); dims=list(native.size); mode=native.mode
            im=native.convert('L' if a['family']=='b2' else 'RGB').resize((1024,1024),Image.Resampling.LANCZOS)
        norm=ROOT/'normalized_1024'/a['file']; im.save(norm)
        candidate=im
        ops=['Convert native output to L mask or RGB color, Lanczos resize to 1024x1024']
        if a['family']=='b2':
            # Preserve sparse region shapes and flat background; no blur or global range amplification.
            arr=np.asarray(im,dtype=float); center=float(np.median(arr))
            arr=128+np.clip(arr-center,-12,12)
            candidate=Image.fromarray(np.uint8(np.rint(arr)))
            ops+=['Recenter image median to 128 and clamp deviations to +/-12, no blur']
        candidate=edge_blend(candidate)
        ops+=['64px opposing-border pair blend as build_review.edge_blend; no noise, mirroring or layout synthesis']
        out=ROOT/'processed'/a['file'].replace('.png','_candidate.png'); candidate.save(out)
        note={'a1':'No baked grout/grid; low-contrast ceramic mottling repeats. Opposing edge blend removes numeric jump; derivative band still requires art review.',
              'a3':'No panel joints; soft stone mineral groups repeat. Opposing edge blend removes numeric jump; subtle broad periodicity remains.',
              'b2':'Four isolated maintenance regions, substantially reduced coverage. Flat background supports wrapping; recognizable four-patch stamp still repeats.'}[a['family']]
        e={'id':sid,'revision':'r2','supersedes':a['family'],'filename':src.relative_to(ROOT).as_posix(),
           'role':a['label'],'material_family':'ageing mask' if a['family']=='b2' else 'material base',
           'dimensions':dims,'mode':mode,'sha256':digest(src),'generation_capability':log['capability'],
           'model':'not exposed by tool','prompt':a['prompt'],'generation_date':log['date'],
           'independent_ai_output':True,'status':'accepted','acceptance_scope':'offline candidate review; pending artistic approval',
           'visible_tiling_problems':note,'tiling_metrics':metrics(Image.open(src)),
           'normalized_copy':norm.relative_to(ROOT).as_posix(),'processed_derivative_files':[out.relative_to(ROOT).as_posix()],
           'imported_into_unreal':False}
        if a['family']=='b2': e['repair_coverage_proxy']=repair_coverage(im)
        m['sources'].append(e); new[a['family']]=e
        for kind,p,operation in [('normalized review copy',norm,ops[:1]),('processed game material candidate',out,ops)]:
            m['derivatives'].append({'source_id':sid,'kind':kind,'operation':operation,
                'output_filename':p.relative_to(ROOT).as_posix(),'output_sha256':digest(p),'dimensions':[1024,1024],
                'status':'accepted for offline review, pending artistic approval','tiling_metrics':metrics(Image.open(p))})
    byid={e['id']:e for e in m['sources']}
    active=[byid[m['active_sources'][k]] for k in ('a1','a2','a3','b1','b2','b3')]
    contact=Image.new('RGB',(1260,1040),'#172029'); d=ImageDraw.Draw(contact)
    d.text((20,12),'TAIPEI BATCH 1 / r2 ACTIVE SOURCES - AI image_gen.imagegen',font=font(25),fill='white')
    for i,e in enumerate(active):
        x=20+i%3*415; y=60+i//3*485
        contact.paste(Image.open(ROOT/e['filename']).convert('RGB').resize((390,390),Image.Resampling.LANCZOS),(x,y))
        d.text((x,y+395),e['role'],font=font(20),fill='white')
        d.text((x,y+422),Path(e['filename']).name,font=font(15),fill='#ccd7df')
        d.text((x,y+443),'AI image_gen.imagegen / offline candidate',font=font(15),fill='#ccd7df')
    contact.save(ROOT/'review/contact_sheet.png')
    tiling=Image.new('RGB',(1880,810),'#172029'); d=ImageDraw.Draw(tiling)
    d.text((16,10),'r2 ACTIVE SET / 3x3 RAW SOURCE (left) vs 1024 CANDIDATE (right)',font=font(25),fill='white')
    for i,e in enumerate(active):
        x=16+i%3*620; y=60+i//3*370
        d.text((x,y),e['role'],font=font(19),fill='white')
        tiling.paste(repeat(Image.open(ROOT/e['filename'])),(x,y+28))
        tiling.paste(repeat(Image.open(ROOT/e['processed_derivative_files'][0])),(x+305,y+28))
        d.text((x,y+332),'Raw AI / '+str(e['dimensions'][0])+' square',font=font(15),fill='white')
        d.text((x+305,y+332),'1024 candidate / '+('r2' if e.get('revision') else 'retained r1'),font=font(15),fill='white')
    tiling.save(ROOT/'review/tiling_review.png')
    compare=Image.new('RGB',(1480,1090),'#172029'); d=ImageDraw.Draw(compare)
    d.text((16,10),'r1 vs r2 / ORIGINALS + 3x3 CANDIDATE REVIEW',font=font(26),fill='white')
    for row,k in enumerate(('a1','a3','b2')):
        old=byid[k]; e=new[k]; y=55+row*345
        ims=[Image.open(ROOT/old['filename']),Image.open(ROOT/e['filename']),
             repeat(Image.open(ROOT/old['normalized_copy'])),repeat(Image.open(ROOT/e['processed_derivative_files'][0]))]
        labels=[k.upper()+' r1 original','r2 original / AI','r1 3x3 (unaccepted)','r2 3x3 candidate']
        for j,(im,label) in enumerate(zip(ims,labels)):
            x=16+j*365; d.text((x,y),label,font=font(19),fill='white')
            compare.paste(im.convert('RGB').resize((300,300),Image.Resampling.LANCZOS),(x,y+28))
    compare.save(ROOT/'review/comparison_r2.png')
    study=Image.new('RGB',(1480,1090),'#172029'); d=ImageDraw.Draw(study)
    d.text((16,10),'B1/B3 REPETITION STUDY - NO ADDITIONAL BLUR / NO RUNTIME CHANGE',font=font(25),fill='white')
    findings=[]
    for row,k in enumerate(('b1','b3')):
        a=np.asarray(Image.open(ROOT/byid[k]['processed_derivative_files'][0]),dtype=float)
        n=768; yy,xx=np.mgrid[:n,:n]; u=xx/(n/3); v=yy/(n/3)
        baseline=sample(a,u,v)
        secondary=sample(a,-u*1.37+0.371,v*1.37+0.619)
        mixed=(baseline+secondary)*0.5
        mixed=(mixed-mixed.mean())*(baseline.std()/mixed.std())+baseline.mean()
        mixed=np.clip(mixed,112,144)
        walls=Image.new('RGB',(450,450),'#172029')
        for i in range(9):
            seed=hashlib.sha256((k+':wall:'+str(i)).encode()).digest()
            y2,x2=np.mgrid[:146,:146]; scale=0.9+0.2*seed[2]/255
            wall=sample(a,((-1 if seed[3]%2 else 1)*x2/146)*scale+seed[0]/255,y2/146*scale+seed[1]/255)
            walls.paste(Image.fromarray(np.uint8(np.rint(wall))).convert('RGB'),(i%3*150,i//3*150))
        y=65+row*490
        for col,(arr,label) in enumerate([(baseline,k.upper()+' regular repeat'),(walls,'Separate walls / 1 sample'),(mixed,'Continuous wall / 2 samples')]):
            x=16+col*490; d.text((x,y),label,font=font(21),fill='white')
            im=arr if isinstance(arr,Image.Image) else Image.fromarray(np.uint8(np.rint(arr))).convert('RGB')
            study.paste(im.resize((450,450),Image.Resampling.LANCZOS),(x,y+28))
        findings.append({'source_id':k,'baseline':spatial_stats(baseline,256),'two_sample_study':spatial_stats(mixed,256),
                         'important':'Two samples exceed current one-sample budget. Separate-wall transforms do not solve repeat within one continuous wall. No vertical flips/rotations.'})
    study.save(ROOT/'review/repetition_study_r2.png')
    m.update({'generation_attempts':10,'rejected_generations':1,'independent_ai_source_count':9,
              'accepted_independent_ai_source_count':6,'needs_revision_source_count':3,
              'active_independent_ai_source_count':6,'active_accepted_candidate_count':6,
              'processed_variant_count':6,'normalized_copy_count':9,'review_image_count':6,
              'total_image_file_count':30,'revision_generation_attempts':3,'revision_rejected_generations':0})
    m['repetition_investigation']={'method':'Offline bilinear periodic resampling of retained candidates; review previews only, no new material asset',
        'one_sample':'Per-building deterministic UV offset + horizontal mirror + 0.9..1.1 scale. Reduces aligned repetition across separate buildings; intra-wall periodicity unchanged.',
        'two_sample':'0.5*M(u,v)+0.5*M(-1.37u+0.371,1.37v+0.619), variance restored and clamped to 112..144. No additional blur. Second sample costs +1 texture read; not recommended under current cap without future budget approval.',
        'findings':findings}
    m['repair_coverage_comparison']={'old':repair_coverage(Image.open(ROOT/byid['b2']['normalized_copy'])),
                                     'revised':new['b2']['repair_coverage_proxy']}
    m['review_files']=[{'filename':p.relative_to(ROOT).as_posix(),'sha256':digest(p)} for p in sorted((ROOT/'review').glob('*.png'))]
    m['original_preservation']={'manifest':'manifest_r1.json','all_six_r1_sources_unchanged':True,'a2_b1_b3_candidates_unchanged':True}
    (ROOT/'manifest.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    validate()

def validate():
    m=json.loads((ROOT/'manifest.json').read_text()); old=json.loads((ROOT/'manifest_r1.json').read_text())
    files=[]
    for e in m['sources']:
        p=ROOT/e['filename']; assert digest(p)==e['sha256']; files.append(p)
        with Image.open(p) as im: im.load(); assert list(im.size)==e['dimensions'] and im.format=='PNG'
        assert e['independent_ai_output'] and not e['imported_into_unreal']
    for e in m['derivatives']:
        p=ROOT/e['output_filename']; assert digest(p)==e['output_sha256']; files.append(p)
        with Image.open(p) as im:
            im.load(); assert im.size==(1024,1024) and im.format=='PNG'
            if e['source_id'].startswith('b'): assert im.mode=='L'
            if e['kind']=='processed game material candidate':
                a=np.asarray(im); assert np.array_equal(a[:,0],a[:,-1]) and np.array_equal(a[0],a[-1])
    for e in m['review_files']:
        p=ROOT/e['filename']; assert digest(p)==e['sha256']; files.append(p)
        with Image.open(p) as im: im.load(); assert im.format=='PNG'
    for e in old['sources']: assert digest(ROOT/e['filename'])==e['sha256']
    for e in old['derivatives']: assert digest(ROOT/e['output_filename'])==e['output_sha256']
    for e in old['review_files']:
        archive=Path(e['filename']).with_stem(Path(e['filename']).stem+'_r1')
        assert digest(ROOT/archive)==e['sha256']
    assert len(m['sources'])==9 and len(m['derivatives'])==15 and len(m['active_sources'])==6
    assert len(files)==30 and set(files)==set(ROOT.rglob('*.png'))
    assert m['repair_coverage_comparison']['revised']['fraction'] < m['repair_coverage_comparison']['old']['fraction']/2
    print(json.dumps({'validation':'PASS','originals':9,'active_candidates':6,'normalized':9,'processed':6,'sheets':6,'total_png':30,'all_r1_asset_hashes_unchanged':True}))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--validate',action='store_true'); args=p.parse_args()
    validate() if args.validate else build()
